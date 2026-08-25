"""Layer 9 - Enterprise AI Governance & Orchestration Division (EAGOD).

Twelve operations departments run on an enterprise operation request (a build
request, a workflow to optimize, a conflict to arbitrate, or an enterprise-wide
health review), and the Chief AI Operations Director merges their findings into
one Division Operations Report: required divisions, work packages, agent
assignments, capability matches, arbitration rulings, resource plan, dependency
map, schedule, policy compliance, performance insights, audit trail,
operational alerts, enterprise KPIs, and approvals - plus an Executive
Operations Brief the CEO reads live. The division governs, orchestrates,
coordinates, monitors, and optimizes every AI agent, workflow, and decision
across the enterprise. It does not replace the CEO; it is the Chief Operating
Office for the AI workforce, and no department bypasses this layer.
"""

from governance.engine import GovernanceDivision
from governance.models import GovernanceDepartmentReport, OperationsReport
from governance.prompts import (
    GOVERNANCE_DEPARTMENTS,
    GOVERNANCE_DEPARTMENTS_LIST,
    GOVERNANCE_ORDER,
    SUBJECT_TYPES,
)

__all__ = [
    "GovernanceDivision",
    "GovernanceDepartmentReport",
    "OperationsReport",
    "GOVERNANCE_DEPARTMENTS",
    "GOVERNANCE_DEPARTMENTS_LIST",
    "GOVERNANCE_ORDER",
    "SUBJECT_TYPES",
]
