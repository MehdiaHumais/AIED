"""Cross-Layer Workflow Orchestration. Data models.

A WorkflowRun walks a product request through all 10 layers:

    Layer 2 Board -> Layer 3 Research -> Layer 4 UX -> Layer 5 Design
    -> Layer 6 Growth -> Layer 7 Quality
    -> Layer 8 Intelligence -> Layer 9 Governance -> Layer 10 EKDT

Layers 2-7 are board-gated: each produces an artifact, submits it to the
Executive Product Board, and only advances on approval. A rejected/revision
gate pauses the run so the user can edit the pending request and retry.

Layers 8-10 are internal learning/memory layers that auto-approve after
running their analysis (they store knowledge and learn from the project).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class WorkflowStage(BaseModel):
    """One gated layer step inside a workflow run."""

    key: str
    name: str
    layer: int
    status: str = "pending"  # pending | running | approved | needs_review | failed
    item_id: Optional[str] = None
    board_review_id: Optional[str] = None
    request_sent: str = ""
    verdict: Optional[str] = None  # approved | revision | rejected | failed
    score: Optional[float] = None
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class WorkflowRun(BaseModel):
    """A single cross-layer workflow run."""

    id: str
    name: str
    request: str
    status: str = "running"  # running | needs_review | completed | failed | cancelled
    stage_index: int = 0
    stages: list[WorkflowStage] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    error: str = ""
