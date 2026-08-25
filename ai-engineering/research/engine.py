"""Layer 3 - Product Research & Discovery Division (PRDD). Research engine.

Runs a product subject through the ten research departments in parallel, the
Research Coordinator merges their findings into one standardized dossier, and
the dossier is persisted to ``data/research/dossiers.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the dossier still completes using whatever evidence was gathered.
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

from research.models import DepartmentReport, ResearchDossier
from research.prompts import (
    RESEARCH_DEPARTMENTS,
    RESEARCH_DEPARTMENTS_LIST,
    RESEARCH_ORDER,
    SUBJECT_TYPES,
    build_coordinator_prompt,
    build_department_request_prompt,
    get_research_department_prompt,
)

logger = logging.getLogger(__name__)

_RESEARCH_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "research")
_RESEARCH_DATA_FILE = os.path.join(_RESEARCH_DATA_DIR, "dossiers.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEPARTMENT_TIMEOUT = 240

_STRICT_FORMAT_REMINDER = (
    "\n\nIMPORTANT: your previous reply did not follow the required format. "
    "Reply AGAIN using EXACTLY these headings, one per line: "
    "## VERDICT: <support|recommend|caution|risk>, ## CONFIDENCE: <0.0-1.0>, "
    "## FINDINGS, ## RECOMMENDATIONS, ## EVIDENCE. Put at least one bullet "
    "under FINDINGS and RECOMMENDATIONS."
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

    findings = _bullets(_find_section(text, "FINDINGS"))
    recommendations = _bullets(_find_section(text, "RECOMMENDATIONS"))
    evidence = _bullets(_find_section(text, "EVIDENCE"))
    return {
        "verdict": verdict,
        "confidence": confidence,
        "findings": findings,
        "recommendations": recommendations,
        "evidence": evidence,
        "report": text,
    }


_DOSSIER_LIST_SECTIONS = {
    "Customer Needs": "customer_needs",
    "Market Insights": "market_insights",
    "Competitor Findings": "competitor_findings",
    "Missing Features": "missing_features",
    "UX Risks": "ux_risks",
    "Growth Opportunities": "growth_opportunities",
    "Security Considerations": "security_considerations",
    "Industry Expectations": "industry_expectations",
    "Pricing Suggestions": "pricing_suggestions",
    "Recommended Priorities": "recommended_priorities",
    "Confidence Levels": "confidence_levels",
    "Evidence Sources": "evidence_sources",
}

_DOSSIER_TEXT_SECTIONS = {
    "Research Summary": "research_summary",
    "Business Objective": "business_objective",
    "Executive Summary": "executive_summary",
}


def _salvage_department_text(text: str) -> dict[str, Any]:
    """Salvage a non-empty but off-format reply instead of failing the department.

    Keeps the raw text as the report (the coordinator still reads it) and
    extracts usable bullet points as findings so the department counts as done.
    """
    lines = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("*-•#").strip()
        if line and len(line) > 3 and not line.lower().startswith(("##", "section", "verdict", "confidence")):
            lines.append(line)
    return {
        "verdict": "caution",
        "confidence": 0.3,
        "findings": lines[:10],
        "recommendations": [],
        "evidence": [],
        "report": text,
    }


def _parse_dossier(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _DOSSIER_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _DOSSIER_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
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


def _dossier_markdown(d: dict[str, Any]) -> str:
    lines = ["# Product Research & Discovery Division - Research Dossier"]
    lines.append("")
    if d.get("research_summary"):
        lines.append(f"**Research Summary:** {d['research_summary']}")
    if d.get("business_objective"):
        lines.append(f"**Business Objective:** {d['business_objective']}")
    for label, key in (
        ("Customer Needs", "customer_needs"),
        ("Market Insights", "market_insights"),
        ("Competitor Findings", "competitor_findings"),
        ("Missing Features", "missing_features"),
        ("UX Risks", "ux_risks"),
        ("Growth Opportunities", "growth_opportunities"),
        ("Security Considerations", "security_considerations"),
        ("Industry Expectations", "industry_expectations"),
        ("Pricing Suggestions", "pricing_suggestions"),
        ("Recommended Priorities", "recommended_priorities"),
        ("Confidence Levels", "confidence_levels"),
        ("Evidence Sources", "evidence_sources"),
    ):
        values = d.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if d.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(d["executive_summary"])
    return "\n".join(lines)


class ResearchDivision:
    """The Product Research & Discovery Division (Layer 3)."""

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
        self.dossiers: dict[str, ResearchDossier] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _RESEARCH_DATA_FILE
        self._load()

    # --- Persistence ---

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump({"dossiers": [d.model_dump() for d in self.dossiers.values()]}, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("dossiers", []):
                dossier = ResearchDossier.model_validate(raw)
                self.dossiers[dossier.id] = dossier
            logger.info(f"Loaded {len(self.dossiers)} research dossiers from disk")
        except Exception as e:
            logger.error(f"Failed to load research dossiers: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": RESEARCH_DEPARTMENTS[did]["name"],
                "title": RESEARCH_DEPARTMENTS[did]["title"],
                "order": RESEARCH_ORDER.index(did),
                "is_coordinator": did == "research-coordinator",
            }
            for did in RESEARCH_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [d for d in self.dossiers.values() if d.status == "completed"]
        confidences = [d.avg_confidence for d in completed if d.avg_confidence is not None]
        return {
            "total": len(self.dossiers),
            "in_progress": sum(1 for d in self.dossiers.values() if d.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for d in self.dossiers.values() if d.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "total_recommendations": sum(d.total_recommendations for d in completed),
            "departments": len(RESEARCH_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
        }

    def list_dossiers(self) -> list[dict[str, Any]]:
        out = []
        for d in sorted(self.dossiers.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": d.id,
                "request": d.request[:120],
                "subject_type": d.subject_type,
                "status": d.status,
                "stage": d.stage,
                "created_at": d.created_at,
                "completed_at": d.completed_at,
                "avg_confidence": d.avg_confidence,
                "total_recommendations": d.total_recommendations,
                "departments_completed": sum(1 for r in d.reports if r.status == "completed"),
                "total_departments": len(d.reports),
                "board_review_id": d.board_review_id,
            })
        return out

    def get_dossier(self, dossier_id: str) -> ResearchDossier | None:
        return self.dossiers.get(dossier_id)

    def get_dossier_dict(self, dossier_id: str) -> dict[str, Any] | None:
        d = self.dossiers.get(dossier_id)
        return d.model_dump() if d else None

    def delete_dossier(self, dossier_id: str) -> bool:
        if dossier_id not in self.dossiers:
            return False
        if dossier_id in self._running:
            self._running[dossier_id].cancel()
            del self._running[dossier_id]
        del self.dossiers[dossier_id]
        self.persist()
        return True

    def board_request_text(self, dossier: ResearchDossier) -> str:
        """Build a board review request that carries this dossier's findings."""
        summary = dossier.research_summary or "Research completed; see dossier for details."
        return f"{dossier.request}\n\n[Evidence from Product Research dossier {dossier.id[:8]}: {summary}]"

    # --- Research workflow ---

    async def run_research(self, request: str, subject_type: str = "new_product") -> dict[str, Any]:
        """Run full research on a subject in the background. Updates the stored dossier."""
        dossier_id = str(uuid.uuid4())
        dossier = ResearchDossier(id=dossier_id, request=request, subject_type=subject_type)
        self.dossiers[dossier_id] = dossier

        task = asyncio.create_task(self._execute(dossier))
        self._running[dossier_id] = task
        task.add_done_callback(lambda t: self._running.pop(dossier_id, None) and None)
        return {"status": "started", "dossier_id": dossier_id, "dossier": dossier.model_dump()}

    async def run_research_sync(self, request: str, subject_type: str = "new_product") -> dict[str, Any]:
        """Run full research synchronously (blocks until finished). For tests/CLI."""
        dossier_id = str(uuid.uuid4())
        dossier = ResearchDossier(id=dossier_id, request=request, subject_type=subject_type)
        self.dossiers[dossier_id] = dossier
        await self._execute(dossier)
        return dossier.model_dump()

    async def _execute(self, dossier: ResearchDossier) -> None:
        try:
            await self._run_departments(dossier)
            await self._run_coordinator(dossier)
            self._finalize(dossier)
            if dossier.status != "failed":
                dossier.status = "completed"
            dossier.stage = "done"
            dossier.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            dossier.status = "cancelled"
            dossier.error = "Research cancelled"
        except Exception as e:
            logger.exception("Research failed")
            dossier.status = "failed"
            dossier.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for research: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_research_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> DepartmentReport:
        dept = RESEARCH_DEPARTMENTS[department_id]
        return DepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, dossier: ResearchDossier) -> None:
        dossier.stage = "research"

        async def run_one(department_id: str) -> None:
            report = self._report_skeleton(department_id)
            report.started_at = datetime.utcnow().isoformat() + "Z"
            dossier.reports.append(report)
            dept = RESEARCH_DEPARTMENTS[department_id]
            focus = " ".join(dept.get("focus_areas", []))
            try:
                user_prompt = build_department_request_prompt(
                    department_id, dossier.request, dossier.subject_type,
                    foundation_block=self._foundation_block(dossier.request + " " + focus),
                )
                parsed = await self._department_parsed(department_id, user_prompt)
                self._apply_parsed(report, parsed)
                report.completed_at = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                report.status = "failed"
                report.error = _err_text(e)
                logger.warning(f"Research department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in RESEARCH_DEPARTMENTS_LIST:
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
                    logger.warning(f"Research department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, report: DepartmentReport, parsed: dict[str, Any]) -> None:
        report.verdict = parsed["verdict"]
        report.confidence = parsed["confidence"]
        report.findings = parsed["findings"]
        report.recommendations = parsed["recommendations"]
        report.evidence = parsed["evidence"]
        report.report = parsed["report"]
        report.status = "completed"

    # --- Coordinator + dossier ---

    async def _run_coordinator(self, dossier: ResearchDossier) -> None:
        dossier.stage = "synthesis"
        coord = self._report_skeleton("research-coordinator")
        coord.started_at = datetime.utcnow().isoformat() + "Z"
        dossier.reports.append(coord)

        reports = []
        for r in dossier.reports:
            if r.department_id == "research-coordinator":
                continue
            header = f"### {r.department_title} ({r.department_id})\n"
            if r.status == "completed":
                body = r.report or r.findings_text()
                reports.append(header + body[:3000])
            else:
                reports.append(header + f"_(department research unavailable: {r.error or 'failed'})_")

        data: dict[str, Any] = {}
        try:
            user_prompt = build_coordinator_prompt(
                dossier.request, reports, dossier.subject_type,
                foundation_block=self._foundation_block(dossier.request + " research dossier", 3),
            )
            text = await self._call_department("research-coordinator", user_prompt, max_tokens=4000)
            parsed = _parse_dossier(text)
            self._apply_parsed(coord, {
                "verdict": "recommend",
                "confidence": 0.7,
                "findings": _bullets(_find_section(text, "FINDINGS")),
                "recommendations": _bullets(_find_section(text, "RECOMMENDATIONS")),
                "evidence": _bullets(_find_section(text, "EVIDENCE")),
                "report": text,
            })
            coord.verdict = "recommend"
            coord.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            coord.status = "failed"
            coord.error = _err_text(e)
            logger.warning(f"Research coordinator failed: {e}")

        self._apply_dossier(dossier, data)

    def _confidence_fallback(self, dossier: ResearchDossier) -> list[str]:
        out = []
        for r in dossier.reports:
            if r.department_id == "research-coordinator":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_dossier(self, dossier: ResearchDossier, data: dict[str, Any]) -> None:
        dossier.research_summary = data.get("research_summary") or ""
        dossier.business_objective = data.get("business_objective") or ""
        for header, key in _DOSSIER_LIST_SECTIONS.items():
            setattr(dossier, key, data.get(key) or [])
        dossier.executive_summary = data.get("executive_summary") or ""

        # Fill gaps from department reports so the dossier is never empty.
        if not dossier.missing_features:
            collected: list[str] = []
            for r in dossier.reports:
                collected.extend(r.recommendations)
            dossier.missing_features = _dedupe(collected)[:15]
        if not dossier.evidence_sources:
            sources: list[str] = []
            for r in dossier.reports:
                sources.extend(r.evidence)
            dossier.evidence_sources = _dedupe(sources)[:12]
        if not dossier.confidence_levels:
            dossier.confidence_levels = self._confidence_fallback(dossier)
        if not dossier.research_summary:
            done = sum(1 for r in dossier.reports if r.status == "completed")
            dossier.research_summary = (
                f"Research completed across {done} of {len(RESEARCH_DEPARTMENTS_LIST)} departments. "
                f"See the department reports for full findings."
            )

    def _finalize(self, dossier: ResearchDossier) -> None:
        done = [r for r in dossier.reports if r.status == "completed" and r.department_id != "research-coordinator"]
        if not done:
            dossier.status = "failed"
            dossier.error = "No research departments completed (LLM unavailable)"
        if done:
            dossier.avg_confidence = round(mean(r.confidence for r in done), 2)
        dossier.total_recommendations = sum(len(r.recommendations) for r in done)
        dossier.dossier_markdown = _dossier_markdown(dossier.model_dump())
