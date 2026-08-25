"""Layer 10 - Enterprise Knowledge & Digital Twin Platform (EKDT). Engine.

Runs an enterprise knowledge subject (a new idea, a project, a customer, a
process, or an enterprise-wide refresh) through the eleven knowledge systems,
the Knowledge Architect merges their updates into one Digital Twin Update
Report - organizational snapshot, product snapshot, customer insights, process
updates, agent insights, decisions logged, knowledge graph links, semantic
answers, proven patterns, detected patterns, predictions, knowledge actions,
and knowledge quality - plus a Knowledge Brief for the CEO, and the report is
persisted to ``data/ekdt/reports.json``.

The engine is resilient: an LLM outage marks individual knowledge systems as
failed and the report still completes using whatever updates were gathered. If
the Knowledge Architect fails, the engine still produces a deterministic
knowledge status from the system scores - no twin update is ever silently
accepted.
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

from ekdt.models import DigitalTwinReport, EkdtDepartmentReport
from ekdt.prompts import (
    EKDT_DEPARTMENTS,
    EKDT_DEPARTMENTS_LIST,
    EKDT_ORDER,
    SUBJECT_TYPES,
    build_architect_prompt,
    build_department_request_prompt,
    get_ekdt_department_prompt,
)

logger = logging.getLogger(__name__)

_EKD_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ekdt")
_EKD_DATA_FILE = os.path.join(_EKD_DATA_DIR, "reports.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEPARTMENT_TIMEOUT = 240
_ARCHITECT_TIMEOUT = 300

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
    one of the given stop headers. Used for sections like the Knowledge Brief
    whose body may contain multi-line text."""
    m = re.search(
        rf"^##\s*{re.escape(header)}\s*:?\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in stop_headers)})\s*:?\s*$|\Z)",
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _parse_knowledge_status(text: str) -> str:
    """Parse the Optimal / Actionable / Stale knowledge status.

    The status value sits on the first line of the section (e.g. "Actionable");
    the rest of the section explains it and may contain other keywords (e.g. "a
    stale pattern"), so the first line is authoritative. The whole section is
    only scanned when no value is on the first line (inline forms).
    """
    section = _find_section(text, "Knowledge Status")
    if not section:
        for line in text.splitlines():
            if re.search(r"knowledge status", line, re.IGNORECASE):
                section = line
                break
    first_line = section.splitlines()[0].strip() if section else ""
    low = first_line.lower()
    if "optimal" in low:
        return "Optimal"
    if "stale" in low:
        return "Stale"
    if "actionable" in low:
        return "Actionable"
    low_all = section.lower()
    if "optimal" in low_all:
        return "Optimal"
    if "stale" in low_all:
        return "Stale"
    if "actionable" in low_all:
        return "Actionable"
    return "pending"


def _status_from_score(score: Optional[int]) -> str:
    """Deterministic fallback knowledge status when the Knowledge Architect is unavailable."""
    if score is None:
        return "Actionable"
    if score >= 70:
        return "Optimal"
    if score >= 50:
        return "Actionable"
    return "Stale"


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
    """Salvage a non-empty but off-format reply instead of failing the system.

    Keeps the raw text as the report (the Knowledge Architect still reads it)
    and extracts usable bullet points as checks so the system counts as done.
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


_TWIN_LIST_SECTIONS = {
    "Organizational Twin Snapshot": "org_snapshot",
    "Product Twin Snapshot": "product_snapshot",
    "Customer Twin Insights": "customer_insights",
    "Process Twin Updates": "process_updates",
    "AI Agent Twin Insights": "agent_insights",
    "Decisions Logged": "decisions_logged",
    "Knowledge Graph Links": "knowledge_links",
    "Semantic Answers": "semantic_answers",
    "Proven Patterns": "proven_patterns",
    "Detected Patterns": "detected_patterns",
    "Predictions": "predictions",
    "Knowledge Actions": "knowledge_actions",
    "Knowledge Quality": "knowledge_quality",
}

_TWIN_TEXT_SECTIONS = {
    "Knowledge Brief": "knowledge_brief",
    "Executive Summary": "executive_summary",
}


def _parse_twin_package(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _TWIN_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _TWIN_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The Knowledge Brief body may span multiple lines, so parse it with a
    # dedicated extractor that runs until the Executive Summary.
    data["knowledge_brief"] = _find_section_until(text, "Knowledge Brief", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Overall Knowledge Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["knowledge_score"] = score

    data["knowledge_status"] = _parse_knowledge_status(text)
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
    lines = ["# Enterprise Knowledge & Digital Twin Platform - Digital Twin Update Report"]
    lines.append("")
    if p.get("knowledge_score") is not None:
        lines.append(f"**Overall Knowledge Score:** {p['knowledge_score']}/100")
    lines.append(f"**Knowledge Status:** {p.get('knowledge_status') or 'pending'}")
    for label, key in _TWIN_LIST_SECTIONS.items():
        values = p.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if p.get("knowledge_brief"):
        lines.append("")
        lines.append("## Knowledge Brief")
        lines.append(p["knowledge_brief"])
    if p.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(p["executive_summary"])
    return "\n".join(lines)


class EkdtDivision:
    """The Enterprise Knowledge & Digital Twin Platform (Layer 10)."""

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
        self.reports: dict[str, DigitalTwinReport] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _EKD_DATA_FILE
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
                report = DigitalTwinReport.model_validate(raw)
                self.reports[report.id] = report
            logger.info(f"Loaded {len(self.reports)} Digital Twin Update Reports from disk")
        except Exception as e:
            logger.error(f"Failed to load Digital Twin Update Reports: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": EKDT_DEPARTMENTS[did]["name"],
                "title": EKDT_DEPARTMENTS[did]["title"],
                "order": EKDT_ORDER.index(did),
                "is_coordinator": did == "knowledge-architect",
            }
            for did in EKDT_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [p for p in self.reports.values() if p.status == "completed"]
        confidences = [p.avg_confidence for p in completed if p.avg_confidence is not None]
        scores = [p.knowledge_score for p in completed if p.knowledge_score is not None]
        statuses = {"optimal": 0, "actionable": 0, "stale": 0}
        for p in completed:
            s = (p.knowledge_status or "").lower()
            if s == "optimal":
                statuses["optimal"] += 1
            elif s == "stale":
                statuses["stale"] += 1
            elif s == "actionable":
                statuses["actionable"] += 1
        stale = statuses["stale"]
        # The Enterprise Intelligence Dashboard: a live view of the whole twin.
        return {
            "total": len(self.reports),
            "in_progress": sum(1 for p in self.reports.values() if p.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for p in self.reports.values() if p.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_knowledge_score": round(mean(scores)) if scores else None,
            "total_checks": sum(p.total_checks for p in completed),
            "total_findings": sum(p.total_findings for p in completed),
            "total_recommendations": sum(p.total_recommendations for p in completed),
            "knowledge_statuses": statuses,
            "departments": len(EKDT_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
            # Enterprise Intelligence Dashboard metrics (the CEO view).
            "organizations": sum(len(p.org_snapshot) for p in completed),
            "active_products": sum(1 for p in completed if p.product_snapshot),
            "ai_agents": sum(len(p.agent_insights) for p in completed),
            "knowledge_items": sum(p.total_checks + p.total_findings for p in completed),
            "successful_patterns": sum(len(p.proven_patterns) for p in completed),
            "decisions_stored": sum(len(p.decisions_logged) for p in completed),
            "active_projects": len(completed),
            "predictive_alerts": sum(len(p.predictions) for p in completed),
            "learning_updates": sum(p.total_recommendations for p in completed),
            "knowledge_links": sum(len(p.knowledge_links) for p in completed),
            "semantic_answers": sum(len(p.semantic_answers) for p in completed),
            "knowledge_health": round(mean(scores)) if scores else None,
            "twin_status": "Attention" if stale else "Healthy",
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
                "knowledge_score": p.knowledge_score,
                "knowledge_status": p.knowledge_status,
                "total_checks": p.total_checks,
                "total_findings": p.total_findings,
                "total_recommendations": p.total_recommendations,
                "predictions": len(p.predictions),
                "patterns": len(p.proven_patterns),
                "decisions": len(p.decisions_logged),
                "departments_completed": sum(1 for rep in p.reports if rep.status == "completed"),
                "total_departments": len(p.reports),
                "board_review_id": p.board_review_id,
            })
        return out

    def get_report(self, report_id: str) -> DigitalTwinReport | None:
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

    def board_request_text(self, report: DigitalTwinReport) -> str:
        """Build a board review request that carries this report's twin update."""
        summary = report.executive_summary or "Digital Twin Update Report completed; see the report for details."
        return (
            f"{report.request}\n\n"
            f"[Digital Twin Update Report from EKDT report {report.id[:8]}: knowledge status "
            f"{report.knowledge_status} - {summary}]"
        )

    # --- Knowledge workflow ---

    async def run_review(self, request: str, subject_type: str = "idea") -> dict[str, Any]:
        """Run a full knowledge update in the background. Updates the stored report."""
        report_id = str(uuid.uuid4())
        report = DigitalTwinReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report

        task = asyncio.create_task(self._execute(report))
        self._running[report_id] = task
        task.add_done_callback(lambda t: self._running.pop(report_id, None) and None)
        return {"status": "started", "report_id": report_id, "report": report.model_dump()}

    async def run_review_sync(self, request: str, subject_type: str = "idea") -> dict[str, Any]:
        """Run a full knowledge update synchronously (blocks until finished). For tests/CLI."""
        report_id = str(uuid.uuid4())
        report = DigitalTwinReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report
        await self._execute(report)
        return report.model_dump()

    async def _execute(self, report: DigitalTwinReport) -> None:
        try:
            await self._run_departments(report)
            await self._run_architect(report)
            self._finalize(report)
            if report.status != "failed":
                report.status = "completed"
            report.stage = "done"
            report.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            report.status = "cancelled"
            report.error = "Digital Twin Update Report cancelled"
        except Exception as e:
            logger.exception("Digital Twin Update Report failed")
            report.status = "failed"
            report.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for EKDT review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_ekdt_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> EkdtDepartmentReport:
        dept = EKDT_DEPARTMENTS[department_id]
        return EkdtDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, report: DigitalTwinReport) -> None:
        report.stage = "review"

        async def run_one(department_id: str) -> None:
            dept_report = self._report_skeleton(department_id)
            dept_report.started_at = datetime.utcnow().isoformat() + "Z"
            report.reports.append(dept_report)
            dept = EKDT_DEPARTMENTS[department_id]
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
                logger.warning(f"EKDT knowledge system {department_id} failed: {e}")

        # The LLM manager serializes all requests, so knowledge systems run one
        # at a time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in EKDT_DEPARTMENTS_LIST:
            await run_one(department_id)

    async def _department_parsed(self, department_id: str, user_prompt: str) -> dict[str, Any]:
        """Call a knowledge system, retrying once on transient failures / empty
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
                    logger.warning(f"EKDT knowledge system {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, dept_report: EkdtDepartmentReport, parsed: dict[str, Any]) -> None:
        dept_report.verdict = parsed["verdict"]
        dept_report.confidence = parsed["confidence"]
        dept_report.score = parsed.get("score")
        dept_report.checks = parsed["checks"]
        dept_report.findings = parsed["findings"]
        dept_report.recommendations = parsed["recommendations"]
        dept_report.evidence = parsed["evidence"]
        dept_report.report = parsed["report"]
        dept_report.status = "completed"

    # --- Knowledge Architect + report ---

    async def _run_architect(self, report: DigitalTwinReport) -> None:
        report.stage = "synthesis"
        architect = self._report_skeleton("knowledge-architect")
        architect.started_at = datetime.utcnow().isoformat() + "Z"
        report.reports.append(architect)

        system_reports = []
        for r in report.reports:
            if r.department_id == "knowledge-architect":
                continue
            header = f"### {r.department_title} ({r.department_id})\n"
            if r.status == "completed":
                body = r.report or r.findings_text()
                system_reports.append(header + body[:3000])
            else:
                system_reports.append(header + f"_(knowledge system unavailable: {r.error or 'failed'})_")

        data: dict[str, Any] = {}
        try:
            user_prompt = build_architect_prompt(
                report.request, system_reports, report.subject_type,
                foundation_block=self._foundation_block(report.request + " knowledge architecture quality", 3),
            )
            text = await self._call_department("knowledge-architect", user_prompt, max_tokens=4000)
            parsed = _parse_twin_package(text)
            status = parsed.get("knowledge_status") or "pending"
            self._apply_parsed(architect, {
                "verdict": "support" if status == "Optimal" else ("caution" if status == "Actionable" else "risk"),
                "confidence": 0.7,
                "score": parsed.get("knowledge_score"),
                "checks": _bullets(_find_section(text, "KNOWLEDGE QUALITY")) or _bullets(_find_section(text, "KNOWLEDGE ACTIONS")),
                "findings": _bullets(_find_section(text, "DETECTED PATTERNS")),
                "recommendations": _bullets(_find_section(text, "KNOWLEDGE ACTIONS")),
                "evidence": _bullets(_find_section(text, "KNOWLEDGE GRAPH LINKS")) or _bullets(_find_section(text, "SEMANTIC ANSWERS")),
                "report": text,
            })
            architect.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            architect.status = "failed"
            architect.error = _err_text(e)
            logger.warning(f"Knowledge Architect failed: {e}")

        self._apply_package(report, data)

    def _confidence_fallback(self, report: DigitalTwinReport) -> list[str]:
        out = []
        for r in report.reports:
            if r.department_id == "knowledge-architect":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_package(self, report: DigitalTwinReport, data: dict[str, Any]) -> None:
        report.knowledge_score = data.get("knowledge_score")
        report.knowledge_status = data.get("knowledge_status") or "pending"
        for header, key in _TWIN_LIST_SECTIONS.items():
            setattr(report, key, data.get(key) or [])
        for header, key in _TWIN_TEXT_SECTIONS.items():
            setattr(report, key, data.get(key) or "")

        # Fill gaps from knowledge system reports so the report is never empty.
        all_checks: list[str] = []
        all_findings: list[str] = []
        all_recs: list[str] = []
        scores: list[int] = []
        by_dept: dict[str, EkdtDepartmentReport] = {}
        for r in report.reports:
            if r.department_id == "knowledge-architect":
                continue
            by_dept[r.department_id] = r
            all_checks.extend(r.checks)
            all_findings.extend(r.findings)
            all_recs.extend(r.recommendations)
            if r.score is not None:
                scores.append(r.score)

        dept_section_map = {
            "organizational-twin": "org_snapshot",
            "product-twin": "product_snapshot",
            "customer-twin": "customer_insights",
            "process-twin": "process_updates",
            "agent-twin": "agent_insights",
            "decision-memory": "decisions_logged",
            "knowledge-graph": "knowledge_links",
            "semantic-search": "semantic_answers",
            "experience-repository": "proven_patterns",
            "pattern-recognition": "detected_patterns",
            "predictive-intelligence": "predictions",
        }
        for dept_id, key in dept_section_map.items():
            if not getattr(report, key):
                dept = by_dept.get(dept_id)
                if dept and dept.status == "completed":
                    setattr(report, key, _dedupe(dept.checks or dept.findings)[:10])

        if not report.knowledge_actions:
            report.knowledge_actions = _dedupe(all_recs)[:8]
        if not report.knowledge_quality:
            report.knowledge_quality = _dedupe(all_checks)[:8]

        if report.knowledge_score is None and scores:
            report.knowledge_score = round(mean(scores))
        if report.knowledge_score is None:
            report.knowledge_score = 50
        if report.knowledge_status in ("", "pending"):
            report.knowledge_status = _status_from_score(report.knowledge_score)

        if not report.knowledge_brief:
            report.knowledge_brief = (
                f"Twin health {report.knowledge_score}/100. Status: {report.knowledge_status}. "
                f"Knowledge subject '{report.request[:80]}' enriched across "
                f"{sum(1 for r in report.reports if r.status == 'completed')} of "
                f"{len(EKDT_DEPARTMENTS_LIST)} knowledge systems. "
                f"Top signal: {report.predictions[0] if report.predictions else 'none'}. "
                f"Proven patterns available: {len(report.proven_patterns)}. "
                f"Decisions stored this update: {len(report.decisions_logged)}."
            )
        if not report.executive_summary:
            done = sum(1 for r in report.reports if r.status == "completed")
            report.executive_summary = (
                f"Digital Twin Update Report completed across {done} of {len(EKDT_DEPARTMENTS_LIST)} knowledge systems. "
                f"Overall knowledge score: {report.knowledge_score}/100. Knowledge status: {report.knowledge_status}. "
                f"The platform now remembers why things exist - every decision, pattern, and relationship "
                f"is stored so the next agent starts from what the enterprise already learned, and no "
                f"division works without this context."
            )

    def _finalize(self, report: DigitalTwinReport) -> None:
        done = [r for r in report.reports if r.status == "completed" and r.department_id != "knowledge-architect"]
        if not done:
            report.status = "failed"
            report.error = "No knowledge systems completed (LLM unavailable)"
        if done:
            report.avg_confidence = round(mean(r.confidence for r in done), 2)
        report.total_checks = sum(len(r.checks) for r in done)
        report.total_findings = sum(len(r.findings) for r in done)
        report.total_recommendations = sum(len(r.recommendations) for r in done)
        report.report_markdown = _report_markdown(report.model_dump())
