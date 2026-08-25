"""Layer 7 - Quality, Security & Release Excellence Division (QSRED). Quality engine.

Runs a release subject through the twelve quality departments, the Release
Director merges their findings into one Release Excellence Report with a
formal Final Decision (Go / Conditional Go / No Go) and a release certificate,
and the report is persisted to ``data/quality/reports.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the report still completes using whatever findings were gathered. If the
Release Director fails, the engine still produces a deterministic fallback
decision from the department scores - the gate is never silently opened.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from statistics import mean
from typing import Any, Optional

from quality.models import QualityDepartmentReport, ReleaseExcellenceReport
from quality.prompts import (
    QUALITY_DEPARTMENTS,
    QUALITY_DEPARTMENTS_LIST,
    QUALITY_ORDER,
    SUBJECT_TYPES,
    build_department_request_prompt,
    build_director_prompt,
    get_quality_department_prompt,
)

logger = logging.getLogger(__name__)

_QUALITY_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "quality")
_QUALITY_DATA_FILE = os.path.join(_QUALITY_DATA_DIR, "reports.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEPARTMENT_TIMEOUT = 240
_DIRECTOR_TIMEOUT = 300

_STRICT_FORMAT_REMINDER = (
    "\n\nIMPORTANT: your previous reply did not follow the required format. "
    "Reply AGAIN using EXACTLY these headings, one per line: "
    "## VERDICT: <support|recommend|caution|risk>, ## CONFIDENCE: <0.0-1.0>, "
    "## SCORE: <0-100>, ## CHECKS, ## FINDINGS, ## RECOMMENDATIONS, ## EVIDENCE. "
    "Put at least one bullet under CHECKS, FINDINGS, and RECOMMENDATIONS."
)


def _err_text(e: Exception) -> str:
    """Human-readable error message (asyncio.TimeoutError has an empty str())."""
    if isinstance(e, asyncio.TimeoutError):
        return f"Timed out after {_DEPARTMENT_TIMEOUT}s"
    return str(e)[:300] or type(e).__name__


def _quota_exhausted(e: Exception) -> bool:
    """True when the error is a definitive provider quota/rate-limit
    exhaustion, which a retry cannot succeed past. The LLM manager already
    waited through its internal 60s backoff, so retrying only burns time."""
    msg = str(e)
    return ("Rate limited" in msg or "remaining=0" in msg or "quota" in msg.lower())


# --- Parsing helpers (robust against free-form LLM output) ---

def _find_section(text: str, header: str) -> str:
    """Return the text of a '## HEADER' section up to the next '##' or end."""
    pattern = rf"^##\s*{re.escape(header)}\s*:?\s*$"
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip(), re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        m = re.search(rf"^##\s*{re.escape(header)}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
        return ""
    out = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        out.append(line)
    return "\n".join(out).strip()


def _bullets(section: str) -> list[str]:
    out = []
    for line in section.splitlines():
        line = line.strip().lstrip("*-•").strip()
        if line and not line.lower().startswith(("##", "section")):
            out.append(line)
    return out


def _inline_value(text: str, header: str) -> str:
    m = re.search(rf"^##\s*{re.escape(header)}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def _find_section_until(text: str, header: str, stop_headers: list[str]) -> str:
    """Return a section's full text, capturing inner '##' sub-headers, until
    one of the given stop headers. Used for sections like the Release
    Certificate whose body itself contains '##' headings."""
    m = re.search(
        rf"^##\s*{re.escape(header)}\s*:?\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in stop_headers)})\s*:?\s*$|\Z)",
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _parse_final_decision(text: str) -> str:
    """Parse the Go / Conditional Go / No Go decision. No Go and Conditional Go
    must be checked before Go so their substrings don't match it."""
    section = _find_section(text, "Final Decision")
    if not section:
        for line in text.splitlines():
            if re.search(r"final decision", line, re.IGNORECASE):
                section = line
                break
    low = section.lower()
    if "no go" in low:
        return "No Go"
    if "conditional go" in low:
        return "Conditional Go"
    if re.search(r"\bgo\b", low):
        return "Go"
    return "pending"


def _decision_from_score(score: Optional[int]) -> str:
    """Deterministic fallback decision when the Release Director is unavailable."""
    if score is None:
        return "Conditional Go"
    if score >= 60:
        return "Go"
    if score >= 40:
        return "Conditional Go"
    return "No Go"


