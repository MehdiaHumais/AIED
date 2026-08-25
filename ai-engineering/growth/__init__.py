"""Layer 6 - Growth, Conversion & Customer Success Division (GCCSD).

Eleven growth departments cover the entire customer lifecycle - conversion
optimization, landing page intelligence, customer acquisition, onboarding &
activation, customer success, retention & engagement, pricing & monetization,
customer feedback intelligence, product analytics, experimentation, and trust
& credibility - and the Growth Director merges their findings into one Growth
Intelligence Report: an implementation-ready spec the Frontend and Backend
Development Agents build against. Everything is measured; nothing is based on
opinions. This division optimizes growth; it never builds features itself.
"""

from growth.engine import GrowthDivision
from growth.models import GrowthDepartmentReport, GrowthReviewPackage
from growth.prompts import (
    GROWTH_DEPARTMENTS,
    GROWTH_DEPARTMENTS_LIST,
    GROWTH_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "GrowthDivision",
    "GrowthDepartmentReport",
    "GrowthReviewPackage",
    "GROWTH_DEPARTMENTS",
    "GROWTH_DEPARTMENTS_LIST",
    "GROWTH_ORDER",
    "SUBJECT_TYPES",
]
