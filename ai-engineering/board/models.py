"""Layer 2 - Executive Product Board. Data models.

The board reviews every product request before development and produces a
structured decision package plus a weighted scorecard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class BoardMemberDef(BaseModel):
    """Static definition of one executive board member."""

    id: str
    name: str
    title: str
    department: str = "Executive Product Board (Layer 2)"
    score_category: Optional[str] = None  # which scorecard category they feed
    focus_areas: list[str] = Field(default_factory=list)


class BoardMemberVerdict(BaseModel):
    """A single member's review of the request."""

    member_id: str
    member_name: str
    member_title: str
    score: int = 50  # 0-100, 100 = strongly approve
    verdict: str = "reviewed"  # approved | conditional | rejected | reviewed | failed
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.findings) + list(self.recommendations)
        return "\n".join(f"- {p}" for p in parts)


class ScorecardEntry(BaseModel):
    category: str
    label: str
    weight: float  # 0-1
    score: Optional[int] = None
    weighted: Optional[float] = None
    member_id: str = ""
    member_name: str = ""
    scored: bool = False


class BoardReview(BaseModel):
    """A complete Executive Product Board review of one request."""

    id: str
    request: str
    project_id: Optional[str] = None
    status: str = "in_review"  # in_review | completed | failed | cancelled
    stage: str = "queued"  # queued | strategist | members | chair | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    strategist_scope: str = ""
    strategist_notes: list[str] = Field(default_factory=list)
    verdicts: list[BoardMemberVerdict] = Field(default_factory=list)
    scorecard: list[ScorecardEntry] = Field(default_factory=list)
    total_score: Optional[float] = None
    final_verdict: str = "pending"  # approved | revision | rejected | failed | pending
    decision: dict[str, Any] = Field(default_factory=dict)
    decision_markdown: str = ""
    error: str = ""
