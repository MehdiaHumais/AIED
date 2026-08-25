"""Layer 8 - Intelligence, Learning & Continuous Improvement Division (ILCID). Data models.

The division runs eleven intelligence departments on a learning subject (a
completed project, a release, a product, the whole organization, or a specific
learning topic), and the Intelligence Director merges their findings into a
single Project Intelligence Report: project summary, objectives achieved,
customer impact, business impact, feature adoption, support trends,
performance, security, UX outcomes, growth outcomes, lessons learned, process
improvements, updated standards, future recommendations, and confidence
levels - plus an organization-wide knowledge graph that every other department
queries before making decisions.

This division does not create products. It makes every other division smarter:
updating Layer 1 standards, refining board decision criteria, improving
research/UX/design/growth/quality methods - it is the organizational memory and
continuous improvement engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class IntelligenceDepartmentReport(BaseModel):
    """One intelligence department's assessment for the learning subject."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 intelligence maturity from this department's view
    checks: list[str] = Field(default_factory=list)  # what was reviewed + result
    findings: list[str] = Field(default_factory=list)  # lessons / problems identified
    recommendations: list[str] = Field(default_factory=list)  # improvements / standard updates
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.checks) + list(self.findings) + list(self.recommendations)
        return "\n".join(f"- {p}" for p in parts)


class IntelligenceReport(BaseModel):
    """A complete Project Intelligence Report for one learning subject."""

    id: str
    request: str
    subject_type: str = "project"  # project | release | product | organization | learning_topic
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | review | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[IntelligenceDepartmentReport] = Field(default_factory=list)

    # Consolidated Project Intelligence Report sections produced by the Intelligence Director.
    intelligence_score: Optional[int] = None  # 0-100
    project_summary: list[str] = Field(default_factory=list)
    objectives_achieved: list[str] = Field(default_factory=list)
    customer_impact: list[str] = Field(default_factory=list)
    business_impact: list[str] = Field(default_factory=list)
    feature_adoption: list[str] = Field(default_factory=list)
    support_trends: list[str] = Field(default_factory=list)
    performance: list[str] = Field(default_factory=list)
    security: list[str] = Field(default_factory=list)
    ux_outcomes: list[str] = Field(default_factory=list)
    growth_outcomes: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
    process_improvements: list[str] = Field(default_factory=list)
    updated_standards: list[str] = Field(default_factory=list)
    future_recommendations: list[str] = Field(default_factory=list)
    confidence_levels: list[str] = Field(default_factory=list)

    # The central intelligence layer every department queries before deciding:
    # relationships between products, features, users, business goals, workflows,
    # standards, lessons learned, recommendations, and future projects.
    knowledge_graph: str = ""
    executive_summary: str = ""
    report_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_lessons: int = 0
    total_recommendations: int = 0
    total_standards: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
