"""Layer 4 - UX & Human Experience Division (UXHED). Data models.

The division runs eleven UX departments on a product surface (screen,
workflow, feature, onboarding, or whole product), and the UX Director merges
their findings into a single consolidated UX Review Report plus an
implementation-ready specification for the Development Division. The report
is delivered to the Executive Product Board.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class UXDepartmentReport(BaseModel):
    """One UX department's review of the subject surface."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 where the department scores the surface
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.findings) + list(self.recommendations)
        return "\n".join(f"- {p}" for p in parts)


class UXReview(BaseModel):
    """A complete UX review of one product surface."""

    id: str
    request: str
    subject_type: str = "whole_product"  # screen | workflow | feature | onboarding | whole_product
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | review | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[UXDepartmentReport] = Field(default_factory=list)
    # Consolidated UX Review Report sections produced by the UX Director.
    overall_score: Optional[int] = None
    journey_analysis: list[str] = Field(default_factory=list)
    workflow_improvements: list[str] = Field(default_factory=list)
    navigation_recommendations: list[str] = Field(default_factory=list)
    information_architecture: list[str] = Field(default_factory=list)
    accessibility_findings: list[str] = Field(default_factory=list)
    mobile_experience: list[str] = Field(default_factory=list)
    onboarding_improvements: list[str] = Field(default_factory=list)
    micro_interaction_suggestions: list[str] = Field(default_factory=list)
    microcopy_recommendations: list[str] = Field(default_factory=list)
    psychology_insights: list[str] = Field(default_factory=list)
    quick_wins: list[str] = Field(default_factory=list)
    high_impact_improvements: list[str] = Field(default_factory=list)
    estimated_ux_gain: str = ""
    ux_specification: str = ""
    executive_summary: str = ""
    review_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_recommendations: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
