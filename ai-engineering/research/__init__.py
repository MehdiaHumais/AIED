"""Layer 3 - Product Research & Discovery Division (PRDD).

Ten research departments gather evidence about customer needs, market
opportunities, competitors, missing features, positioning, trends, pricing,
and industry standards. The Research Coordinator merges their findings into
a single standardized research dossier for the Executive Product Board.
"""

from research.engine import ResearchDivision
from research.models import DepartmentReport, ResearchDossier
from research.prompts import (
    RESEARCH_DEPARTMENTS,
    RESEARCH_DEPARTMENTS_LIST,
    RESEARCH_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "ResearchDivision",
    "DepartmentReport",
    "ResearchDossier",
    "RESEARCH_DEPARTMENTS",
    "RESEARCH_DEPARTMENTS_LIST",
    "RESEARCH_ORDER",
    "SUBJECT_TYPES",
]
