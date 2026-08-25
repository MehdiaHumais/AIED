"""Layer 10 - Enterprise Knowledge & Digital Twin Platform (EKDT). Data models.

EKDT is the living digital representation of the entire organization: the
single source of truth for the whole AI enterprise. Instead of documents in
folders and human memory, the platform keeps knowledge with relationships,
context, reasoning, decisions, actions, and learning - the system remembers why
things exist. It sits underneath everything: every agent connects to EKDT
before it works.

Eleven knowledge systems run on an enterprise knowledge subject (a new product
idea, a project, a customer, a business process, or an enterprise-wide refresh),
and the Knowledge Architect Agent merges their findings into one Digital Twin
Update Report: organizational snapshot, product snapshot, customer insights,
process updates, agent insights, decisions logged, knowledge graph links,
semantic answers, proven patterns, detected patterns, predictions, knowledge
actions, and knowledge quality - plus a Knowledge Brief for the CEO.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class EkdtDepartmentReport(BaseModel):
    """One knowledge system's update for the enterprise knowledge subject."""

    department_id: str
    department_name: str
    department_title: str
    verdict: str = "neutral"  # support | recommend | caution | risk | neutral
    confidence: float = 0.5  # 0.0 - 1.0
    score: Optional[int] = None  # 0-100 knowledge confidence from this system's view
    checks: list[str] = Field(default_factory=list)  # what was reviewed + result
    findings: list[str] = Field(default_factory=list)  # issues / knowledge gaps identified
    recommendations: list[str] = Field(default_factory=list)  # knowledge actions
    evidence: list[str] = Field(default_factory=list)
    report: str = ""
    status: str = "completed"  # completed | failed | skipped
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def findings_text(self) -> str:
        parts = list(self.checks) + list(self.findings) + list(self.recommendations)
        return "\n".join(f"- {p}" for p in parts)


class DigitalTwinReport(BaseModel):
    """A complete Digital Twin Update Report for one enterprise knowledge subject."""

    id: str
    request: str
    subject_type: str = "idea"  # idea | project | customer | process | enterprise
    status: str = "in_progress"  # in_progress | completed | failed | cancelled
    stage: str = "queued"  # queued | review | synthesis | done
    created_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    reports: list[EkdtDepartmentReport] = Field(default_factory=list)

    # Consolidated Digital Twin Update Report sections produced by the
    # Knowledge Architect Agent.
    knowledge_score: Optional[int] = None  # 0-100 overall knowledge confidence
    knowledge_status: str = "pending"  # Optimal | Actionable | Stale | pending
    org_snapshot: list[str] = Field(default_factory=list)  # Organizational Digital Twin
    product_snapshot: list[str] = Field(default_factory=list)  # Product Digital Twin
    customer_insights: list[str] = Field(default_factory=list)  # Customer Digital Twin
    process_updates: list[str] = Field(default_factory=list)  # Process Digital Twin
    agent_insights: list[str] = Field(default_factory=list)  # AI Agent Digital Twin
    decisions_logged: list[str] = Field(default_factory=list)  # Decision Memory Engine
    knowledge_links: list[str] = Field(default_factory=list)  # Knowledge Graph
    semantic_answers: list[str] = Field(default_factory=list)  # Semantic Search Engine
    proven_patterns: list[str] = Field(default_factory=list)  # Experience Repository
    detected_patterns: list[str] = Field(default_factory=list)  # Pattern Recognition Engine
    predictions: list[str] = Field(default_factory=list)  # Predictive Intelligence Engine
    knowledge_actions: list[str] = Field(default_factory=list)  # Knowledge Architect actions
    knowledge_quality: list[str] = Field(default_factory=list)  # accuracy / freshness controls

    # The live knowledge view the CEO reads.
    knowledge_brief: str = ""
    executive_summary: str = ""
    report_markdown: str = ""
    avg_confidence: Optional[float] = None
    total_checks: int = 0
    total_findings: int = 0
    total_recommendations: int = 0
    board_review_id: Optional[str] = None
    error: str = ""
