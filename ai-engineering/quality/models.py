"""Layer 7 - Quality, Security & Release Excellence Division (QSRED). Data models.

The division runs twelve quality departments on a release subject (a versioned
release, a feature area, a service, the whole product, or an enterprise
deployment), and the Release Director merges their findings into a single
Release Excellence Report: functional QA, performance, security, compliance,
accessibility, documentation, architecture, deployment readiness, monitoring,
enterprise readiness, known risks, and a rollback strategy. The Director
finishes with a formal Final Decision (Go / Conditional Go / No Go) and a
release certificate. Nothing reaches customers without approval from this
division - it is the final gate before production.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class QualityDepartmentReport(BaseModel):
    """One quality department's assessment for the release subject."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 quality from this department's view
    checks: list[str] = Field(default_factory=list)  # checks performed + result
    findings: list[str] = Field(default_factory=list)  # defects / risks / blockers
    recommendations: list[str] = Field(default_factory=list)  # required fixes
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.checks) + list(self.findings) + list(self.recommendations)
        return "\n".join(f"- {p}" for p in parts)


class ReleaseExcellenceReport(BaseModel):
    """A complete Release Excellence Report for one release subject."""

    id: str
    request: str
    subject_type: str = "release"  # release | feature | service | whole_product | enterprise
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | review | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[QualityDepartmentReport] = Field(default_factory=list)

    # Consolidated Release Excellence Report sections produced by the Release Director.
    quality_score: Optional[int] = None  # Overall Quality Score 0-100
    release_version: str = ""
    functional_qa: list[str] = Field(default_factory=list)
    performance_review: list[str] = Field(default_factory=list)
    security_review: list[str] = Field(default_factory=list)
    compliance_review: list[str] = Field(default_factory=list)
    accessibility_review: list[str] = Field(default_factory=list)
    documentation_status: list[str] = Field(default_factory=list)
    architecture_review: list[str] = Field(default_factory=list)
    deployment_readiness: list[str] = Field(default_factory=list)
    monitoring_status: list[str] = Field(default_factory=list)
    enterprise_readiness: list[str] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)
    rollback_strategy: list[str] = Field(default_factory=list)

    # Formal release gate.
    final_decision: str = "pending"  # Go | Conditional Go | No Go | pending
    release_certificate: str = ""
    executive_summary: str = ""
    report_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_checks: int = 0
    total_findings: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
