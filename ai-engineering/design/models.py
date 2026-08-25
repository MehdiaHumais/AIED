"""Layer 5 - Visual Design & Design System Division (VDDS). Data models.

The division runs eleven design departments on a design subject (screen,
component set, flow, whole product, or brand), and the Creative Director
merges their output into a single Visual Design Package: design system
components, layout specification, spacing rules, typography, color tokens,
icon selection, responsive behavior, animation rules, accessibility
requirements, component variants, design assets, and an acceptance checklist.
The package becomes the implementation guide for the Frontend Development
Agent - it never writes frontend code itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class DesignDepartmentReport(BaseModel):
    """One design department's specification for the subject."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 design quality from this department's view
    tokens: list[str] = Field(default_factory=list)  # e.g. "--spacing-md: 16px"
    components: list[str] = Field(default_factory=list)  # reusable component specs
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.findings) + list(self.recommendations) + list(self.components)
        return "\n".join(f"- {p}" for p in parts)


class VisualDesignPackage(BaseModel):
    """A complete Visual Design Package for one design subject."""

    id: str
    request: str
    subject_type: str = "screen"  # screen | component | flow | whole_product | brand
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | design | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[DesignDepartmentReport] = Field(default_factory=list)

    # Consolidated Visual Design Package sections produced by the Creative Director.
    visual_quality_score: Optional[int] = None  # 0-100
    design_components: list[str] = Field(default_factory=list)
    layout_specification: list[str] = Field(default_factory=list)
    spacing_rules: list[str] = Field(default_factory=list)
    typography: list[str] = Field(default_factory=list)
    color_tokens: list[str] = Field(default_factory=list)
    icon_selection: list[str] = Field(default_factory=list)
    responsive_behavior: list[str] = Field(default_factory=list)
    animation_rules: list[str] = Field(default_factory=list)
    accessibility_requirements: list[str] = Field(default_factory=list)
    component_variants: list[str] = Field(default_factory=list)
    design_assets: list[str] = Field(default_factory=list)
    acceptance_checklist: list[str] = Field(default_factory=list)

    # Implementation-ready guide for the Frontend Development Agent.
    visual_specification: str = ""
    executive_summary: str = ""
    package_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_tokens: int = 0
    total_components: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
