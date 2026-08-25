"""Layer 1 - Foundation Knowledge (Britsync AIED).

A central Product Knowledge Base with nine repositories (UI standards, UX
standards, SaaS best practices, landing page library, UX pattern library,
customer psychology, conversion, accessibility, competitor database).

Every other layer consults this store instead of inventing recommendations
independently, so all agents evaluate products against the same standards.
"""

from knowledge.models import (
    AgentBriefing,
    KnowledgeCategory,
    KnowledgeItem,
    KnowledgeRepository,
)
from knowledge.store import KnowledgeStore, KnowledgeStore as Store  # noqa: F401

__all__ = [
    "AgentBriefing",
    "KnowledgeCategory",
    "KnowledgeItem",
    "KnowledgeRepository",
    "KnowledgeStore",
    "Store",
]
