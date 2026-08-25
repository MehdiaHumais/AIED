"""Layer 6 - Growth, Conversion & Customer Success Division (GCCSD). Data models.

The division runs eleven growth departments on a growth subject (landing page,
product experience, onboarding flow, pricing, or whole business), and the
Growth Director merges their findings into a single Growth Intelligence
Report: conversion analysis, landing page audit, acquisition opportunities,
activation improvements, retention strategy, pricing recommendations,
customer success insights, customer feedback summary, analytics findings,
experiment recommendations, trust & credibility assessment, quick wins, high
impact projects, and estimated business impact. The report becomes the
implementation-ready spec for the Frontend and Backend Development Agents -
growth recommendations become implementation tasks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class GrowthDepartmentReport(BaseModel):
    """One growth department's assessment for the subject."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 growth maturity from this department's view
    metrics: list[str] = Field(default_factory=list)  # key KPIs this dept owns
    opportunities: list[str] = Field(default_factory=list)  # concrete growth actions
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.findings) + list(self.recommendations) + list(self.opportunities)
        return "\n".join(f"- {p}" for p in parts)


class GrowthReviewPackage(BaseModel):
    """A complete Growth Intelligence Report for one growth subject."""

    id: str
    request: str
    subject_type: str = "landing_page"  # landing_page | product | onboarding | pricing | whole_business
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | review | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[GrowthDepartmentReport] = Field(default_factory=list)

    # Consolidated Growth Intelligence Report sections produced by the Growth Director.
    growth_score: Optional[int] = None  # 0-100
    conversion_analysis: list[str] = Field(default_factory=list)
    landing_page_audit: list[str] = Field(default_factory=list)
    acquisition_opportunities: list[str] = Field(default_factory=list)
    activation_improvements: list[str] = Field(default_factory=list)
    retention_strategy: list[str] = Field(default_factory=list)
    pricing_recommendations: list[str] = Field(default_factory=list)
    customer_success_insights: list[str] = Field(default_factory=list)
    customer_feedback_summary: list[str] = Field(default_factory=list)
    analytics_findings: list[str] = Field(default_factory=list)
    experiment_recommendations: list[str] = Field(default_factory=list)
    trust_credibility_assessment: list[str] = Field(default_factory=list)
    quick_wins: list[str] = Field(default_factory=list)
    high_impact_projects: list[str] = Field(default_factory=list)
    estimated_business_impact: list[str] = Field(default_factory=list)

    # Implementation-ready guide for the Frontend and Backend Development Agents.
    implementation_specification: str = ""
    executive_summary: str = ""
    package_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_opportunities: int = 0
    total_metrics: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
