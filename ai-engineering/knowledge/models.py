"""Layer 1 - Foundation Knowledge. Data models for the Product Knowledge Base.

Repositories store the company's product standards so every agent evaluates
software against the same rules instead of inventing recommendations independently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class KnowledgeItem(BaseModel):
    """A single rule / pattern / observation inside a repository."""

    id: str = Field(default_factory=lambda: "")
    title: str
    summary: str = ""
    content: str = ""
    rules: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=_now)


class KnowledgeCategory(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    items: list[KnowledgeItem] = Field(default_factory=list)


class KnowledgeRepository(BaseModel):
    """One of the nine Layer 1 repositories."""

    id: str
    name: str
    description: str = ""
    icon: str = "BookOpen"
    accent: str = "blue"
    tags: list[str] = Field(default_factory=list)
    categories: list[KnowledgeCategory] = Field(default_factory=list)
    updated_at: str = Field(default_factory=_now)

    @property
    def item_count(self) -> int:
        return sum(len(c.items) for c in self.categories)


class AgentBriefing(BaseModel):
    """Snapshot of Layer 1 knowledge relevant to an agent's task."""

    task_type: str
    matched_repositories: list[str]
    items: list[KnowledgeItem]
    summary: str = ""
