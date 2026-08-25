"""Layer 8 - Intelligence, Learning & Continuous Improvement Division (ILCID). Intelligence engine.

Runs a learning subject through the eleven intelligence departments, the
Intelligence Director merges their findings into one Project Intelligence
Report (organizational memory) plus an organization-wide knowledge graph, and
the report is persisted to ``data/intelligence/reports.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the report still completes using whatever findings were gathered. If the
Intelligence Director fails, the engine still produces a deterministic
knowledge graph from the department findings so the learning loop never stops.
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

from intelligence.models import IntelligenceDepartmentReport, IntelligenceReport
from intelligence.prompts import (
    INTELLIGENCE_DEPARTMENTS,
    INTELLIGENCE_DEPARTMENTS_LIST,
    INTELLIGENCE_ORDER,
    SUBJECT_TYPES,
    build_department_request_prompt,
    build_director_prompt,
    get_intelligence_department_prompt,
)

logger = logging.getLogger(__name__)

_INTEL_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "intelligence")
_INTEL_DATA_FILE = os.path.join(_INTEL_DATA_DIR, "reports.json")

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
    one of the given stop headers. Used for sections like the Knowledge Graph
    whose body itself contains relationship lines."""
    m = re.search(
        rf"^##\s*{re.escape(header)}\s*:?\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in stop_headers)})\s*:?\s*$|\Z)",
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


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

    Keeps the raw text as the report (the Intelligence Director still reads it)
    and extracts usable bullet points as checks so the department counts as done.
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
    "Project Summary": "project_summary",
    "Objectives Achieved": "objectives_achieved",
    "Customer Impact": "customer_impact",
    "Business Impact": "business_impact",
    "Feature Adoption": "feature_adoption",
    "Support Trends": "support_trends",
    "Performance": "performance",
    "Security": "security",
    "UX Outcomes": "ux_outcomes",
    "Growth Outcomes": "growth_outcomes",
    "Lessons Learned": "lessons_learned",
    "Process Improvements": "process_improvements",
    "Updated Standards": "updated_standards",
    "Future Recommendations": "future_recommendations",
    "Confidence Levels": "confidence_levels",
}

_PACKAGE_TEXT_SECTIONS = {
    "Knowledge Graph": "knowledge_graph",
    "Executive Summary": "executive_summary",
}


