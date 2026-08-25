"""Layer 4 - UX & Human Experience Division (UXHED).

Eleven UX departments review a product surface - journey, workflows,
information architecture, navigation, onboarding, micro interactions,
accessibility, mobile experience, psychology, microcopy, and usability
testing - and the UX Director merges their findings into one consolidated
UX Review Report plus an implementation-ready specification for the
Development Division.
"""

from ux.engine import UXDivision
from ux.models import UXDepartmentReport, UXReview
from ux.prompts import (
    UX_DEPARTMENTS,
    UX_DEPARTMENTS_LIST,
    UX_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "UXDivision",
    "UXDepartmentReport",
    "UXReview",
    "UX_DEPARTMENTS",
    "UX_DEPARTMENTS_LIST",
    "UX_ORDER",
    "SUBJECT_TYPES",
]
