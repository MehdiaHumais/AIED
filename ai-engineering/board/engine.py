"""Layer 2 - Executive Product Board. Review engine.

Runs a product request through the nine executive members, computes the
weighted scorecard, produces the final Decision Package, and persists
reviews to ``data/board/reviews.json``.

The engine is resilient: an LLM outage marks individual members as failed
and the review still completes (score renormalized over the scored
categories). Nothing here writes code - it produces decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from board.models import BoardMemberVerdict, BoardReview, ScorecardEntry
from board.prompts import (
    APPROVE_THRESHOLD,
    REVISION_THRESHOLD,
    BOARD_MEMBERS,
    BOARD_ORDER,
    SCORE_MEMBERS,
    SCORECARD_LABELS,
    SCORECARD_WEIGHTS,
    build_chair_prompt,
    build_member_request_prompt,
    get_board_member_prompt,
)

logger = logging.getLogger(__name__)

_BOARD_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "board")
_BOARD_DATA_FILE = os.path.join(_BOARD_DATA_DIR, "reviews.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_MEMBER_TIMEOUT = 180
# Free-tier Gemini allows ~10 requests/min. A review fires 9 member calls back
# to back, so space them out to keep the burst under the RPM cap.
_MEMBER_GAP = 6.0


def _err_text(e: Exception) -> str:
    """Human-readable error message (asyncio.TimeoutError has an empty str())."""
    if isinstance(e, asyncio.TimeoutError):
        return f"Timed out after {_MEMBER_TIMEOUT}s"
    return str(e)[:300] or type(e).__name__


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
        # also allow '## HEADER: inline value'
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


def _parse_member_output(text: str) -> dict[str, Any]:
    score_match = re.search(r"##\s*SCORE\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    score = 50
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = 50

    verdict = "reviewed"
    verdict_match = re.search(
        r"##\s*VERDICT\s*:?\s*(approved|approve|go|conditional|rejected|reject|no)",
        text, re.IGNORECASE,
    )
    if verdict_match:
        v = verdict_match.group(1).lower()
        verdict = {"approved": "approved", "approve": "approved", "go": "approved",
                   "conditional": "conditional", "rejected": "rejected",
                   "reject": "rejected", "no": "rejected"}.get(v, "reviewed")

    findings = _bullets(_find_section(text, "FINDINGS"))
    recommendations = _bullets(_find_section(text, "RECOMMENDATIONS"))
    return {"score": score, "verdict": verdict, "findings": findings,
            "recommendations": recommendations, "report": text}


def _parse_decision(text: str) -> dict[str, Any]:
    """Parse the chair's Decision Package markdown into a dict."""
    dec = {
        "project_name": _inline_value(text, "Project Name"),
        "business_goal": _inline_value(text, "Business Goal"),
        "customer_goal": _inline_value(text, "Customer Goal"),
        "approved_features": _bullets(_find_section(text, "Approved Features")),
        "deferred_features": _bullets(_find_section(text, "Deferred Features")),
        "rejected_features": _bullets(_find_section(text, "Rejected Features")),
        "priority": _inline_value(text, "Priority"),
        "estimated_complexity": _inline_value(text, "Estimated Complexity"),
        "expected_customer_value": _inline_value(text, "Expected Customer Value"),
        "ux_rules": _bullets(_find_section(text, "UX Rules")),
        "security_rules": _bullets(_find_section(text, "Security Rules")),
        "acceptance_criteria": _bullets(_find_section(text, "Acceptance Criteria")),
    }
    # Roadmap / risk register are optional extra sections
    roadmap = _bullets(_find_section(text, "Roadmap"))
    risk = _bullets(_find_section(text, "Risk Register"))
    if roadmap:
        dec["roadmap"] = roadmap
    if risk:
        dec["risk_register"] = risk
    return dec


def _decision_markdown(dec: dict[str, Any]) -> str:
    lines = ["# Executive Product Board - Decision Package"]
    lines.append("")
    if dec.get("project_name"):
        lines.append(f"**Project:** {dec['project_name']}")
    if dec.get("business_goal"):
        lines.append(f"**Business Goal:** {dec['business_goal']}")
    if dec.get("customer_goal"):
        lines.append(f"**Customer Goal:** {dec['customer_goal']}")
    if dec.get("priority"):
        lines.append(f"**Priority:** {dec['priority']}")
    if dec.get("estimated_complexity"):
        lines.append(f"**Estimated Complexity:** {dec['estimated_complexity']}")
    if dec.get("expected_customer_value"):
        lines.append(f"**Expected Customer Value:** {dec['expected_customer_value']}")
    for label, key in (
        ("Approved Features", "approved_features"),
        ("Deferred Features", "deferred_features"),
        ("Rejected Features", "rejected_features"),
        ("UX Rules", "ux_rules"),
        ("Security Rules", "security_rules"),
        ("Acceptance Criteria", "acceptance_criteria"),
        ("Roadmap", "roadmap"),
        ("Risk Register", "risk_register"),
    ):
        values = dec.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    return "\n".join(lines)


