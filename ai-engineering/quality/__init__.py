"""Layer 7 - Quality, Security & Release Excellence Division (QSRED).

Twelve quality departments cover the entire release gate - functional QA,
performance engineering, security review, privacy & compliance, accessibility
validation, release readiness, documentation & knowledge, DevOps quality,
architecture review, production monitoring, incident prevention, and enterprise
readiness - and the Release Director merges their findings into one Release
Excellence Report with a formal Go / Conditional Go / No Go decision and a
release certificate. Nothing reaches customers without approval from this
division; it is the final gate before production.
"""

from quality.engine import QualityDivision
from quality.models import QualityDepartmentReport, ReleaseExcellenceReport
from quality.prompts import (
    QUALITY_DEPARTMENTS,
    QUALITY_DEPARTMENTS_LIST,
    QUALITY_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "QualityDivision",
    "QualityDepartmentReport",
    "ReleaseExcellenceReport",
    "QUALITY_DEPARTMENTS",
    "QUALITY_DEPARTMENTS_LIST",
    "QUALITY_ORDER",
    "SUBJECT_TYPES",
]
