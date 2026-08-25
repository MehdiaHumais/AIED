"""Layer 6 - Growth, Conversion & Customer Success Division (GCCSD). Growth engine.

Runs a growth subject through the eleven growth departments, the Growth
Director merges their findings into one Growth Intelligence Report plus an
implementation-ready specification for the Frontend and Backend Development
Agents, and the report is persisted to ``data/growth/reviews.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the report still completes using whatever findings were gathered.
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

from growth.models import GrowthDepartmentReport, GrowthReviewPackage
from growth.prompts import (
    GROWTH_DEPARTMENTS,
    GROWTH_DEPARTMENTS_LIST,
    GROWTH_ORDER,
    SUBJECT_TYPES,
    build_department_request_prompt,
    build_director_prompt,
    get_growth_department_prompt,
)

logger = logging.getLogger(__name__)

_GROWTH_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "growth")
_GROWTH_DATA_FILE = os.path.join(_GROWTH_DATA_DIR, "reviews.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEPARTMENT_TIMEOUT = 240
_DIRECTOR_TIMEOUT = 300

_STRICT_FORMAT_REMINDER = (
    "\n\nIMPORTANT: your previous reply did not follow the required format. "
    "Reply AGAIN using EXACTLY these headings, one per line: "
    "## VERDICT: <support|recommend|caution|risk>, ## CONFIDENCE: <0.0-1.0>, "
    "## SCORE: <0-100>, ## METRICS, ## OPPORTUNITIES, ## FINDINGS, "
    "## RECOMMENDATIONS, ## EVIDENCE. Put at least one bullet under METRICS, "
    "OPPORTUNITIES, FINDINGS, and RECOMMENDATIONS."
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
    one of the given stop headers. Used for sections like the Implementation
    Specification whose body itself contains '##' headings."""
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

    metrics = _bullets(_find_section(text, "METRICS"))
    opportunities = _bullets(_find_section(text, "OPPORTUNITIES"))
    findings = _bullets(_find_section(text, "FINDINGS"))
    recommendations = _bullets(_find_section(text, "RECOMMENDATIONS"))
    evidence = _bullets(_find_section(text, "EVIDENCE"))
    return {
        "verdict": verdict,
        "confidence": confidence,
        "score": score,
        "metrics": metrics,
        "opportunities": opportunities,
        "findings": findings,
        "recommendations": recommendations,
        "evidence": evidence,
        "report": text,
    }