def _slugify(text: str, max_words: int = 3) -> str:
    words = [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]
    core = "-".join(words[:max_words]) if words else "product"
    return core[:48]


def _derive_codename(request: str) -> str:
    base = _slugify(request, 2) or "product"
    return f"{base}-{uuid.uuid4().hex[:5]}"


def _derive_project_name(request: str) -> str:
    words = re.split(r"\s+", request.strip())
    short = " ".join(words[:4]).strip(" ,.-")
    if not short:
        short = "New Product"
    return short.title()[:60]


# --- Engine ---

class ExecutiveProductBoard:
    """The highest decision-making authority before development begins."""

    def __init__(self, config, llm_manager, kb=None, data_file: str | None = None, model: str | None = None) -> None:
        self.config = config
        self.llm = llm_manager
        self.kb = kb
        self.model = model or _DEFAULT_MODEL
        self.data_file = data_file or _BOARD_DATA_FILE
        self.reviews: dict[str, BoardReview] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._load()

    # --- Persistence ---

    def _load(self) -> None:
        if not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("reviews", []):
                try:
                    review = BoardReview.model_validate(raw)
                    if review.status == "in_review":
                        review.status = "failed"
                        review.error = review.error or "Interrupted (server restarted mid-review)"
                    self.reviews[review.id] = review
                except Exception as e:
                    logger.warning(f"Skipping malformed board review: {e}")
            logger.info(f"Loaded {len(self.reviews)} board reviews")
        except Exception as e:
            logger.error(f"Failed to load board reviews: {e}")

    def persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            payload = {"reviews": [r.model_dump() for r in self.reviews.values()]}
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist board reviews: {e}")

    # --- Read ---

    def list_reviews(self) -> list[dict[str, Any]]:
        out = []
        for r in sorted(self.reviews.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": r.id,
                "request": r.request[:120],
                "status": r.status,
                "stage": r.stage,
                "total_score": r.total_score,
                "final_verdict": r.final_verdict,
                "project_id": r.project_id,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "scored_members": sum(1 for v in r.verdicts if v.status == "completed"),
                "total_members": len(r.verdicts),
            })
        return out

    def get_review(self, review_id: str) -> BoardReview | None:
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

    def stats(self) -> dict[str, Any]:
        completed = [r for r in self.reviews.values() if r.status == "completed"]
        return {
            "total": len(self.reviews),
            "in_review": sum(1 for r in self.reviews.values() if r.status == "in_review"),
            "approved": sum(1 for r in completed if r.final_verdict == "approved"),
            "revision": sum(1 for r in completed if r.final_verdict == "revision"),
            "rejected": sum(1 for r in completed if r.final_verdict == "rejected"),
            "failed": sum(1 for r in self.reviews.values() if r.status == "failed"),
            "avg_score": round(sum(r.total_score or 0 for r in completed) / len(completed), 1) if completed else None,
            "approve_threshold": APPROVE_THRESHOLD,
        }

    def members(self) -> list[dict[str, Any]]:
        return [
            {
                "id": mid,
                "name": BOARD_MEMBERS[mid]["name"],
                "title": BOARD_MEMBERS[mid]["title"],
                "score_category": BOARD_MEMBERS[mid]["score_category"],
                "order": BOARD_ORDER.index(mid),
            }
            for mid in BOARD_ORDER
        ]

    # --- Review workflow ---

    async def run_review(self, request: str, project_id: str | None = None) -> dict[str, Any]:
        """Run the full board review for a request. Updates the stored review."""
        review_id = str(uuid.uuid4())
        review = BoardReview(id=review_id, request=request, project_id=project_id)
        self.reviews[review_id] = review

        task = asyncio.create_task(self._execute(review))
        self._running[review_id] = task
        task.add_done_callback(lambda t: self._running.pop(review_id, None) and None)
        return {"status": "started", "review_id": review_id, "review": review.model_dump()}

    async def run_review_sync(self, request: str, project_id: str | None = None) -> dict[str, Any]:
        """Run a full review synchronously (blocks until finished). For tests/CLI."""
        review_id = str(uuid.uuid4())
        review = BoardReview(id=review_id, request=request, project_id=project_id)
        self.reviews[review_id] = review
        await self._execute(review)
        return review.model_dump()

    async def _execute(self, review: BoardReview) -> None:
        try:
            await self._run_strategist(review)
            await self._run_members(review)
            await self._run_chair(review)
            self._score(review)
            if review.final_verdict == "failed":
                review.status = "failed"
            else:
                review.status = "completed"
            review.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            review.status = "cancelled"
            review.error = "Review cancelled"
        except Exception as e:
            logger.exception("Board review failed")
            review.status = "failed"
            review.error = str(e)
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 4) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for board: {e}")
            return ""

    async def _call_member(self, member_id: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": get_board_member_prompt(member_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.3, max_tokens=1800),
            timeout=_MEMBER_TIMEOUT,
        )
        return response

    async def _run_strategist(self, review: BoardReview) -> None:
        review.stage = "strategist"
        verdict = self._verdict_skeleton("chief-product-strategist")
        verdict.started_at = datetime.utcnow().isoformat() + "Z"
        review.verdicts.append(verdict)
        try:
            focus = " ".join(BOARD_MEMBERS["chief-product-strategist"]["focus_areas"])
            user_prompt = build_member_request_prompt(
                "chief-product-strategist", review.request,
                foundation_block=self._foundation_block(review.request + " " + focus),
            )
            text = await self._call_member("chief-product-strategist", user_prompt)
            parsed = _parse_member_output(text)
            self._apply_parsed(verdict, parsed)
            verdict.completed_at = datetime.utcnow().isoformat() + "Z"
            scope = _find_section(text, "SCOPE") or (verdict.recommendations[0] if verdict.recommendations else "")
            review.strategist_scope = scope[:500]
            review.strategist_notes = verdict.recommendations
        except Exception as e:
            verdict.status = "failed"
            verdict.error = _err_text(e)
            logger.warning(f"Strategist failed: {e}")

    async def _run_members(self, review: BoardReview) -> None:
        review.stage = "members"
        scope_context = f"Approved scope from the Chief Product Strategist: {review.strategist_scope}" if review.strategist_scope else ""

        async def run_one(member_id: str) -> None:
            verdict = self._verdict_skeleton(member_id)
            verdict.started_at = datetime.utcnow().isoformat() + "Z"
            review.verdicts.append(verdict)
            member = BOARD_MEMBERS[member_id]
            focus = " ".join(member.get("focus_areas", []))
            try:
                user_prompt = build_member_request_prompt(
                    member_id, review.request,
                    foundation_block=self._foundation_block(review.request + " " + focus),
                    prior_context=scope_context,
                )
                text = await self._call_member(member_id, user_prompt)
                parsed = _parse_member_output(text)
                self._apply_parsed(verdict, parsed)
                verdict.completed_at = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                verdict.status = "failed"
                verdict.error = _err_text(e)
                logger.warning(f"Board member {member_id} failed: {e}")

        # The LLM manager serializes all requests, so members run one at a time.
        # Sequential execution gives each member a full timeout window instead
        # of burning it waiting in the queue behind earlier members. A short gap
        # between members keeps the burst under the provider's free-tier RPM.
        for member_id in SCORE_MEMBERS:
            await run_one(member_id)
            if member_id != SCORE_MEMBERS[-1]:
                await asyncio.sleep(_MEMBER_GAP)

    def _verdict_skeleton(self, member_id: str) -> BoardMemberVerdict:
        member = BOARD_MEMBERS[member_id]
        return BoardMemberVerdict(
            member_id=member_id,
            member_name=member["name"],
            member_title=member["title"],
        )

    def _apply_parsed(self, verdict: BoardMemberVerdict, parsed: dict[str, Any]) -> None:
        verdict.score = int(parsed["score"])
        verdict.verdict = parsed["verdict"]
        verdict.findings = parsed["findings"]
        verdict.recommendations = parsed["recommendations"]
        verdict.report = parsed["report"]
        verdict.status = "completed"

    # --- Chair + decision package ---

    async def _run_chair(self, review: BoardReview) -> None:
        review.stage = "chair"
        chair = self._verdict_skeleton("executive-review-chair")
        chair.started_at = datetime.utcnow().isoformat() + "Z"
        review.verdicts.append(chair)
        reports = []
        for v in review.verdicts:
            if v.member_id == "executive-review-chair":
                continue
            header = f"### {v.member_name} ({v.member_id})\n"
            if v.status == "completed":
                body = v.report or v.findings_text()
                reports.append(header + body[:3000])
            else:
                reports.append(header + f"_(member review unavailable: {v.error or 'failed'})_")
        try:
            user_prompt = build_chair_prompt(
                review.request,
                reports,
                foundation_block=self._foundation_block(review.request + " decision package", 3),
            )
            text = await self._call_member("executive-review-chair", user_prompt)
            chair.report = text
            chair.verdict = "approved" if len(text) > 20 else "reviewed"
            chair.status = "completed"
            chair.completed_at = datetime.utcnow().isoformat() + "Z"
            dec = _parse_decision(text)
        except Exception as e:
            chair.status = "failed"
            chair.error = _err_text(e)
            logger.warning(f"Chair failed: {e}")
            dec = {}

        review.decision = self._finalize_decision(dec, review)
        review.decision_markdown = _decision_markdown(review.decision)

    def _finalize_decision(self, dec: dict[str, Any], review: BoardReview) -> dict[str, Any]:
        """Fill any gaps in the chair's package from member reports."""
        base = {
            "project_name": dec.get("project_name") or _derive_project_name(review.request),
            "codename": dec.get("codename") or _derive_codename(review.request),
            "business_goal": dec.get("business_goal") or "",
            "customer_goal": dec.get("customer_goal") or "",
            "approved_features": dec.get("approved_features") or [],
            "deferred_features": dec.get("deferred_features") or [],
            "rejected_features": dec.get("rejected_features") or [],
            "priority": dec.get("priority") or "P1",
            "estimated_complexity": dec.get("estimated_complexity") or "medium",
            "expected_customer_value": dec.get("expected_customer_value") or "",
            "ux_rules": dec.get("ux_rules") or [],
            "security_rules": dec.get("security_rules") or [],
            "acceptance_criteria": dec.get("acceptance_criteria") or [],
            "roadmap": dec.get("roadmap") or [],
            "risk_register": dec.get("risk_register") or [],
        }
        if not base["approved_features"]:
            collected = []
            for v in review.verdicts:
                collected.extend(v.recommendations)
            base["approved_features"] = _dedupe(collected)[:12]
        if not base["ux_rules"]:
            ux = self._verdict_in(review, "ux-executive")
            if ux and ux.recommendations:
                base["ux_rules"] = _dedupe(ux.recommendations)[:8]
        if not base["security_rules"]:
            risk = self._verdict_in(review, "risk-compliance-director")
            if risk and risk.recommendations:
                base["security_rules"] = _dedupe(risk.recommendations)[:8]
        if not base["acceptance_criteria"]:
            base["acceptance_criteria"] = [
                "Pass all UX, accessibility, security, and performance checks before release."
            ]
        return base

    # --- Scoring ---

    def _score(self, review: BoardReview) -> None:
        review.stage = "done"
        scored_categories: list[ScorecardEntry] = []
        scored_weight = 0.0
        total = 0.0
        for mid in SCORE_MEMBERS:
            member = BOARD_MEMBERS[mid]
            cat = member["score_category"]
            weight = SCORECARD_WEIGHTS.get(cat, 0.0)
            entry = ScorecardEntry(
                category=cat,
                label=SCORECARD_LABELS.get(cat, cat),
                weight=weight,
                member_id=mid,
                member_name=member["name"],
            )
            verdict = self._verdict_in(review, mid)
            if verdict and verdict.status == "completed":
                entry.score = verdict.score
                entry.weighted = round(verdict.score * weight, 2)
                entry.scored = True
                scored_categories.append(entry)
                scored_weight += weight
                total += verdict.score * weight
            else:
                scored_categories.append(entry)
        review.scorecard = scored_categories
        if scored_weight > 0:
            review.total_score = round(total / scored_weight, 1)
            if review.total_score >= APPROVE_THRESHOLD:
                review.final_verdict = "approved"
            elif review.total_score >= REVISION_THRESHOLD:
                review.final_verdict = "revision"
            else:
                review.final_verdict = "rejected"
        else:
            review.total_score = None
            review.final_verdict = "failed"
            detail = self._first_member_error(review)
            if detail:
                review.error = (
                    "All board member reviews failed - the LLM provider is "
                    f"unavailable or rate-limited. First member error: {detail}"
                )
            else:
                review.error = review.error or "No board member reviews completed (LLM unavailable)"

    @staticmethod
    def _verdict_in(review: BoardReview, member_id: str) -> BoardMemberVerdict | None:
        for v in review.verdicts:
            if v.member_id == member_id:
                return v
        return None

    @staticmethod
    def _first_member_error(review: BoardReview) -> str:
        for v in review.verdicts:
            if v.status != "completed" and v.error:
                return v.error[:400]
        return ""

    # --- Send to development ---

    def build_development_package(self, review_id: str) -> dict[str, Any] | None:
        """Build the structured package handed to the dev agents (Hermes project)."""
        review = self.reviews.get(review_id)
        if not review:
            return None
        dec = review.decision or {}
        package = {
            "project_name": dec.get("project_name") or _derive_project_name(review.request),
            "codename": dec.get("codename") or _derive_codename(review.request),
            "description": (
                f"{dec.get('business_goal') or ''}\n\n"
                f"Customer goal: {dec.get('customer_goal') or ''}".strip()
            ),
            "tech_stack": [],
            "decision_package": dec,
            "decision_markdown": review.decision_markdown,
            "board_review_id": review.id,
            "total_score": review.total_score,
            "final_verdict": review.final_verdict,
        }
        return package


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        key = it.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out
