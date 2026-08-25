"""Layer 10 - Enterprise Knowledge & Digital Twin Platform (EKDT).

A living digital representation of the entire organization - businesses,
products, projects, processes, employees, AI agents, customers, decisions,
standards, knowledge, performance, and historical lessons. The single source of
truth for the entire AI enterprise. The system remembers why things exist:
knowledge -> relationships -> context -> reasoning -> decisions -> actions ->
learning. It sits underneath everything - every agent connects to EKDT before
it works.

Eleven knowledge systems run on an enterprise knowledge subject (a new idea, a
project, a customer, a process, or an enterprise-wide refresh), and the
Knowledge Architect Agent merges their findings into one Digital Twin Update
Report: organizational snapshot, product snapshot, customer insights, process
updates, agent insights, decisions logged, knowledge graph links, semantic
answers, proven patterns, detected patterns, predictions, knowledge actions,
and knowledge quality - plus a Knowledge Brief for the CEO.
"""

from ekdt.engine import EkdtDivision
from ekdt.models import DigitalTwinReport, EkdtDepartmentReport
from ekdt.prompts import (
    EKDT_DEPARTMENTS,
    EKDT_DEPARTMENTS_LIST,
    EKDT_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "EkdtDivision",
    "DigitalTwinReport",
    "EkdtDepartmentReport",
    "EKDT_DEPARTMENTS",
    "EKDT_DEPARTMENTS_LIST",
    "EKDT_ORDER",
    "SUBJECT_TYPES",
]