def _parse_package(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _PACKAGE_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _PACKAGE_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The Knowledge Graph body contains its own relationship lines, so parse it
    # with a dedicated extractor that runs until the Executive Summary.
    data["knowledge_graph"] = _find_section_until(text, "Knowledge Graph", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Overall Intelligence Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["intelligence_score"] = score
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
    lines = ["# Intelligence, Learning & Continuous Improvement Division - Project Intelligence Report"]
    lines.append("")
    if p.get("intelligence_score") is not None:
        lines.append(f"**Overall Intelligence Score:** {p['intelligence_score']}/100")
    for label, key in _PACKAGE_LIST_SECTIONS.items():
        values = p.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if p.get("knowledge_graph"):
        lines.append("")
        lines.append("## Knowledge Graph")
        lines.append(p["knowledge_graph"])
    if p.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(p["executive_summary"])
    return "\n".join(lines)


class IntelligenceDivision:
    """The Intelligence, Learning & Continuous Improvement Division (Layer 8)."""

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
        self.reports: dict[str, IntelligenceReport] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _INTEL_DATA_FILE
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
                report = IntelligenceReport.model_validate(raw)
                self.reports[report.id] = report
            logger.info(f"Loaded {len(self.reports)} Project Intelligence Reports from disk")
        except Exception as e:
            logger.error(f"Failed to load Project Intelligence Reports: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": INTELLIGENCE_DEPARTMENTS[did]["name"],
                "title": INTELLIGENCE_DEPARTMENTS[did]["title"],
                "order": INTELLIGENCE_ORDER.index(did),
                "is_coordinator": did == "intelligence-director",
            }
            for did in INTELLIGENCE_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [p for p in self.reports.values() if p.status == "completed"]
        confidences = [p.avg_confidence for p in completed if p.avg_confidence is not None]
        scores = [p.intelligence_score for p in completed if p.intelligence_score is not None]
        return {
            "total": len(self.reports),
            "in_progress": sum(1 for p in self.reports.values() if p.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for p in self.reports.values() if p.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_intelligence_score": round(mean(scores)) if scores else None,
            "total_lessons": sum(p.total_lessons for p in completed),
            "total_recommendations": sum(p.total_recommendations for p in completed),
            "total_standards": sum(p.total_standards for p in completed),
            "departments": len(INTELLIGENCE_DEPARTMENTS_LIST),
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
                "intelligence_score": p.intelligence_score,
                "total_lessons": p.total_lessons,
                "total_recommendations": p.total_recommendations,
                "total_standards": p.total_standards,
                "departments_completed": sum(1 for rep in p.reports if rep.status == "completed"),
                "total_departments": len(p.reports),
                "board_review_id": p.board_review_id,
            })
        return out

    def get_report(self, report_id: str) -> IntelligenceReport | None:
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

    def board_request_text(self, report: IntelligenceReport) -> str:
        """Build a board review request that carries this report's learning."""
        summary = report.executive_summary or "Project Intelligence Report completed; see the report for details."
        return (
            f"{report.request}\n\n"
            f"[Project Intelligence Report from ILCID report {report.id[:8]}: {summary}]"
        )

    # --- Learning workflow ---

    async def run_review(self, request: str, subject_type: str = "project") -> dict[str, Any]:
        """Run a full intelligence review in the background. Updates the stored report."""
        report_id = str(uuid.uuid4())
        report = IntelligenceReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report

        task = asyncio.create_task(self._execute(report))
        self._running[report_id] = task
        task.add_done_callback(lambda t: self._running.pop(report_id, None) and None)
        return {"status": "started", "report_id": report_id, "report": report.model_dump()}

    async def run_review_sync(self, request: str, subject_type: str = "project") -> dict[str, Any]:
        """Run a full intelligence review synchronously (blocks until finished). For tests/CLI."""
        report_id = str(uuid.uuid4())
        report = IntelligenceReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report
        await self._execute(report)
        return report.model_dump()

    async def _execute(self, report: IntelligenceReport) -> None:
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
            report.error = "Project Intelligence Report cancelled"
        except Exception as e:
            logger.exception("Project Intelligence Report failed")
            report.status = "failed"
            report.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for intelligence review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_intelligence_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> IntelligenceDepartmentReport:
        dept = INTELLIGENCE_DEPARTMENTS[department_id]
        return IntelligenceDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, report: IntelligenceReport) -> None:
        report.stage = "review"

        async def run_one(department_id: str) -> None:
            dept_report = self._report_skeleton(department_id)
            dept_report.started_at = datetime.utcnow().isoformat() + "Z"
            report.reports.append(dept_report)
            dept = INTELLIGENCE_DEPARTMENTS[department_id]
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
                logger.warning(f"Intelligence department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in INTELLIGENCE_DEPARTMENTS_LIST:
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
                    logger.warning(f"Intelligence department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, dept_report: IntelligenceDepartmentReport, parsed: dict[str, Any]) -> None:
        dept_report.verdict = parsed["verdict"]
        dept_report.confidence = parsed["confidence"]
        dept_report.score = parsed.get("score")
        dept_report.checks = parsed["checks"]
        dept_report.findings = parsed["findings"]
        dept_report.recommendations = parsed["recommendations"]
        dept_report.evidence = parsed["evidence"]
        dept_report.report = parsed["report"]
        dept_report.status = "completed"

    # --- Intelligence Director + report ---

    async def _run_director(self, report: IntelligenceReport) -> None:
        report.stage = "synthesis"
        director = self._report_skeleton("intelligence-director")
        director.started_at = datetime.utcnow().isoformat() + "Z"
        report.reports.append(director)

        dept_reports = []
        for r in report.reports:
            if r.department_id == "intelligence-director":
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
                foundation_block=self._foundation_block(report.request + " intelligence learning standards", 3),
            )
            text = await self._call_department("intelligence-director", user_prompt, max_tokens=4000)
            parsed = _parse_package(text)
            score = parsed.get("intelligence_score")
            self._apply_parsed(director, {
                "verdict": "support" if (score is not None and score >= 70) else ("recommend" if (score is not None and score >= 50) else "caution"),
                "confidence": 0.7,
                "score": score,
                "checks": _bullets(_find_section(text, "PROJECT SUMMARY")) or _bullets(_find_section(text, "OBJECTIVES ACHIEVED")),
                "findings": _bullets(_find_section(text, "LESSONS LEARNED")),
                "recommendations": _bullets(_find_section(text, "FUTURE RECOMMENDATIONS")),
                "evidence": _bullets(_find_section(text, "UPDATED STANDARDS")) or _bullets(_find_section(text, "CONFIDENCE LEVELS")),
                "report": text,
            })
            director.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            director.status = "failed"
            director.error = _err_text(e)
            logger.warning(f"Intelligence Director failed: {e}")

        self._apply_package(report, data)

    def _confidence_fallback(self, report: IntelligenceReport) -> list[str]:
        out = []
        for r in report.reports:
            if r.department_id == "intelligence-director":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_package(self, report: IntelligenceReport, data: dict[str, Any]) -> None:
        report.intelligence_score = data.get("intelligence_score")
        for header, key in _PACKAGE_LIST_SECTIONS.items():
            setattr(report, key, data.get(key) or [])
        for header, key in _PACKAGE_TEXT_SECTIONS.items():
            setattr(report, key, data.get(key) or "")

        # Fill gaps from department reports so the report is never empty.
        all_checks: list[str] = []
        all_findings: list[str] = []
        all_recs: list[str] = []
        scores: list[int] = []
        by_dept: dict[str, IntelligenceDepartmentReport] = {}
        for r in report.reports:
            if r.department_id == "intelligence-director":
                continue
            by_dept[r.department_id] = r
            all_checks.extend(r.checks)
            all_findings.extend(r.findings)
            all_recs.extend(r.recommendations)
            if r.score is not None:
                scores.append(r.score)

        if not report.lessons_learned:
            report.lessons_learned = _dedupe(all_findings)[:10]
        if not report.future_recommendations:
            report.future_recommendations = _dedupe(all_recs)[:10]
        if not report.process_improvements:
            ops = [d for d in (by_dept.get("process-optimization"), by_dept.get("workflow-optimization")) if d and d.status == "completed"]
            report.process_improvements = _dedupe(
                [c for d in ops for c in (d.checks + d.recommendations)]
            )[:8]
        if not report.updated_standards:
            ops = [d for d in (by_dept.get("knowledge-evolution"), by_dept.get("organizational-learning")) if d and d.status == "completed"]
            report.updated_standards = _dedupe(
                [c for d in ops for c in (d.checks + d.recommendations)]
            )[:8]
        if not report.feature_adoption:
            ops = [d for d in (by_dept.get("product-intelligence"), by_dept.get("customer-intelligence")) if d and d.status == "completed"]
            report.feature_adoption = _dedupe(
                [c for d in ops for c in (d.checks + d.findings)]
            )[:8]
        if not report.objectives_achieved:
            report.objectives_achieved = _dedupe(all_checks)[:6]
        if not report.confidence_levels:
            report.confidence_levels = _dedupe(all_checks)[:5]
        if not report.project_summary:
            report.project_summary = [report.request[:200]]

        if report.intelligence_score is None and scores:
            report.intelligence_score = round(mean(scores))
        if report.intelligence_score is None:
            report.intelligence_score = 50

        if not report.knowledge_graph:
            lessons = report.lessons_learned or report.future_recommendations
            lesson_lines = "\n".join(f"- LESSON -> RECOMMENDATION: {l}" for l in lessons[:6])
            rec_lines = "\n".join(f"- RECOMMENDATION -> FUTURE PROJECT: {r}" for r in report.future_recommendations[:4])
            report.knowledge_graph = (
                f"- SUBJECT -> PRODUCT/FEATURE: {report.request[:160]}\n"
                f"- WORKFLOW -> STANDARD: see Updated Standards below\n"
                f"{lesson_lines}\n"
                f"{rec_lines}"
            )

        if not report.executive_summary:
            done = sum(1 for r in report.reports if r.status == "completed")
            report.executive_summary = (
                f"Project Intelligence Report completed across {done} of {len(INTELLIGENCE_DEPARTMENTS_LIST)} departments. "
                f"Overall intelligence score: {report.intelligence_score}/100. "
                f"The lessons learned and updated standards make the next project "
                f"better than the last - see the knowledge graph for how this "
                f"subject connects to the rest of the organization."
            )

    def _finalize(self, report: IntelligenceReport) -> None:
        done = [r for r in report.reports if r.status == "completed" and r.department_id != "intelligence-director"]
        if not done:
            report.status = "failed"
            report.error = "No intelligence departments completed (LLM unavailable)"
        if done:
            report.avg_confidence = round(mean(r.confidence for r in done), 2)
        report.total_lessons = sum(len(r.findings) for r in done)
        report.total_recommendations = sum(len(r.recommendations) for r in done)
        report.total_standards = len(report.updated_standards)
        report.report_markdown = _report_markdown(report.model_dump())
