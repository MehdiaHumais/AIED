"""Layer 8 - Intelligence, Learning & Continuous Improvement Division (ILCID).

Eleven intelligence departments run on a learning subject (a completed project,
a release, a product, the whole organization, or a specific learning topic),
and the Intelligence Director merges their findings into one Project
Intelligence Report: project summary, objectives achieved, customer impact,
business impact, feature adoption, support trends, performance, security, UX
outcomes, growth outcomes, lessons learned, process improvements, updated
standards, future recommendations, and confidence levels - plus an
organization-wide knowledge graph and executive summary. The report becomes
the organizational memory and continuous improvement engine every other
division learns from. This division does not create products; it makes every
other division smarter.
"""

from intelligence.engine import IntelligenceDivision
from intelligence.models import IntelligenceDepartmentReport, IntelligenceReport
from intelligence.prompts import (
    INTELLIGENCE_DEPARTMENTS,
    INTELLIGENCE_DEPARTMENTS_LIST,
    INTELLIGENCE_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "IntelligenceDivision",
    "IntelligenceDepartmentReport",
    "IntelligenceReport",
    "INTELLIGENCE_DEPARTMENTS",
    "INTELLIGENCE_DEPARTMENTS_LIST",
    "INTELLIGENCE_ORDER",
    "SUBJECT_TYPES",
]
