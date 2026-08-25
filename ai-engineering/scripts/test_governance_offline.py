"""Offline test for the Layer 9 governance engine (no LLM calls)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from governance.engine import (
    _bullets,
    _decision_from_score,
    _find_section,
    _find_section_until,
    _parse_department_output,
    _parse_final_decision,
    _parse_package,
    _salvage_department_text,
    GovernanceDivision,
)
from governance.models import GovernanceDepartmentReport, OperationsReport
from governance.prompts import (
    GOVERNANCE_DEPARTMENTS,
    GOVERNANCE_DEPARTMENTS_LIST,
    GOVERNANCE_ORDER,
    SUBJECT_TYPES,
)

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name}")


# --- department output parsing ---

DEPT_TEXT = """## VERDICT: recommend
## CONFIDENCE: 0.7
## SCORE: 64
## CHECKS
- required divisions identified - pass
- frontend gated on UX + UI approval - pass
- invoice module assigned to backend agent - pass
## FINDINGS
- The orchestrator would over-activate if not told to prune the roster.
- UX and Compliance disagree on how many fields the form collects.
## RECOMMENDATIONS
- Route frontend work only after UX and UI approval.
- Reserve the expensive model for the Executive Product Board review.
## EVIDENCE
- Agent registry availability data.
- Workflow history from the last three builds.

The operation is orchestratable with two fixes.
"""

parsed = _parse_department_output(DEPT_TEXT)
check("dept verdict", parsed["verdict"] == "recommend")
check("dept confidence", parsed["confidence"] == 0.7)
check("dept score", parsed["score"] == 64)
check("dept checks", len(parsed["checks"]) == 3 and "required divisions identified - pass" in parsed["checks"])
check("dept findings", len(parsed["findings"]) == 2)
check("dept recommendations", len(parsed["recommendations"]) == 2)
check("dept evidence", len(parsed["evidence"]) >= 2)

salvaged = _salvage_department_text("Some loose text about the operation.\n- an action item\n- another action item")
check("salvage checks", len(salvaged["checks"]) >= 2)
check("salvage verdict", salvaged["verdict"] == "caution")
check("salvage confidence", salvaged["confidence"] == 0.3)
check("salvage report kept", "loose text" in salvaged["report"])

# --- final decision parsing ---

check("decision Approved", _parse_final_decision("## Final Decision\nApproved\n\nProceed end to end.") == "Approved")
check("decision Conditional", _parse_final_decision("## Final Decision\nConditional Approval\n\nFix the dependency first.") == "Conditional Approval")
check("decision Not Approved", _parse_final_decision("## Final Decision\nNot Approved\n\nBlocked on policy violation.") == "Not Approved")
check("decision pending", _parse_final_decision("## Unrelated\nNothing here.") == "pending")
check("decision inline", _parse_final_decision("## Final Decision: Conditional Approval") == "Conditional Approval")
check("decision not-approved not approved", _parse_final_decision("## Final Decision: Not Approved") == "Not Approved")

check("fallback 80 -> Approved", _decision_from_score(80) == "Approved")
check("fallback 60 -> Approved", _decision_from_score(60) == "Approved")
check("fallback 50 -> Conditional", _decision_from_score(50) == "Conditional Approval")
check("fallback 30 -> Not Approved", _decision_from_score(30) == "Not Approved")
check("fallback none -> Conditional", _decision_from_score(None) == "Conditional Approval")

# --- package / director output parsing ---

DIRECTOR_TEXT = """## Overall Governance Score
78. The operation is orchestratable with a clear schedule and minor policy fixes.

## Final Decision
Conditional Approval
- Approve after the frontend dependency gate is enforced.

## Required Divisions
- Executive Product Board -> kickoff
- Research -> then UX, Growth, Competitor Review in parallel
- Development -> after UX and UI approval
- QA -> after development
- Deployment -> after release approval

## Work Packages
- Business Analysis -> analyst agent
- Invoices -> backend agent
- Payments -> backend agent
- Dashboard -> frontend agent

## Agent Assignments
- Invoices -> backend agent
- Dashboard -> frontend agent
- Reporting -> data agent

## Capability Matches
- Invoices -> backend agent (accounting skills, past performance 92%)
- Dashboard -> frontend agent (UI library expertise)

## Arbitration Rulings
- UX vs Compliance on form fields -> rule for Compliance on regulatory fields, UX on optional ones.

## Resource Plan
- Use mid-tier model for invoice generation; reserve frontier model for the board review.