def _salvage_department_text(text: str) -> dict[str, Any]:
    """Salvage a non-empty but off-format reply instead of failing the department.

    Keeps the raw text as the report (the Growth Director still reads it) and
    extracts usable bullet points as opportunities so the department counts as done.
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
        "metrics": [],
        "opportunities": lines[:10],
        "findings": lines[:10],
        "recommendations": [],
        "evidence": [],
        "report": text,
    }


_PACKAGE_LIST_SECTIONS = {
    "Conversion Analysis": "conversion_analysis",
    "Landing Page Audit": "landing_page_audit",
    "Acquisition Opportunities": "acquisition_opportunities",
    "Activation Improvements": "activation_improvements",
    "Retention Strategy": "retention_strategy",
    "Pricing Recommendations": "pricing_recommendations",
    "Customer Success Insights": "customer_success_insights",
    "Customer Feedback Summary": "customer_feedback_summary",
    "Analytics Findings": "analytics_findings",
    "Experiment Recommendations": "experiment_recommendations",
    "Trust & Credibility Assessment": "trust_credibility_assessment",
    "Quick Wins": "quick_wins",
    "High Impact Projects": "high_impact_projects",
    "Estimated Business Impact": "estimated_business_impact",
}

_PACKAGE_TEXT_SECTIONS = {
    "Implementation Specification": "implementation_specification",
    "Executive Summary": "executive_summary",
}


def _parse_package(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _PACKAGE_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _PACKAGE_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The Implementation Specification body contains its own ## sub-headers
    # (Project, Objective, Changes, Acceptance Criteria), so parse it with a
    # dedicated extractor that runs until the Executive Summary.
    data["implementation_specification"] = _find_section_until(text, "Implementation Specification", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Overall Growth Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["growth_score"] = score
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


def _package_markdown(p: dict[str, Any]) -> str:
    lines = ["# Growth, Conversion & Customer Success Division - Growth Intelligence Report"]
    lines.append("")
    if p.get("growth_score") is not None:
        lines.append(f"**Overall Growth Score:** {p['growth_score']}/100")
    for label, key in _PACKAGE_LIST_SECTIONS.items():
        values = p.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if p.get("implementation_specification"):
        lines.append("")
        lines.append("## Implementation Specification")
        lines.append(p["implementation_specification"])
    if p.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(p["executive_summary"])
    return "\n".join(lines)


class GrowthDivision:
    """The Growth, Conversion & Customer Success Division (Layer 6)."""

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
        self.reviews: dict[str, GrowthReviewPackage] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _GROWTH_DATA_FILE
        self._load()

    # --- Persistence ---

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump({"reviews": [p.model_dump() for p in self.reviews.values()]}, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("reviews", []):
                package = GrowthReviewPackage.model_validate(raw)
                self.reviews[package.id] = package
            logger.info(f"Loaded {len(self.reviews)} Growth Intelligence Reports from disk")
        except Exception as e:
            logger.error(f"Failed to load Growth Intelligence Reports: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": GROWTH_DEPARTMENTS[did]["name"],
                "title": GROWTH_DEPARTMENTS[did]["title"],
                "order": GROWTH_ORDER.index(did),
                "is_coordinator": did == "growth-director",
            }
            for did in GROWTH_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [p for p in self.reviews.values() if p.status == "completed"]
        confidences = [p.avg_confidence for p in completed if p.avg_confidence is not None]
        scores = [p.growth_score for p in completed if p.growth_score is not None]
        return {
            "total": len(self.reviews),
            "in_progress": sum(1 for p in self.reviews.values() if p.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for p in self.reviews.values() if p.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_growth_score": round(mean(scores)) if scores else None,
            "total_opportunities": sum(p.total_opportunities for p in completed),
            "total_metrics": sum(p.total_metrics for p in completed),
            "departments": len(GROWTH_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
        }

    def list_reviews(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.reviews.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": p.id,
                "request": p.request[:120],
                "subject_type": p.subject_type,
                "status": p.status,
                "stage": p.stage,
                "created_at": p.created_at,
                "completed_at": p.completed_at,
                "avg_confidence": p.avg_confidence,
                "growth_score": p.growth_score,
                "total_opportunities": p.total_opportunities,
                "total_metrics": p.total_metrics,
                "departments_completed": sum(1 for rep in p.reports if rep.status == "completed"),
                "total_departments": len(p.reports),
                "board_review_id": p.board_review_id,
            })
        return out

    def get_review(self, review_id: str) -> GrowthReviewPackage | None:
        return self.reviews.get(review_id)

    def get_review_dict(self, review_id: str) -> dict[str, Any] | None:
        p = self.reviews.get(review_id)
        return p.model_dump() if p else None

    def delete_review(self, review_id: str) -> bool:
        if review_id not in self.reviews:
            return False
        if review_id in self._running:
            self._running[review_id].cancel()
            del self._running[review_id]
        del self.reviews[review_id]
        self.persist()
        return True

    def board_request_text(self, package: GrowthReviewPackage) -> str:
        """Build a board review request that carries this report's findings."""
        summary = package.executive_summary or "Growth Intelligence Report completed; see the report for details."
        return f"{package.request}\n\n[Growth Intelligence Report from GCCSD review {package.id[:8]}: {summary}]"

    # --- Growth workflow ---

    async def run_review(self, request: str, subject_type: str = "landing_page") -> dict[str, Any]:
        """Run a full growth review in the background. Updates the stored report."""
        review_id = str(uuid.uuid4())
        package = GrowthReviewPackage(id=review_id, request=request, subject_type=subject_type)
        self.reviews[review_id] = package

        task = asyncio.create_task(self._execute(package))
        self._running[review_id] = task
        task.add_done_callback(lambda t: self._running.pop(review_id, None) and None)
        return {"status": "started", "review_id": review_id, "review": package.model_dump()}

    async def run_review_sync(self, request: str, subject_type: str = "landing_page") -> dict[str, Any]:
        """Run a full growth review synchronously (blocks until finished). For tests/CLI."""
        review_id = str(uuid.uuid4())
        package = GrowthReviewPackage(id=review_id, request=request, subject_type=subject_type)
        self.reviews[review_id] = package
        await self._execute(package)
        return package.model_dump()

    async def _execute(self, package: GrowthReviewPackage) -> None:
        try:
            await self._run_departments(package)
            await self._run_director(package)
            self._finalize(package)
            if package.status != "failed":
                package.status = "completed"
            package.stage = "done"
            package.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            package.status = "cancelled"
            package.error = "Growth Intelligence Report cancelled"
        except Exception as e:
            logger.exception("Growth Intelligence Report failed")
            package.status = "failed"
            package.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for growth review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_growth_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> GrowthDepartmentReport:
        dept = GROWTH_DEPARTMENTS[department_id]
        return GrowthDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, package: GrowthReviewPackage) -> None:
        package.stage = "review"

        async def run_one(department_id: str) -> None:
            report = self._report_skeleton(department_id)
            report.started_at = datetime.utcnow().isoformat() + "Z"
            package.reports.append(report)
            dept = GROWTH_DEPARTMENTS[department_id]
            focus = " ".join(dept.get("focus_areas", []))
            try:
                user_prompt = build_department_request_prompt(
                    department_id, package.request, package.subject_type,
                    foundation_block=self._foundation_block(package.request + " " + focus),
                )
                parsed = await self._department_parsed(department_id, user_prompt)
                self._apply_parsed(report, parsed)
                report.completed_at = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                report.status = "failed"
                report.error = _err_text(e)
                logger.warning(f"Growth department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in GROWTH_DEPARTMENTS_LIST:
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
                    logger.warning(f"Growth department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, report: GrowthDepartmentReport, parsed: dict[str, Any]) -> None:
        report.verdict = parsed["verdict"]
        report.confidence = parsed["confidence"]
        report.score = parsed.get("score")
        report.metrics = parsed["metrics"]
        report.opportunities = parsed["opportunities"]
        report.findings = parsed["findings"]
        report.recommendations = parsed["recommendations"]
        report.evidence = parsed["evidence"]
        report.report = parsed["report"]
        report.status = "completed"

    # --- Growth Director + report ---

    async def _run_director(self, package: GrowthReviewPackage) -> None:
        package.stage = "synthesis"
        director = self._report_skeleton("growth-director")
        director.started_at = datetime.utcnow().isoformat() + "Z"
        package.reports.append(director)

        reports = []
        for r in package.reports:
            if r.department_id == "growth-director":
                continue
            header = f"### {r.department_title} ({r.department_id})\n"
            if r.status == "completed":
                body = r.report or r.findings_text()
                reports.append(header + body[:3000])
            else:
                reports.append(header + f"_(department assessment unavailable: {r.error or 'failed'})_")

        data: dict[str, Any] = {}
        try:
            user_prompt = build_director_prompt(
                package.request, reports, package.subject_type,
                foundation_block=self._foundation_block(package.request + " growth", 3),
            )
            text = await self._call_department("growth-director", user_prompt, max_tokens=4000)
            parsed = _parse_package(text)
            self._apply_parsed(director, {
                "verdict": "recommend",
                "confidence": 0.7,
                "score": parsed.get("growth_score"),
                "metrics": _bullets(_find_section(text, "ANALYTICS FINDINGS")) or _bullets(_find_section(text, "ESTIMATED BUSINESS IMPACT")),
                "opportunities": _bullets(_find_section(text, "QUICK WINS")) or _bullets(_find_section(text, "HIGH IMPACT PROJECTS")),
                "findings": _bullets(_find_section(text, "CONVERSION ANALYSIS")),
                "recommendations": _bullets(_find_section(text, "IMPLEMENTATION SPECIFICATION")),
                "evidence": _bullets(_find_section(text, "TRUST & CREDIBILITY ASSESSMENT")),
                "report": text,
            })
            director.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            director.status = "failed"
            director.error = _err_text(e)
            logger.warning(f"Growth Director failed: {e}")

        self._apply_package(package, data)

    def _confidence_fallback(self, package: GrowthReviewPackage) -> list[str]:
        out = []
        for r in package.reports:
            if r.department_id == "growth-director":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_package(self, package: GrowthReviewPackage, data: dict[str, Any]) -> None:
        package.growth_score = data.get("growth_score")
        for header, key in _PACKAGE_LIST_SECTIONS.items():
            setattr(package, key, data.get(key) or [])
        for header, key in _PACKAGE_TEXT_SECTIONS.items():
            setattr(package, key, data.get(key) or "")

        # Fill gaps from department reports so the report is never empty.
        all_opportunities: list[str] = []
        all_metrics: list[str] = []
        all_recs: list[str] = []
        all_findings: list[str] = []
        scores: list[int] = []
        for r in package.reports:
            if r.department_id == "growth-director":
                continue
            all_opportunities.extend(r.opportunities)
            all_metrics.extend(r.metrics)
            all_recs.extend(r.recommendations)
            all_findings.extend(r.findings)
            if r.score is not None:
                scores.append(r.score)

        if not package.quick_wins:
            package.quick_wins = _dedupe(all_opportunities)[:6]
        if not package.conversion_analysis:
            package.conversion_analysis = _dedupe(all_opportunities)[:6]
        if not package.acquisition_opportunities:
            package.acquisition_opportunities = _dedupe(all_opportunities)[:6]
        if not package.analytics_findings:
            package.analytics_findings = _dedupe(all_metrics)[:8]
        if not package.customer_feedback_summary:
            package.customer_feedback_summary = _dedupe(all_findings)[:6]
        if not package.experiment_recommendations:
            package.experiment_recommendations = _dedupe(all_recs)[:5]
        if package.growth_score is None and scores:
            package.growth_score = round(mean(scores))
        if package.growth_score is None:
            package.growth_score = 50
        if not package.implementation_specification:
            changes = package.quick_wins or package.high_impact_projects
            package.implementation_specification = (
                "## Project\nApply the Growth Intelligence Report recommendations.\n\n"
                "## Objective\nIncrease measurable business outcomes across the customer lifecycle.\n\n"
                "## Changes\n" + "\n".join(f"- {c}" for c in changes[:8]) +
                "\n\n## Acceptance Criteria\n- Track the metrics named in the report.\n"
                "- Each change ships responsive, accessible, and instrumented.\n"
                "- The success metrics from the experiment recommendations are measurable."
            )
        if not package.executive_summary:
            done = sum(1 for r in package.reports if r.status == "completed")
            package.executive_summary = (
                f"Growth Intelligence Report completed across {done} of {len(GROWTH_DEPARTMENTS_LIST)} departments. "
                f"Overall growth score: {package.growth_score}/100. See the department "
                f"reports and the implementation specification for what the development agents must build."
            )

    def _finalize(self, package: GrowthReviewPackage) -> None:
        done = [r for r in package.reports if r.status == "completed" and r.department_id != "growth-director"]
        if not done:
            package.status = "failed"
            package.error = "No growth departments completed (LLM unavailable)"
        if done:
            package.avg_confidence = round(mean(r.confidence for r in done), 2)
        package.total_opportunities = sum(len(r.opportunities) for r in done)
        package.total_metrics = sum(len(r.metrics) for r in done)
        package.package_markdown = _package_markdown(package.model_dump())