def _parse_department_output(text: str) -> dict[str, Any]:
    verdict_match = re.search(
        r"##\s*VERDICT\s*:?\s*(support|recommend|caution|risk|neutral)",
        text, re.IGNORECASE,
    )
    verdict = "neutral"
    if verdict_match:
        verdict = verdict_match.group(1).lower()

    confidence = 0.5
    conf_match = re.search(r"##\s*CONFIDENCE\s*:?\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
    if conf_match:
        try:
            confidence = max(0.0, min(1.0, float(conf_match.group(1))))
        except ValueError:
            confidence = 0.5

    score: Optional[int] = None
    score_match = re.search(r"##\s*SCORE\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None

    checks = _bullets(_find_section(text, "CHECKS"))
    findings = _bullets(_find_section(text, "FINDINGS"))
    recommendations = _bullets(_find_section(text, "RECOMMENDATIONS"))
    evidence = _bullets(_find_section(text, "EVIDENCE"))
    return {
        "verdict": verdict,
        "confidence": confidence,
        "score": score,
        "checks": checks,
        "findings": findings,
        "recommendations": recommendations,
        "evidence": evidence,
        "report": text,
    }


def _salvage_department_text(text: str) -> dict[str, Any]:
    """Salvage a non-empty but off-format reply instead of failing the department.

    Keeps the raw text as the report (the Release Director still reads it) and
    extracts usable bullet points as checks so the department counts as done.
    """
    lines = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("*-•#").strip()
        if line and len(line) > 3 and not line.lower().startswith(("##", "section", "verdict", "confidence")):
            lines.append(line)
    return {
        "verdict": "caution",
        "confidence": 0.3,
        "score": None,
        "checks": lines[:10],
        "findings": lines[:10],
        "recommendations": [],
        "evidence": [],
        "report": text,
    }


_PACKAGE_LIST_SECTIONS = {
    "Functional QA": "functional_qa",
    "Performance Review": "performance_review",
    "Security Review": "security_review",
    "Compliance Review": "compliance_review",
    "Accessibility Review": "accessibility_review",
    "Documentation Status": "documentation_status",
    "Architecture Review": "architecture_review",
    "Deployment Readiness": "deployment_readiness",
    "Monitoring Status": "monitoring_status",
    "Enterprise Readiness": "enterprise_readiness",
    "Known Risks": "known_risks",
    "Rollback Strategy": "rollback_strategy",
}

_PACKAGE_TEXT_SECTIONS = {
    "Release Certificate": "release_certificate",
    "Executive Summary": "executive_summary",
}


def _parse_package(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _PACKAGE_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _PACKAGE_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The Release Certificate body contains its own ## sub-headers (Release
    # Version, Final Decision, Required Fixes, Conditions, Sign-off), so parse
    # it with a dedicated extractor that runs until the Executive Summary.
    data["release_certificate"] = _find_section_until(text, "Release Certificate", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Overall Quality Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["quality_score"] = score

    version = _find_section(text, "Release Version") or _inline_value(text, "Release Version")
    data["release_version"] = version.splitlines()[0].strip().lstrip("-*").strip() if version else ""

    data["final_decision"] = _parse_final_decision(text)
    return data


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        key = it.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _report_markdown(p: dict[str, Any]) -> str:
    lines = ["# Quality, Security & Release Excellence Division - Release Excellence Report"]
    lines.append("")
    if p.get("release_version"):
        lines.append(f"**Release Version:** {p['release_version']}")
    if p.get("quality_score") is not None:
        lines.append(f"**Overall Quality Score:** {p['quality_score']}/100")
    lines.append(f"**Final Decision:** {p.get('final_decision') or 'pending'}")
    for label, key in _PACKAGE_LIST_SECTIONS.items():
        values = p.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if p.get("release_certificate"):
        lines.append("")
        lines.append("## Release Certificate")
        lines.append(p["release_certificate"])
    if p.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(p["executive_summary"])
    return "\n".join(lines)


class QualityDivision:
    """The Quality, Security & Release Excellence Division (Layer 7)."""

    def __init__(
        self,
        config,
        llm_manager,
        kb=None,
        data_file: str | None = None,
        model: str | None = None,
    ) -> None:
        self.config = config
        self.llm = llm_manager
        self.kb = kb
        self.model = model or _DEFAULT_MODEL
        self.reports: dict[str, ReleaseExcellenceReport] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _QUALITY_DATA_FILE
        self._load()

    # --- Persistence ---

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump({"reports": [p.model_dump() for p in self.reports.values()]}, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("reports", []):
                report = ReleaseExcellenceReport.model_validate(raw)
                self.reports[report.id] = report
            logger.info(f"Loaded {len(self.reports)} Release Excellence Reports from disk")
        except Exception as e:
            logger.error(f"Failed to load Release Excellence Reports: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": QUALITY_DEPARTMENTS[did]["name"],
                "title": QUALITY_DEPARTMENTS[did]["title"],
                "order": QUALITY_ORDER.index(did),
                "is_coordinator": did == "release-director",
            }
            for did in QUALITY_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [p for p in self.reports.values() if p.status == "completed"]
        confidences = [p.avg_confidence for p in completed if p.avg_confidence is not None]
        scores = [p.quality_score for p in completed if p.quality_score is not None]
        decisions = {"go": 0, "conditional_go": 0, "no_go": 0}
        for p in completed:
            d = (p.final_decision or "").lower()
            if d == "go":
                decisions["go"] += 1
            elif d == "conditional go":
                decisions["conditional_go"] += 1
            elif d == "no go":
                decisions["no_go"] += 1
        return {
            "total": len(self.reports),
            "in_progress": sum(1 for p in self.reports.values() if p.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for p in self.reports.values() if p.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_quality_score": round(mean(scores)) if scores else None,
            "total_checks": sum(p.total_checks for p in completed),
            "total_findings": sum(p.total_findings for p in completed),
            "final_decisions": decisions,
            "departments": len(QUALITY_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
        }

    def list_reports(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.reports.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": p.id,
                "request": p.request[:120],
                "subject_type": p.subject_type,
                "status": p.status,
                "stage": p.stage,
                "created_at": p.created_at,
                "completed_at": p.completed_at,
                "avg_confidence": p.avg_confidence,
                "quality_score": p.quality_score,
                "final_decision": p.final_decision,
                "release_version": p.release_version,
                "total_checks": p.total_checks,
                "total_findings": p.total_findings,
                "departments_completed": sum(1 for rep in p.reports if rep.status == "completed"),
                "total_departments": len(p.reports),
                "board_review_id": p.board_review_id,
            })
        return out

    def get_report(self, report_id: str) -> ReleaseExcellenceReport | None:
        return self.reports.get(report_id)

    def get_report_dict(self, report_id: str) -> dict[str, Any] | None:
        p = self.reports.get(report_id)
        return p.model_dump() if p else None

    def delete_report(self, report_id: str) -> bool:
        if report_id not in self.reports:
            return False
        if report_id in self._running:
            self._running[report_id].cancel()
            del self._running[report_id]
        del self.reports[report_id]
        self.persist()
        return True

    def board_request_text(self, report: ReleaseExcellenceReport) -> str:
        """Build a board review request that carries this report's findings."""
        summary = report.executive_summary or "Release Excellence Report completed; see the report for details."
        return (
            f"{report.request}\n\n"
            f"[Release Excellence Report from QSRED report {report.id[:8]}: final decision "
            f"{report.final_decision} - {summary}]"
        )

    # --- Release workflow ---

    async def run_review(self, request: str, subject_type: str = "release") -> dict[str, Any]:
        """Run a full release review in the background. Updates the stored report."""
        report_id = str(uuid.uuid4())
        report = ReleaseExcellenceReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report

        task = asyncio.create_task(self._execute(report))
        self._running[report_id] = task
        task.add_done_callback(lambda t: self._running.pop(report_id, None) and None)
        return {"status": "started", "report_id": report_id, "report": report.model_dump()}

    async def run_review_sync(self, request: str, subject_type: str = "release") -> dict[str, Any]:
        """Run a full release review synchronously (blocks until finished). For tests/CLI."""
        report_id = str(uuid.uuid4())
        report = ReleaseExcellenceReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report
        await self._execute(report)
        return report.model_dump()

    async def _execute(self, report: ReleaseExcellenceReport) -> None:
        try:
            await self._run_departments(report)
            await self._run_director(report)
            self._finalize(report)
            if report.status != "failed":
                report.status = "completed"
            report.stage = "done"
            report.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            report.status = "cancelled"
            report.error = "Release Excellence Report cancelled"
        except Exception as e:
            logger.exception("Release Excellence Report failed")
            report.status = "failed"
            report.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for quality review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_quality_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> QualityDepartmentReport:
        dept = QUALITY_DEPARTMENTS[department_id]
        return QualityDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, report: ReleaseExcellenceReport) -> None:
        report.stage = "review"

        async def run_one(department_id: str) -> None:
            dept_report = self._report_skeleton(department_id)
            dept_report.started_at = datetime.utcnow().isoformat() + "Z"
            report.reports.append(dept_report)
            dept = QUALITY_DEPARTMENTS[department_id]
            focus = " ".join(dept.get("focus_areas", []))
            try:
                user_prompt = build_department_request_prompt(
                    department_id, report.request, report.subject_type,
                    foundation_block=self._foundation_block(report.request + " " + focus),
                )
                parsed = await self._department_parsed(department_id, user_prompt)
                self._apply_parsed(dept_report, parsed)
                dept_report.completed_at = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                dept_report.status = "failed"
                dept_report.error = _err_text(e)
                logger.warning(f"Quality department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in QUALITY_DEPARTMENTS_LIST:
            await run_one(department_id)

    async def _department_parsed(self, department_id: str, user_prompt: str) -> dict[str, Any]:
        """Call a department, retrying once on transient failures / empty
        replies (the LLM manager retries internally, but a single extra attempt
        catches brief provider outages)."""
        last_exc: Exception | None = None
        for attempt in range(2):
            prompt = user_prompt + (_STRICT_FORMAT_REMINDER if attempt else "")
            try:
                text = await self._call_department(department_id, prompt)
                parsed = _parse_department_output(text)
                if not parsed["findings"] and not parsed["recommendations"] and not parsed["evidence"]:
                    if attempt == 0:
                        continue  # retry once with a strict format reminder
                    if text and text.strip():
                        return _salvage_department_text(text)
                    raise ValueError("Empty response from LLM - no parsable sections in reply")
                return parsed
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                if attempt == 0 and not _quota_exhausted(e):
                    logger.warning(f"Quality department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, dept_report: QualityDepartmentReport, parsed: dict[str, Any]) -> None:
        dept_report.verdict = parsed["verdict"]
        dept_report.confidence = parsed["confidence"]
        dept_report.score = parsed.get("score")
        dept_report.checks = parsed["checks"]
        dept_report.findings = parsed["findings"]
        dept_report.recommendations = parsed["recommendations"]
        dept_report.evidence = parsed["evidence"]
        dept_report.report = parsed["report"]
        dept_report.status = "completed"

    # --- Release Director + report ---

    async def _run_director(self, report: ReleaseExcellenceReport) -> None:
        report.stage = "synthesis"
        director = self._report_skeleton("release-director")
        director.started_at = datetime.utcnow().isoformat() + "Z"
        report.reports.append(director)

        dept_reports = []
        for r in report.reports:
            if r.department_id == "release-director":
                continue
            header = f"### {r.department_title} ({r.department_id})\n"
            if r.status == "completed":
                body = r.report or r.findings_text()
                dept_reports.append(header + body[:3000])
            else:
                dept_reports.append(header + f"_(department assessment unavailable: {r.error or 'failed'})_")

        data: dict[str, Any] = {}
        try:
            user_prompt = build_director_prompt(
                report.request, dept_reports, report.subject_type,
                foundation_block=self._foundation_block(report.request + " quality security compliance", 3),
            )
            text = await self._call_department("release-director", user_prompt, max_tokens=4000)
            parsed = _parse_package(text)
            decision = parsed.get("final_decision") or "pending"
            self._apply_parsed(director, {
                "verdict": "support" if decision == "Go" else ("caution" if decision == "Conditional Go" else "risk"),
                "confidence": 0.7,
                "score": parsed.get("quality_score"),
                "checks": _bullets(_find_section(text, "FUNCTIONAL QA")) or _bullets(_find_section(text, "DEPLOYMENT READINESS")),
                "findings": _bullets(_find_section(text, "KNOWN RISKS")),
                "recommendations": _bullets(_find_section(text, "ROLLBACK STRATEGY")),
                "evidence": _bullets(_find_section(text, "ENTERPRISE READINESS")) or _bullets(_find_section(text, "MONITORING STATUS")),
                "report": text,
            })
            director.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            director.status = "failed"
            director.error = _err_text(e)
            logger.warning(f"Release Director failed: {e}")

        self._apply_package(report, data)

    def _confidence_fallback(self, report: ReleaseExcellenceReport) -> list[str]:
        out = []
        for r in report.reports:
            if r.department_id == "release-director":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_package(self, report: ReleaseExcellenceReport, data: dict[str, Any]) -> None:
        report.quality_score = data.get("quality_score")
        report.release_version = (data.get("release_version") or "").strip()
        report.final_decision = data.get("final_decision") or "pending"
        for header, key in _PACKAGE_LIST_SECTIONS.items():
            setattr(report, key, data.get(key) or [])
        for header, key in _PACKAGE_TEXT_SECTIONS.items():
            setattr(report, key, data.get(key) or "")

        # Fill gaps from department reports so the report is never empty.
        all_checks: list[str] = []
        all_findings: list[str] = []
        all_recs: list[str] = []
        scores: list[int] = []
        by_dept: dict[str, QualityDepartmentReport] = {}
        for r in report.reports:
            if r.department_id == "release-director":
                continue
            by_dept[r.department_id] = r
            all_checks.extend(r.checks)
            all_findings.extend(r.findings)
            all_recs.extend(r.recommendations)
            if r.score is not None:
                scores.append(r.score)

        dept_section_map = {
            "functional-qa": "functional_qa",
            "performance-engineering": "performance_review",
            "security-review": "security_review",
            "privacy-compliance": "compliance_review",
            "accessibility-validation": "accessibility_review",
            "documentation-knowledge": "documentation_status",
            "architecture-review": "architecture_review",
            "production-monitoring": "monitoring_status",
            "enterprise-readiness": "enterprise_readiness",
        }
        for dept_id, key in dept_section_map.items():
            if not getattr(report, key):
                dept = by_dept.get(dept_id)
                if dept and dept.status == "completed":
                    setattr(report, key, _dedupe(dept.checks or dept.findings)[:10])

        if not report.deployment_readiness:
            ops = [d for d in (by_dept.get("release-readiness"), by_dept.get("devops-quality")) if d and d.status == "completed"]
            report.deployment_readiness = _dedupe(
                [c for d in ops for c in (d.checks + d.recommendations)]
            )[:10]
        if not report.known_risks:
            report.known_risks = _dedupe(all_findings)[:10]
        if not report.rollback_strategy:
            ops = [d for d in (by_dept.get("release-readiness"), by_dept.get("devops-quality"), by_dept.get("incident-prevention")) if d and d.status == "completed"]
            report.rollback_strategy = _dedupe(
                [c for d in ops for c in (d.recommendations + d.checks)]
            )[:8]

        if report.quality_score is None and scores:
            report.quality_score = round(mean(scores))
        if report.quality_score is None:
            report.quality_score = 50
        if report.final_decision in ("", "pending"):
            report.final_decision = _decision_from_score(report.quality_score)
        if not report.release_version:
            m = re.search(r"\bv?\d+\.\d+(?:\.\d+)?\b", report.request)
            report.release_version = m.group(0) if m else "v1.0.0"
        if not report.release_certificate:
            if report.final_decision == "Go":
                fixes = "- No required fixes."
            else:
                fixes = "\n".join(f"- {r}" for r in (report.known_risks or ["None identified."])[:5])
            report.release_certificate = (
                f"## Release Version\n{report.release_version}\n\n"
                f"## Final Decision\n{report.final_decision}\n\n"
                f"## Required Fixes\n{fixes}\n\n"
                f"## Conditions\n- See the Known Risks and department reports for the "
                f"conditions attached to this release.\n\n"
                f"## Sign-off\nQuality, Security & Release Excellence Division - Release Director"
            )
        if not report.executive_summary:
            done = sum(1 for r in report.reports if r.status == "completed")
            report.executive_summary = (
                f"Release Excellence Report completed across {done} of {len(QUALITY_DEPARTMENTS_LIST)} departments. "
                f"Overall quality score: {report.quality_score}/100. Final decision: {report.final_decision}. "
                f"See the department reports and the release certificate for what must "
                f"be fixed before production."
            )

    def _finalize(self, report: ReleaseExcellenceReport) -> None:
        done = [r for r in report.reports if r.status == "completed" and r.department_id != "release-director"]
        if not done:
            report.status = "failed"
            report.error = "No quality departments completed (LLM unavailable)"
        if done:
            report.avg_confidence = round(mean(r.confidence for r in done), 2)
        report.total_checks = sum(len(r.checks) for r in done)
        report.total_findings = sum(len(r.findings) for r in done)
        report.report_markdown = _report_markdown(report.model_dump())
