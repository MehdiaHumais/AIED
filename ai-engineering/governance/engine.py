"""Layer 9 - Enterprise AI Governance & Orchestration Division (EAGOD). Governance engine.

Runs an enterprise operation request through the twelve operations departments,
the Chief AI Operations Director merges their findings into one Division
Operations Report - required divisions, work packages, agent assignments,
capability matches, arbitration rulings, resource plan, dependency map,
schedule, policy compliance, performance insights, audit trail, operational
alerts, enterprise KPIs, and approvals - plus an Executive Operations Brief for
the CEO, and the report is persisted to ``data/governance/reports.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the report still completes using whatever findings were gathered. If the
Chief AI Operations Director fails, the engine still produces a deterministic
final decision from the department scores - no operation is ever silently
approved.
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

from governance.models import GovernanceDepartmentReport, OperationsReport
from governance.prompts import (
    GOVERNANCE_DEPARTMENTS,
    GOVERNANCE_DEPARTMENTS_LIST,
    GOVERNANCE_ORDER,
    SUBJECT_TYPES,
    build_department_request_prompt,
    build_director_prompt,
    get_governance_department_prompt,
)

logger = logging.getLogger(__name__)

_GOV_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "governance")
_GOV_DATA_FILE = os.path.join(_GOV_DATA_DIR, "reports.json")

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
    one of the given stop headers. Used for sections like the Executive
    Operations Brief whose body may contain multi-line text."""
    m = re.search(
        rf"^##\s*{re.escape(header)}\s*:?\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in stop_headers)})\s*:?\s*$|\Z)",
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _parse_final_decision(text: str) -> str:
    """Parse the Approved / Conditional Approval / Not Approved decision.
    Not Approved must be checked before Approved so its substring doesn't match."""
    section = _find_section(text, "Final Decision")
    if not section:
        for line in text.splitlines():
            if re.search(r"final decision", line, re.IGNORECASE):
                section = line
                break
    low = section.lower()
    if "not approved" in low:
        return "Not Approved"
    if "conditional approval" in low:
        return "Conditional Approval"
    if "approved" in low:
        return "Approved"
    return "pending"


def _decision_from_score(score: Optional[int]) -> str:
    """Deterministic fallback decision when the Chief AI Operations Director is unavailable."""
    if score is None:
        return "Conditional Approval"
    if score >= 60:
        return "Approved"
    if score >= 40:
        return "Conditional Approval"
    return "Not Approved"


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

    Keeps the raw text as the report (the Chief AI Operations Director still
    reads it) and extracts usable bullet points as checks so the department
    counts as done.
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
    "Required Divisions": "required_divisions",
    "Work Packages": "work_packages",
    "Agent Assignments": "agent_assignments",
    "Capability Matches": "capability_matches",
    "Arbitration Rulings": "arbitration_rulings",
    "Resource Plan": "resource_plan",
    "Dependency Map": "dependency_map",
    "Schedule": "schedule",
    "Policy Compliance": "policy_compliance",
    "Performance Insights": "performance_insights",
    "Audit Trail": "audit_trail",
    "Operational Alerts": "operational_alerts",
    "Enterprise KPIs": "enterprise_kpis",
    "Approvals": "approvals",
}

_PACKAGE_TEXT_SECTIONS = {
    "Executive Operations Brief": "operations_brief",
    "Executive Summary": "executive_summary",
}


