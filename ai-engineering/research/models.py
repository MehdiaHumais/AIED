"""Layer 3 - Product Research & Discovery Division (PRDD). Data models.

The division runs ten parallel research departments on a product subject and
the Research Coordinator merges their findings into a single standardized
research dossier for the Executive Product Board.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class DepartmentReport(BaseModel):
    """One research department's findings on the subject."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
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


class ResearchDossier(BaseModel):
    """A complete research dossier on one product subject."""

    id: str
    request: str
    subject_type: str = "new_product"  # new_product | existing_product | market | competitor | feature
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | research | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[DepartmentReport] = Field(default_factory=list)
    # Standardized dossier sections produced by the Research Coordinator.
    research_summary: str = ""
    business_objective: str = ""
    customer_needs: list[str] = Field(default_factory=list)
    market_insights: list[str] = Field(default_factory=list)
    competitor_findings: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    ux_risks: list[str] = Field(default_factory=list)
    growth_opportunities: list[str] = Field(default_factory=list)
    security_considerations: list[str] = Field(default_factory=list)
    industry_expectations: list[str] = Field(default_factory=list)
    pricing_suggestions: list[str] = Field(default_factory=list)
    recommended_priorities: list[str] = Field(default_factory=list)
    confidence_levels: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    dossier_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_recommendations: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
