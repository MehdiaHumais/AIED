"""Layer 9 - Enterprise AI Governance & Orchestration Division (EAGOD). Data models.

The division governs, orchestrates, coordinates, monitors, and optimizes every
AI agent, workflow, and decision across the enterprise. It does not replace the
CEO - it acts as the Chief Operating Office for the AI workforce, ensuring the
right agents work at the right time, with the right information, in the right
order.

Twelve operations departments run on an enterprise operation request (a build
request, a workflow to optimize, a conflict to arbitrate, or an enterprise-wide
health review), and the Chief AI Operations Director merges their findings into
one Division Operations Report: required divisions, work packages, agent
assignments, capability matches, arbitration rulings, resource plan, dependency
map, schedule, policy compliance, performance insights, audit trail,
operational alerts, enterprise KPIs, and approvals - plus an Executive
Operations Brief the CEO reads live. Every agent reports operational status
here; no department bypasses this layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class GovernanceDepartmentReport(BaseModel):
    """One operations department's assessment for the enterprise operation."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 operations maturity from this department's view
    checks: list[str] = Field(default_factory=list)  # what was reviewed + result
    findings: list[str] = Field(default_factory=list)  # issues / opportunities identified
    recommendations: list[str] = Field(default_factory=list)  # operational actions
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.checks) + list(self.findings) + list(self.recommendations)
        return "\n".join(f"- {p}" for p in parts)


class OperationsReport(BaseModel):
    """A complete Division Operations Report for one enterprise operation."""

    id: str
    request: str
    subject_type: str = "operation"  # operation | workflow | conflict | enterprise
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | review | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[GovernanceDepartmentReport] = Field(default_factory=list)

    # Consolidated Division Operations Report sections produced by the
    # Chief AI Operations Director.
    governance_score: Optional[int] = None  # 0-100
    final_decision: str = "pending"  # Approved | Conditional Approval | Not Approved | pending
    required_divisions: list[str] = Field(default_factory=list)
    work_packages: list[str] = Field(default_factory=list)
    agent_assignments: list[str] = Field(default_factory=list)
    capability_matches: list[str] = Field(default_factory=list)
    arbitration_rulings: list[str] = Field(default_factory=list)
    resource_plan: list[str] = Field(default_factory=list)
    dependency_map: list[str] = Field(default_factory=list)
    schedule: list[str] = Field(default_factory=list)
    policy_compliance: list[str] = Field(default_factory=list)
    performance_insights: list[str] = Field(default_factory=list)
    audit_trail: list[str] = Field(default_factory=list)
    operational_alerts: list[str] = Field(default_factory=list)
    enterprise_kpis: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)

    # The live operational view the CEO reads.
    operations_brief: str = ""
    executive_summary: str = ""
    report_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_checks: int = 0
    total_findings: int = 0
    total_recommendations: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
