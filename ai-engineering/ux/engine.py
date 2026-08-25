"""Layer 4 - UX & Human Experience Division (UXHED). UX review engine.

Runs a product surface through the eleven UX departments, the UX Director
merges their findings into one consolidated UX Review Report plus an
implementation-ready specification, and the review is persisted to
``data/ux/reviews.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the review still completes using whatever evidence was gathered.
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

from ux.models import UXDepartmentReport, UXReview
from ux.prompts import (
    UX_DEPARTMENTS,
    UX_DEPARTMENTS_LIST,
    UX_ORDER,
    SUBJECT_TYPES,
    build_department_request_prompt,
    build_director_prompt,
    get_ux_department_prompt,
)

logger = logging.getLogger(__name__)

_UX_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ux")
_UX_DATA_FILE = os.path.join(_UX_DATA_DIR, "reviews.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEPARTMENT_TIMEOUT = 240
_DIRECTOR_TIMEOUT = 300

_STRICT_FORMAT_REMINDER = (
    "\n\nIMPORTANT: your previous reply did not follow the required format. "
    "Reply AGAIN using EXACTLY these headings, one per line: "
    "## VERDICT: <support|recommend|caution|risk>, ## CONFIDENCE: <0.0-1.0>, "
    "## SCORE: <0-100>, ## FINDINGS, ## RECOMMENDATIONS, ## EVIDENCE. Put at "
    "least one bullet under FINDINGS and RECOMMENDATIONS."
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

    score: Optional[int] = None
    score_match = re.search(r"##\s*SCORE\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None

    findings = _bullets(_find_section(text, "FINDINGS"))
    recommendations = _bullets(_find_section(text, "RECOMMENDATIONS"))
    evidence = _bullets(_find_section(text, "EVIDENCE"))
    return {
        "verdict": verdict,
        "confidence": confidence,
        "score": score,
        "findings": findings,
        "recommendations": recommendations,
        "evidence": evidence,
        "report": text,
    }


def _salvage_department_text(text: str) -> dict[str, Any]:
    """Salvage a non-empty but off-format reply instead of failing the department.

    Keeps the raw text as the report (the UX Director still reads it) and
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
        "score": None,
        "findings": lines[:10],
        "recommendations": [],
        "evidence": [],
        "report": text,
    }


_REVIEW_LIST_SECTIONS = {
    "Journey Analysis": "journey_analysis",
    "Workflow Improvements": "workflow_improvements",
    "Navigation Recommendations": "navigation_recommendations",
    "Information Architecture": "information_architecture",
    "Accessibility Findings": "accessibility_findings",
    "Mobile Experience": "mobile_experience",
    "Onboarding Improvements": "onboarding_improvements",
    "Micro Interaction Suggestions": "micro_interaction_suggestions",
    "Microcopy Recommendations": "microcopy_recommendations",
    "Psychology Insights": "psychology_insights",
    "Quick Wins": "quick_wins",
    "High Impact Improvements": "high_impact_improvements",
}

_REVIEW_TEXT_SECTIONS = {
    "Estimated User Experience Gain": "estimated_ux_gain",
    "UX Specification": "ux_specification",
    "Executive Summary": "executive_summary",
}