## Dependency Map
- Frontend cannot start until UX AND UI approve.
- QA cannot start until development completes.

## Schedule
- Run UX, Growth, and Competitor Review in parallel after Research.

## Policy Compliance
- Naming conventions - pass.
- Frontend dependency gate - not enforced yet.

## Performance Insights
- Backend agent latency 1.1s, hallucination rate 2%, acceptance 89%.

## Audit Trail
- Workflow history recorded for the last 3 builds; approvals logged.

## Operational Alerts
- Frontend dependency gate unenforced - owner: Workflow Scheduler.

## Enterprise KPIs
- agent utilization: 74%
- policy compliance: 96%

## Approvals
- Approve workflow execution pending the dependency gate fix.

## Executive Operations Brief
Organization health 78/100. Running: Invoice build with 4 agents. Blocked:
frontend gate. Top risk: unenforced dependency. Release pipeline: one build
queued behind QA.

## Executive Summary
The invoice operation is orchestratable at 78/100. The decision is Conditional
Approval - the frontend dependency gate must be enforced before work starts.
Running UX, Growth, and Competitor Review in parallel cuts delivery time.
"""

pkg = _parse_package(DIRECTOR_TEXT)
check("pkg governance score", pkg["governance_score"] == 78)
check("pkg final decision", pkg["final_decision"] == "Conditional Approval")
check("pkg required divisions", len(pkg["required_divisions"]) == 5)
check("pkg work packages", any("Invoices" in x for x in pkg["work_packages"]))
check("pkg agent assignments", len(pkg["agent_assignments"]) == 3)
check("pkg arbitration rulings", len(pkg["arbitration_rulings"]) == 1)
check("pkg resource plan", len(pkg["resource_plan"]) == 1)
check("pkg dependency map", len(pkg["dependency_map"]) == 2)
check("pkg schedule", len(pkg["schedule"]) == 1)
check("pkg policy compliance", len(pkg["policy_compliance"]) == 2)
check("pkg enterprise kpis", len(pkg["enterprise_kpis"]) == 2)
check("pkg approvals", len(pkg["approvals"]) == 1)
check("pkg operations brief", "78/100" in pkg["operations_brief"])
check("brief stops before exec", "Executive Summary" not in pkg["operations_brief"])
check("pkg exec summary", "Conditional Approval" in " ".join(pkg["executive_summary"].split()))

check("find_section exact", "Executive Product Board -> kickoff" in _find_section(DIRECTOR_TEXT, "Required Divisions"))
check("find_section until", "78/100" in _find_section_until(DIRECTOR_TEXT, "Executive Operations Brief", ["Executive Summary"]))
check("bullets strips dashes", _bullets("- item\n- item2") == ["item", "item2"])

# --- registry integrity ---

check("13 departments total", len(GOVERNANCE_DEPARTMENTS) == 13)
check("12 evidence departments", len(GOVERNANCE_DEPARTMENTS_LIST) == 12)
check("13 in order", len(GOVERNANCE_ORDER) == 13)
check("director is coordinator", GOVERNANCE_ORDER[-1] == "chief-ai-ops-director")
check("director excluded from evidence list", "chief-ai-ops-director" not in GOVERNANCE_DEPARTMENTS_LIST)
check("order has no dupes", len(GOVERNANCE_ORDER) == len(set(GOVERNANCE_ORDER)))
check("order matches registry", set(GOVERNANCE_ORDER) == set(GOVERNANCE_DEPARTMENTS))
check("every dept has prompt", all(GOVERNANCE_DEPARTMENTS[d]["prompt"] for d in GOVERNANCE_DEPARTMENTS))
check("every dept has title", all(GOVERNANCE_DEPARTMENTS[d]["title"] for d in GOVERNANCE_DEPARTMENTS))
check("subject types", SUBJECT_TYPES == ["operation", "workflow", "conflict", "enterprise"])

# --- engine run with a stub LLM + gap-fill + deterministic decision ---

class StubConfig:
    version = "test"


class StubLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
        self.calls += 1
        system = messages[0]["content"]
        if system.startswith("You are the Chief AI Operations Director"):
            return DIRECTOR_TEXT
        return DEPT_TEXT


class StubKB:
    def briefing_markdown(self, text, max_items=5):
        return "## Company Standards\n- security standards\n- compliance playbooks"


async def main():
    llm = StubLLM()
    with tempfile.TemporaryDirectory() as tmp:
        div = GovernanceDivision(StubConfig(), llm, kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result = await div.run_review_sync("Build an ERP for manufacturing.", subject_type="operation")

    p = result
    check("engine status completed", p["status"] == "completed")
    check("engine stage done", p["stage"] == "done")
    check("engine has 13 reports", len(p["reports"]) == 13)
    check("engine governance score", p["governance_score"] == 78)
    check("engine final decision", p["final_decision"] == "Conditional Approval")
    check("engine report_markdown non-empty", len(p["report_markdown"]) > 100)
    check("engine total_checks", p["total_checks"] >= 3)
    check("engine total_findings", p["total_findings"] >= 2)
    check("engine avg_confidence", p["avg_confidence"] == 0.7)
    check("engine required divisions filled", len(p["required_divisions"]) >= 1)
    check("engine dependency map filled", len(p["dependency_map"]) >= 1)
    check("engine operations brief", "78/100" in p["operations_brief"])
    check("engine exec summary", "invoice operation" in " ".join(p["executive_summary"].split()))
    check("engine report id", len(p["id"]) == 36)

    # --- stats and list endpoints ---
    stats = div.stats()
    check("stats total", stats["total"] == 1)
    check("stats completed", stats["completed"] == 1)
    check("stats avg governance", stats["avg_governance_score"] == 78)
    check("stats decisions", stats["final_decisions"]["conditional"] == 1)
    check("stats departments", stats["departments"] == 12)
    check("stats subject types", "operation" in stats["subject_types"])
    check("stats org health", stats["organization_health"] == 78)
    check("stats critical risks", stats["critical_risks"] >= 1)
    check("stats infra status", stats["infrastructure_status"] == "Attention")

    listed = div.list_reports()
    check("list has report", len(listed) == 1 and listed[0]["final_decision"] == "Conditional Approval")
    check("list departments_completed", listed[0]["departments_completed"] == 13)
    check("list total_departments", listed[0]["total_departments"] == 13)
    check("list alerts", listed[0]["alerts"] >= 1)

    # --- director failure still produces a deterministic decision ---
    class FailDirectorLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            system = messages[0]["content"]
            if system.startswith("You are the Chief AI Operations Director"):
                raise RuntimeError("Rate limited (429). Retry after 60s., reset=1786060800000, remaining=0")
            return DEPT_TEXT

    with tempfile.TemporaryDirectory() as tmp:
        div2 = GovernanceDivision(StubConfig(), FailDirectorLLM(), kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result2 = await div2.run_review_sync("Build an ERP for manufacturing.", subject_type="operation")
    check("fallback status completed", result2["status"] == "completed")
    check("fallback decision deterministic", result2["final_decision"] in ("Approved", "Conditional Approval", "Not Approved"))
    check("fallback governance score set", result2["governance_score"] is not None)
    check("fallback work packages filled from depts", len(result2["work_packages"]) >= 1)
    check("fallback required divisions filled from depts", len(result2["required_divisions"]) >= 1)
    check("fallback brief deterministic", "Organization health" in result2["operations_brief"])

    # --- all-departments-fail marks report failed ---
    class AlwaysFailLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            raise RuntimeError("Rate limited (429). reset=1786060800000, remaining=0")

    with tempfile.TemporaryDirectory() as tmp:
        div3 = GovernanceDivision(StubConfig(), AlwaysFailLLM(), kb=None, data_file=os.path.join(tmp, "reports.json"))
        result3 = await div3.run_review_sync("Build an ERP.", subject_type="operation")
    check("all-fail status failed", result3["status"] == "failed")
    check("all-fail error mentions LLM", "LLM" in (result3["error"] or ""))

    # --- department card apply + delete ---
    dept_report = GovernanceDepartmentReport(
        department_id="workflow-orchestrator",
        department_name="AI Workflow Orchestrator",
        department_title="AI Workflow Orchestrator",
    )
    div._apply_parsed(dept_report, parsed)
    check("apply_parsed sets fields", dept_report.verdict == "recommend" and dept_report.score == 64 and dept_report.status == "completed")
    check("findings_text", "over-activate" in dept_report.findings_text())

    rid = p["id"]
    check("get_report works", div.get_report(rid) is not None)
    check("get_report_dict", div.get_report_dict(rid)["id"] == rid)
    check("delete_report", div.delete_report(rid) is True)
    check("delete_report twice", div.delete_report(rid) is False)

    # --- board request text carries the decision ---
    br = OperationsReport(id=rid, request="x", final_decision="Conditional Approval", executive_summary="Conditional decision.")
    check("board text decision", "Conditional Approval" in div.board_request_text(br))
    check("board text carries request", div.board_request_text(br).startswith("x"))

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