def _parse_package(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _PACKAGE_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _PACKAGE_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The Executive Operations Brief body may span multiple lines, so parse it
    # with a dedicated extractor that runs until the Executive Summary.
    data["operations_brief"] = _find_section_until(text, "Executive Operations Brief", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Overall Governance Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["governance_score"] = score

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
    lines = ["# Enterprise AI Governance & Orchestration Division - Division Operations Report"]
    lines.append("")
    if p.get("governance_score") is not None:
        lines.append(f"**Overall Governance Score:** {p['governance_score']}/100")
    lines.append(f"**Final Decision:** {p.get('final_decision') or 'pending'}")
    for label, key in _PACKAGE_LIST_SECTIONS.items():
        values = p.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if p.get("operations_brief"):
        lines.append("")
        lines.append("## Executive Operations Brief")
        lines.append(p["operations_brief"])
    if p.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(p["executive_summary"])
    return "\n".join(lines)


class GovernanceDivision:
    """The Enterprise AI Governance & Orchestration Division (Layer 9)."""

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
        self.reports: dict[str, OperationsReport] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _GOV_DATA_FILE
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
                report = OperationsReport.model_validate(raw)
                self.reports[report.id] = report
            logger.info(f"Loaded {len(self.reports)} Division Operations Reports from disk")
        except Exception as e:
            logger.error(f"Failed to load Division Operations Reports: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": GOVERNANCE_DEPARTMENTS[did]["name"],
                "title": GOVERNANCE_DEPARTMENTS[did]["title"],
                "order": GOVERNANCE_ORDER.index(did),
                "is_coordinator": did == "chief-ai-ops-director",
            }
            for did in GOVERNANCE_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [p for p in self.reports.values() if p.status == "completed"]
        confidences = [p.avg_confidence for p in completed if p.avg_confidence is not None]
        scores = [p.governance_score for p in completed if p.governance_score is not None]
        decisions = {"approved": 0, "conditional": 0, "not_approved": 0}
        for p in completed:
            d = (p.final_decision or "").lower()
            if d == "approved":
                decisions["approved"] += 1
            elif d == "conditional approval":
                decisions["conditional"] += 1
            elif d == "not approved":
                decisions["not_approved"] += 1
        alerts = sum(len(p.operational_alerts) for p in completed)
        assignments = sum(len(p.agent_assignments) for p in completed)
        org_health = round(mean(scores)) if scores else None
        return {
            "total": len(self.reports),
            "in_progress": sum(1 for p in self.reports.values() if p.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for p in self.reports.values() if p.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_governance_score": org_health,
            "total_checks": sum(p.total_checks for p in completed),
            "total_findings": sum(p.total_findings for p in completed),
            "total_recommendations": sum(p.total_recommendations for p in completed),
            "final_decisions": decisions,
            "departments": len(GOVERNANCE_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
            # Executive operations dashboard metrics (live view for the CEO).
            "organization_health": org_health,
            "projects_active": len(completed),
            "blocked": sum(1 for p in self.reports.values() if p.status in ("in_progress", "failed")),
            "releases_this_week": decisions["approved"],
            "critical_risks": alerts,
            "agents_online": assignments,
            "avg_utilization": None,
            "avg_task_completion": None,
            "quality_score": org_health,
            "customer_satisfaction": None,
            "infrastructure_status": "Attention" if alerts else "Healthy",
            "executive_alerts": alerts,
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
                "governance_score": p.governance_score,
                "final_decision": p.final_decision,
                "total_checks": p.total_checks,
                "total_findings": p.total_findings,
                "total_recommendations": p.total_recommendations,
                "alerts": len(p.operational_alerts),
                "departments_completed": sum(1 for rep in p.reports if rep.status == "completed"),
                "total_departments": len(p.reports),
                "board_review_id": p.board_review_id,
            })
        return out

    def get_report(self, report_id: str) -> OperationsReport | None:
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

    def board_request_text(self, report: OperationsReport) -> str:
        """Build a board review request that carries this report's operations plan."""
        summary = report.executive_summary or "Division Operations Report completed; see the report for details."
        return (
            f"{report.request}\n\n"
            f"[Division Operations Report from EAGOD report {report.id[:8]}: final decision "
            f"{report.final_decision} - {summary}]"
        )

    # --- Governance workflow ---

    async def run_review(self, request: str, subject_type: str = "operation") -> dict[str, Any]:
        """Run a full operations review in the background. Updates the stored report."""
        report_id = str(uuid.uuid4())
        report = OperationsReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report

        task = asyncio.create_task(self._execute(report))
        self._running[report_id] = task
        task.add_done_callback(lambda t: self._running.pop(report_id, None) and None)
        return {"status": "started", "report_id": report_id, "report": report.model_dump()}

    async def run_review_sync(self, request: str, subject_type: str = "operation") -> dict[str, Any]:
        """Run a full operations review synchronously (blocks until finished). For tests/CLI."""
        report_id = str(uuid.uuid4())
        report = OperationsReport(id=report_id, request=request, subject_type=subject_type)
        self.reports[report_id] = report
        await self._execute(report)
        return report.model_dump()

    async def _execute(self, report: OperationsReport) -> None:
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
            report.error = "Division Operations Report cancelled"
        except Exception as e:
            logger.exception("Division Operations Report failed")
            report.status = "failed"
            report.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for governance review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_governance_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> GovernanceDepartmentReport:
        dept = GOVERNANCE_DEPARTMENTS[department_id]
        return GovernanceDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, report: OperationsReport) -> None:
        report.stage = "review"

        async def run_one(department_id: str) -> None:
            dept_report = self._report_skeleton(department_id)
            dept_report.started_at = datetime.utcnow().isoformat() + "Z"
            report.reports.append(dept_report)
            dept = GOVERNANCE_DEPARTMENTS[department_id]
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
                logger.warning(f"Governance department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in GOVERNANCE_DEPARTMENTS_LIST:
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
                    logger.warning(f"Governance department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, dept_report: GovernanceDepartmentReport, parsed: dict[str, Any]) -> None:
        dept_report.verdict = parsed["verdict"]
        dept_report.confidence = parsed["confidence"]
        dept_report.score = parsed.get("score")
        dept_report.checks = parsed["checks"]
        dept_report.findings = parsed["findings"]
        dept_report.recommendations = parsed["recommendations"]
        dept_report.evidence = parsed["evidence"]
        dept_report.report = parsed["report"]
        dept_report.status = "completed"

    # --- Chief AI Operations Director + report ---

    async def _run_director(self, report: OperationsReport) -> None:
        report.stage = "synthesis"
        director = self._report_skeleton("chief-ai-ops-director")
        director.started_at = datetime.utcnow().isoformat() + "Z"
        report.reports.append(director)

        dept_reports = []
        for r in report.reports:
            if r.department_id == "chief-ai-ops-director":
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
                foundation_block=self._foundation_block(report.request + " governance policy orchestration", 3),
            )
            text = await self._call_department("chief-ai-ops-director", user_prompt, max_tokens=4000)
            parsed = _parse_package(text)
            decision = parsed.get("final_decision") or "pending"
            self._apply_parsed(director, {
                "verdict": "support" if decision == "Approved" else ("caution" if decision == "Conditional Approval" else "risk"),
                "confidence": 0.7,
                "score": parsed.get("governance_score"),
                "checks": _bullets(_find_section(text, "REQUIRED DIVISIONS")) or _bullets(_find_section(text, "DEPENDENCY MAP")),
                "findings": _bullets(_find_section(text, "OPERATIONAL ALERTS")),
                "recommendations": _bullets(_find_section(text, "APPROVALS")),
                "evidence": _bullets(_find_section(text, "AUDIT TRAIL")) or _bullets(_find_section(text, "POLICY COMPLIANCE")),
                "report": text,
            })
            director.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            director.status = "failed"
            director.error = _err_text(e)
            logger.warning(f"Chief AI Operations Director failed: {e}")

        self._apply_package(report, data)

    def _confidence_fallback(self, report: OperationsReport) -> list[str]:
        out = []
        for r in report.reports:
            if r.department_id == "chief-ai-ops-director":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_package(self, report: OperationsReport, data: dict[str, Any]) -> None:
        report.governance_score = data.get("governance_score")
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
        by_dept: dict[str, GovernanceDepartmentReport] = {}
        for r in report.reports:
            if r.department_id == "chief-ai-ops-director":
                continue
            by_dept[r.department_id] = r
            all_checks.extend(r.checks)
            all_findings.extend(r.findings)
            all_recs.extend(r.recommendations)
            if r.score is not None:
                scores.append(r.score)

        dept_section_map = {
            "workflow-orchestrator": "required_divisions",
            "task-distribution": "work_packages",
            "capability-discovery": "capability_matches",
            "decision-arbitration": "arbitration_rulings",
            "resource-management": "resource_plan",
            "dependency-manager": "dependency_map",
            "workflow-scheduler": "schedule",
            "policy-governance": "policy_compliance",
            "performance-office": "performance_insights",
            "audit-office": "audit_trail",
            "executive-operations": "operational_alerts",
        }
        for dept_id, key in dept_section_map.items():
            if not getattr(report, key):
                dept = by_dept.get(dept_id)
                if dept and dept.status == "completed":
                    setattr(report, key, _dedupe(dept.checks or dept.findings)[:10])

        if not report.agent_assignments:
            ops = [d for d in (by_dept.get("task-distribution"), by_dept.get("capability-discovery")) if d and d.status == "completed"]
            report.agent_assignments = _dedupe(
                [c for d in ops for c in (d.recommendations + d.checks)]
            )[:8]
        if not report.enterprise_kpis:
            ops = [d for d in (by_dept.get("executive-operations"), by_dept.get("resource-management")) if d and d.status == "completed"]
            report.enterprise_kpis = _dedupe(
                [c for d in ops for c in (d.checks + d.findings)]
            )[:8]
        if not report.approvals:
            report.approvals = _dedupe(all_recs)[:6]

        if report.governance_score is None and scores:
            report.governance_score = round(mean(scores))
        if report.governance_score is None:
            report.governance_score = 50
        if report.final_decision in ("", "pending"):
            report.final_decision = _decision_from_score(report.governance_score)

        if not report.operations_brief:
            approved = report.final_decision
            report.operations_brief = (
                f"Organization health {report.governance_score}/100. Decision: {approved}. "
                f"Active workflow '{report.request[:80]}' - "
                f"{sum(1 for r in report.reports if r.status == 'completed')} of "
                f"{len(GOVERNANCE_DEPARTMENTS_LIST)} operations departments reported. "
                f"Top alert: {report.operational_alerts[0] if report.operational_alerts else 'none'}. "
                f"Release pipeline: {report.agent_assignments[0] if report.agent_assignments else 'see report'}."
            )
        if not report.executive_summary:
            done = sum(1 for r in report.reports if r.status == "completed")
            report.executive_summary = (
                f"Division Operations Report completed across {done} of {len(GOVERNANCE_DEPARTMENTS_LIST)} departments. "
                f"Overall governance score: {report.governance_score}/100. Final decision: {report.final_decision}. "
                f"See the required divisions, dependency map, and schedule for how this "
                f"operation is orchestrated - every agent reports here, and no "
                f"department bypasses this layer."
            )

    def _finalize(self, report: OperationsReport) -> None:
        done = [r for r in report.reports if r.status == "completed" and r.department_id != "chief-ai-ops-director"]
        if not done:
            report.status = "failed"
            report.error = "No operations departments completed (LLM unavailable)"
        if done:
            report.avg_confidence = round(mean(r.confidence for r in done), 2)
        report.total_checks = sum(len(r.checks) for r in done)
        report.total_findings = sum(len(r.findings) for r in done)
        report.total_recommendations = sum(len(r.recommendations) for r in done)
        report.report_markdown = _report_markdown(report.model_dump())