def _find_section_until(text: str, header: str, stop_headers: list[str]) -> str:
    """Return a section's full text, capturing inner '##' sub-headers, until
    one of the given stop headers. Used for sections like the UX Specification
    whose body itself contains '##' headings."""
    m = re.search(
        rf"^##\s*{re.escape(header)}\s*:?\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in stop_headers)})\s*:?\s*$|\Z)",
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _parse_review(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _REVIEW_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _REVIEW_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The UX Specification body contains its own ## sub-headers (Goal, Steps,
    # Rules, Components, Acceptance Criteria), so parse it with a dedicated
    # extractor that runs until the Executive Summary.
    data["ux_specification"] = _find_section_until(text, "UX Specification", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Overall UX Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["overall_score"] = score
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


def _review_markdown(r: dict[str, Any]) -> str:
    lines = ["# UX & Human Experience Division - UX Review Report"]
    lines.append("")
    if r.get("overall_score") is not None:
        lines.append(f"**Overall UX Score:** {r['overall_score']}/100")
    for label, key in (
        ("Journey Analysis", "journey_analysis"),
        ("Workflow Improvements", "workflow_improvements"),
        ("Navigation Recommendations", "navigation_recommendations"),
        ("Information Architecture", "information_architecture"),
        ("Accessibility Findings", "accessibility_findings"),
        ("Mobile Experience", "mobile_experience"),
        ("Onboarding Improvements", "onboarding_improvements"),
        ("Micro Interaction Suggestions", "micro_interaction_suggestions"),
        ("Microcopy Recommendations", "microcopy_recommendations"),
        ("Psychology Insights", "psychology_insights"),
        ("Quick Wins", "quick_wins"),
        ("High Impact Improvements", "high_impact_improvements"),
    ):
        values = r.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if r.get("estimated_ux_gain"):
        lines.append("")
        lines.append("## Estimated User Experience Gain")
        lines.append(r["estimated_ux_gain"])
    if r.get("ux_specification"):
        lines.append("")
        lines.append("## UX Specification")
        lines.append(r["ux_specification"])
    if r.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(r["executive_summary"])
    return "\n".join(lines)


class UXDivision:
    """The UX & Human Experience Division (Layer 4)."""

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
        self.reviews: dict[str, UXReview] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _UX_DATA_FILE
        self._load()

    # --- Persistence ---

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump({"reviews": [r.model_dump() for r in self.reviews.values()]}, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("reviews", []):
                review = UXReview.model_validate(raw)
                self.reviews[review.id] = review
            logger.info(f"Loaded {len(self.reviews)} UX reviews from disk")
        except Exception as e:
            logger.error(f"Failed to load UX reviews: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": UX_DEPARTMENTS[did]["name"],
                "title": UX_DEPARTMENTS[did]["title"],
                "order": UX_ORDER.index(did),
                "is_coordinator": did == "ux-director",
            }
            for did in UX_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [r for r in self.reviews.values() if r.status == "completed"]
        confidences = [r.avg_confidence for r in completed if r.avg_confidence is not None]
        scores = [r.overall_score for r in completed if r.overall_score is not None]
        return {
            "total": len(self.reviews),
            "in_progress": sum(1 for r in self.reviews.values() if r.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for r in self.reviews.values() if r.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_ux_score": round(mean(scores)) if scores else None,
            "total_recommendations": sum(r.total_recommendations for r in completed),
            "departments": len(UX_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
        }

    def list_reviews(self) -> list[dict[str, Any]]:
        out = []
        for r in sorted(self.reviews.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": r.id,
                "request": r.request[:120],
                "subject_type": r.subject_type,
                "status": r.status,
                "stage": r.stage,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "avg_confidence": r.avg_confidence,
                "overall_score": r.overall_score,
                "total_recommendations": r.total_recommendations,
                "departments_completed": sum(1 for rep in r.reports if rep.status == "completed"),
                "total_departments": len(r.reports),
                "board_review_id": r.board_review_id,
            })
        return out

    def get_review(self, review_id: str) -> UXReview | None:
        return self.reviews.get(review_id)

    def get_review_dict(self, review_id: str) -> dict[str, Any] | None:
        r = self.reviews.get(review_id)
        return r.model_dump() if r else None

    def delete_review(self, review_id: str) -> bool:
        if review_id not in self.reviews:
            return False
        if review_id in self._running:
            self._running[review_id].cancel()
            del self._running[review_id]
        del self.reviews[review_id]
        self.persist()
        return True

    def board_request_text(self, review: UXReview) -> str:
        """Build a board review request that carries this review's findings."""
        summary = review.executive_summary or "UX review completed; see the review report for details."
        return f"{review.request}\n\n[UX Review Report from UXHED review {review.id[:8]}: {summary}]"

    # --- UX review workflow ---

    async def run_review(self, request: str, subject_type: str = "whole_product") -> dict[str, Any]:
        """Run a full UX review in the background. Updates the stored review."""
        review_id = str(uuid.uuid4())
        review = UXReview(id=review_id, request=request, subject_type=subject_type)
        self.reviews[review_id] = review

        task = asyncio.create_task(self._execute(review))
        self._running[review_id] = task
        task.add_done_callback(lambda t: self._running.pop(review_id, None) and None)
        return {"status": "started", "review_id": review_id, "review": review.model_dump()}

    async def run_review_sync(self, request: str, subject_type: str = "whole_product") -> dict[str, Any]:
        """Run a full UX review synchronously (blocks until finished). For tests/CLI."""
        review_id = str(uuid.uuid4())
        review = UXReview(id=review_id, request=request, subject_type=subject_type)
        self.reviews[review_id] = review
        await self._execute(review)
        return review.model_dump()

    async def _execute(self, review: UXReview) -> None:
        try:
            await self._run_departments(review)
            await self._run_director(review)
            self._finalize(review)
            if review.status != "failed":
                review.status = "completed"
            review.stage = "done"
            review.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            review.status = "cancelled"
            review.error = "UX review cancelled"
        except Exception as e:
            logger.exception("UX review failed")
            review.status = "failed"
            review.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for UX review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_ux_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> UXDepartmentReport:
        dept = UX_DEPARTMENTS[department_id]
        return UXDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, review: UXReview) -> None:
        review.stage = "review"

        async def run_one(department_id: str) -> None:
            report = self._report_skeleton(department_id)
            report.started_at = datetime.utcnow().isoformat() + "Z"
            review.reports.append(report)
            dept = UX_DEPARTMENTS[department_id]
            focus = " ".join(dept.get("focus_areas", []))
            try:
                user_prompt = build_department_request_prompt(
                    department_id, review.request, review.subject_type,
                    foundation_block=self._foundation_block(review.request + " " + focus),
                )
                parsed = await self._department_parsed(department_id, user_prompt)
                self._apply_parsed(report, parsed)
                report.completed_at = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                report.status = "failed"
                report.error = _err_text(e)
                logger.warning(f"UX department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in UX_DEPARTMENTS_LIST:
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
                    logger.warning(f"UX department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in UX_DEPARTMENTS_LIST:
            await run_one(department_id)

    def _apply_parsed(self, report: UXDepartmentReport, parsed: dict[str, Any]) -> None:
        report.verdict = parsed["verdict"]
        report.confidence = parsed["confidence"]
        report.score = parsed.get("score")
        report.findings = parsed["findings"]
        report.recommendations = parsed["recommendations"]
        report.evidence = parsed["evidence"]
        report.report = parsed["report"]
        report.status = "completed"

    # --- UX Director + report ---

    async def _run_director(self, review: UXReview) -> None:
        review.stage = "synthesis"
        director = self._report_skeleton("ux-director")
        director.started_at = datetime.utcnow().isoformat() + "Z"
        review.reports.append(director)

        reports = []
        for r in review.reports:
            if r.department_id == "ux-director":
                continue
            header = f"### {r.department_title} ({r.department_id})\n"
            if r.status == "completed":
                body = r.report or r.findings_text()
                reports.append(header + body[:3000])
            else:
                reports.append(header + f"_(department review unavailable: {r.error or 'failed'})_")

        data: dict[str, Any] = {}
        try:
            user_prompt = build_director_prompt(
                review.request, reports, review.subject_type,
                foundation_block=self._foundation_block(review.request + " UX review", 3),
            )
            text = await self._call_department("ux-director", user_prompt, max_tokens=4000)
            parsed = _parse_review(text)
            self._apply_parsed(director, {
                "verdict": "recommend",
                "confidence": 0.7,
                "score": parsed.get("overall_score"),
                "findings": _bullets(_find_section(text, "QUICK WINS")),
                "recommendations": _bullets(_find_section(text, "HIGH IMPACT IMPROVEMENTS")),
                "evidence": _bullets(_find_section(text, "EVIDENCE")),
                "report": text,
            })
            director.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            director.status = "failed"
            director.error = _err_text(e)
            logger.warning(f"UX Director failed: {e}")

        self._apply_review(review, data)

    def _confidence_fallback(self, review: UXReview) -> list[str]:
        out = []
        for r in review.reports:
            if r.department_id == "ux-director":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_review(self, review: UXReview, data: dict[str, Any]) -> None:
        review.overall_score = data.get("overall_score")
        for header, key in _REVIEW_LIST_SECTIONS.items():
            setattr(review, key, data.get(key) or [])
        for header, key in _REVIEW_TEXT_SECTIONS.items():
            setattr(review, key, data.get(key) or "")

        # Fill gaps from department reports so the report is never empty.
        all_recs: list[str] = []
        all_findings: list[str] = []
        scores: list[int] = []
        for r in review.reports:
            if r.department_id == "ux-director":
                continue
            all_recs.extend(r.recommendations)
            all_findings.extend(r.findings)
            if r.score is not None:
                scores.append(r.score)

        if not review.quick_wins:
            review.quick_wins = _dedupe(all_recs)[:5]
        if not review.high_impact_improvements:
            review.high_impact_improvements = _dedupe(all_recs)[:3]
        if not review.journey_analysis:
            review.journey_analysis = _dedupe(all_findings)[:6]
        if review.overall_score is None and scores:
            review.overall_score = round(mean(scores))
        if review.overall_score is None:
            review.overall_score = 50
        if not review.estimated_ux_gain:
            review.estimated_ux_gain = (
                "Faster completion of core tasks and fewer errors once the "
                "recommended improvements ship. Quantify with the acceptance "
                "criteria in the UX specification."
            )
        if not review.ux_specification:
            steps = review.quick_wins or review.workflow_improvements
            review.ux_specification = (
                "## Goal\nApply the UX review recommendations.\n\n"
                "## Steps\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps[:5])) +
                "\n\n## Acceptance Criteria\n- Core tasks complete with fewer clicks.\n"
                "- Improvements meet the accessibility standards."
            )
        if not review.executive_summary:
            done = sum(1 for r in review.reports if r.status == "completed")
            review.executive_summary = (
                f"UX review completed across {done} of {len(UX_DEPARTMENTS_LIST)} departments. "
                f"Overall UX score: {review.overall_score}/100. See the department "
                f"reports and UX specification for full details."
            )

    def _finalize(self, review: UXReview) -> None:
        done = [r for r in review.reports if r.status == "completed" and r.department_id != "ux-director"]
        if not done:
            review.status = "failed"
            review.error = "No UX departments completed (LLM unavailable)"
        if done:
            review.avg_confidence = round(mean(r.confidence for r in done), 2)
        review.total_recommendations = sum(len(r.recommendations) for r in done)
        review.review_markdown = _review_markdown(review.model_dump())
