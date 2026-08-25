"""Layer 5 - Visual Design & Design System Division (VDDS).

Twelve design departments define a unified visual language - design system
components, brand identity, UI components, layout and grid, visual hierarchy,
iconography, illustrations, motion, responsive behavior, themes, and design QA
- and the Creative Director merges their specifications into one Visual Design
Package: an implementation-ready guide the Frontend Development Agent builds
against. This division defines visuals; it never writes frontend code.
"""

from design.engine import DesignDivision
from design.models import DesignDepartmentReport, VisualDesignPackage
from design.prompts import (
    DESIGN_DEPARTMENTS,
    DESIGN_DEPARTMENTS_LIST,
    DESIGN_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "DesignDivision",
    "DesignDepartmentReport",
    "VisualDesignPackage",
    "DESIGN_DEPARTMENTS",
    "DESIGN_DEPARTMENTS_LIST",
    "DESIGN_ORDER",
    "SUBJECT_TYPES",
]
