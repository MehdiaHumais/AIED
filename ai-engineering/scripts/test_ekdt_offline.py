"""Offline test for the Layer 10 EKDT engine (no LLM calls)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ekdt.engine import (
    _bullets,
    _find_section,
    _find_section_until,
    _parse_department_output,
    _parse_knowledge_status,
    _parse_twin_package,
    _salvage_department_text,
    _status_from_score,
    EkdtDivision,
)
from ekdt.models import DigitalTwinReport, EkdtDepartmentReport
from ekdt.prompts import (
    EKDT_DEPARTMENTS,
    EKDT_DEPARTMENTS_LIST,
    EKDT_ORDER,
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
- product identity resolved - pass
- decision history searched - pass
- duplicate knowledge found - 2 entries
## FINDINGS
- The invoice product has no recurring invoices in its twin.
- Decision memory lacks the expected outcome for the widget removal.
## RECOMMENDATIONS
- Log the recurring invoices decision with its expected outcome.
- Link the recurring invoice feature to payment automation.
## EVIDENCE
- Product history from the last three builds.
- Customer records for small accounting firms.

The twin is richer after this update.
"""

parsed = _parse_department_output(DEPT_TEXT)
check("dept verdict", parsed["verdict"] == "recommend")
check("dept confidence", parsed["confidence"] == 0.7)
check("dept score", parsed["score"] == 64)
check("dept checks", len(parsed["checks"]) == 3 and "product identity resolved - pass" in parsed["checks"])
check("dept findings", len(parsed["findings"]) == 2)
check("dept recommendations", len(parsed["recommendations"]) == 2)
check("dept evidence", len(parsed["evidence"]) >= 2)

salvaged = _salvage_department_text("Some loose twin text about the product.\n- an item to capture\n- another item")
check("salvage checks", len(salvaged["checks"]) >= 2)
check("salvage verdict", salvaged["verdict"] == "caution")
check("salvage confidence", salvaged["confidence"] == 0.3)
check("salvage report kept", "loose twin text" in salvaged["report"])

# --- knowledge status parsing ---

check("status Optimal", _parse_knowledge_status("## Knowledge Status\nOptimal\n\nThe twin is current.") == "Optimal")
check("status Actionable", _parse_knowledge_status("## Knowledge Status\nActionable\n\nEnrich the customer twin.") == "Actionable")
check("status Stale", _parse_knowledge_status("## Knowledge Status\nStale\n\nRefresh the product twin.") == "Stale")
check("status pending", _parse_knowledge_status("## Unrelated\nNothing here.") == "pending")
check("status inline", _parse_knowledge_status("## Knowledge Status: Actionable") == "Actionable")
check("status optimal beats actionable", _parse_knowledge_status("## Knowledge Status\nOptimal Actionable") == "Optimal")

check("fallback 80 -> Optimal", _status_from_score(80) == "Optimal")
check("fallback 60 -> Actionable", _status_from_score(60) == "Actionable")
check("fallback 40 -> Stale", _status_from_score(40) == "Stale")
check("fallback none -> Actionable", _status_from_score(None) == "Actionable")

# --- package / architect output parsing ---

ARCHITECT_TEXT = """## Overall Knowledge Score
78. The twin is current across products, customers, and decisions, with minor gaps in processes.

## Knowledge Status
Actionable
- The twin is accurate; enrich process automation and refresh two stale patterns.

## Organizational Twin Snapshot
- Technology Division -> Software Development Department -> Frontend Agent Team confirmed.
- React Specialist Agent reporting line updated.

## Product Twin Snapshot
- Invoice SaaS: purpose business invoicing, customers SMEs, React/Node.js/MongoDB.
- Recurring invoices added as current problem; payment automation on roadmap.

## Customer Twin Insights
- Small Accounting Firm: needs fast invoicing and tax reports; pain is manual payment tracking.
- Desired outcome: save 10 hours per month.

## Process Twin Updates
- Invoice process: lead -> invoice -> payment currently manual; automation opportunity found.
- Owner: backend agent; improvement history recorded.

## AI Agent Twin Insights
- UX Research Agent: accuracy 94%, 12 min average completion, strength enterprise SaaS.
- Last improvement: prompt version 7.2.

## Decisions Logged
- Remove advanced dashboard widgets - reason: simplify; evidence: low usage; lesson: simplification lifts engagement.

## Knowledge Graph Links
- Recurring Invoice Feature -> requires -> Payment Automation.
- Payment Automation -> drives -> Customer Retention.

## Semantic Answers
- Q: what problems did customers have with invoicing? A: manual payment tracking, no recurring invoices.

## Proven Patterns
- Three-step onboarding raised activation 45% - reusable template.

## Detected Patterns
- Enterprise customers always request audit logs.
- Users abandon long forms.

## Predictions
- New CRM project: high risk of complexity overload - launch CRM Lite first.

## Knowledge Actions
- Dedupe two stale onboarding patterns - owner: Experience Repository.
- Link invoice feature to payment automation - owner: Knowledge Graph.

## Knowledge Quality
- accuracy check - pass; freshness - 2 items scheduled for refresh.
- permissions and classification - updated.

## Knowledge Brief
Twin health 78/100. Captured the invoice SaaS product identity, the small
accounting firm customer segment, and the payment automation opportunity. Top
signal: enterprise customers request audit logs. Biggest gap: process twin
needs automation history. Divisions should rely on the decision memory for
prior simplification outcomes.

## Executive Summary
The twin is current at 78/100 with Actionable status. The invoice SaaS product
identity, its SME customers, and the payment automation opportunity are now
captured, and decision memory now retrieves why widgets were removed. Enrich
process automation and refresh two stale patterns next.
"""

pkg = _parse_twin_package(ARCHITECT_TEXT)
check("pkg knowledge score", pkg["knowledge_score"] == 78)
check("pkg knowledge status", pkg["knowledge_status"] == "Actionable")
check("pkg org snapshot", any("Software Development" in x for x in pkg["org_snapshot"]))
check("pkg product snapshot", len(pkg["product_snapshot"]) == 2)
check("pkg customer insights", any("Small Accounting Firm" in x for x in pkg["customer_insights"]))
check("pkg process updates", len(pkg["process_updates"]) == 2)
check("pkg agent insights", any("UX Research Agent" in x for x in pkg["agent_insights"]))
check("pkg decisions logged", len(pkg["decisions_logged"]) == 1)
check("pkg knowledge links", len(pkg["knowledge_links"]) == 2)
check("pkg semantic answers", any("manual payment tracking" in x for x in pkg["semantic_answers"]))
check("pkg proven patterns", any("45%" in x for x in pkg["proven_patterns"]))
check("pkg detected patterns", len(pkg["detected_patterns"]) == 2)
check("pkg predictions", any("CRM" in x for x in pkg["predictions"]))
check("pkg knowledge actions", len(pkg["knowledge_actions"]) == 2)
check("pkg knowledge quality", len(pkg["knowledge_quality"]) == 2)
check("brief has score", "78/100" in pkg["knowledge_brief"])
check("brief stops before exec", "Executive Summary" not in pkg["knowledge_brief"])
check("pkg exec summary", "Actionable" in " ".join(pkg["executive_summary"].split()))

check("find_section exact", "React/Node.js/MongoDB" in _find_section(ARCHITECT_TEXT, "Product Twin Snapshot"))
check("find_section until", "78/100" in _find_section_until(ARCHITECT_TEXT, "Knowledge Brief", ["Executive Summary"]))
check("bullets strips dashes", _bullets("- item\n- item2") == ["item", "item2"])

# --- registry integrity ---

check("12 knowledge systems total", len(EKDT_DEPARTMENTS) == 12)
check("11 evidence systems", len(EKDT_DEPARTMENTS_LIST) == 11)
check("12 in order", len(EKDT_ORDER) == 12)
check("architect is coordinator", EKDT_ORDER[-1] == "knowledge-architect")
check("architect excluded from evidence list", "knowledge-architect" not in EKDT_DEPARTMENTS_LIST)
check("order has no dupes", len(EKDT_ORDER) == len(set(EKDT_ORDER)))
check("order matches registry", set(EKDT_ORDER) == set(EKDT_DEPARTMENTS))
check("every system has prompt", all(EKDT_DEPARTMENTS[d]["prompt"] for d in EKDT_DEPARTMENTS))
check("every system has title", all(EKDT_DEPARTMENTS[d]["title"] for d in EKDT_DEPARTMENTS))
check("subject types", SUBJECT_TYPES == ["idea", "project", "customer", "process", "enterprise"])

# --- engine run with a stub LLM + gap-fill + deterministic status ---

class StubConfig:
    version = "test"


class StubLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
        self.calls += 1
        system = messages[0]["content"]
        if system.startswith("You are the Knowledge Architect Agent"):
            return ARCHITECT_TEXT
        return DEPT_TEXT


class StubKB:
    def briefing_markdown(self, text, max_items=5):
        return "## Company Standards\n- security standards\n- compliance playbooks"


async def main():
    llm = StubLLM()
    with tempfile.TemporaryDirectory() as tmp:
        div = EkdtDivision(StubConfig(), llm, kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result = await div.run_review_sync("Twin the new Invoice SaaS product idea for SME customers.", subject_type="idea")

    p = result
    check("engine status completed", p["status"] == "completed")
    check("engine stage done", p["stage"] == "done")
    check("engine has 12 reports", len(p["reports"]) == 12)
    check("engine knowledge score", p["knowledge_score"] == 78)
    check("engine knowledge status", p["knowledge_status"] == "Actionable")
    check("engine report_markdown non-empty", len(p["report_markdown"]) > 100)
    check("engine total_checks", p["total_checks"] >= 3)
    check("engine total_findings", p["total_findings"] >= 2)
    check("engine avg_confidence", p["avg_confidence"] == 0.7)
    check("engine product snapshot filled", len(p["product_snapshot"]) >= 1)
    check("engine decisions filled", len(p["decisions_logged"]) >= 1)
    check("engine knowledge links filled", len(p["knowledge_links"]) >= 1)
    check("engine predictions filled", len(p["predictions"]) >= 1)
    check("engine knowledge brief", "78/100" in p["knowledge_brief"])
    check("engine exec summary", "78/100" in p["executive_summary"])
    check("engine report id", len(p["id"]) == 36)

    # --- stats and list endpoints ---
    stats = div.stats()
    check("stats total", stats["total"] == 1)
    check("stats completed", stats["completed"] == 1)
    check("stats avg knowledge", stats["avg_knowledge_score"] == 78)
    check("stats departments", stats["departments"] == 11)
    check("stats subject types", "idea" in stats["subject_types"])
    check("stats orgs", stats["organizations"] >= 1)
    check("stats active products", stats["active_products"] == 1)
    check("stats ai agents", stats["ai_agents"] >= 1)
    check("stats knowledge items", stats["knowledge_items"] >= 5)
    check("stats successful patterns", stats["successful_patterns"] >= 1)
    check("stats decisions stored", stats["decisions_stored"] >= 1)
    check("stats active projects", stats["active_projects"] == 1)
    check("stats predictive alerts", stats["predictive_alerts"] >= 1)
    check("stats learning updates", stats["learning_updates"] >= 2)
    check("stats knowledge links", stats["knowledge_links"] >= 1)
    check("stats knowledge health", stats["knowledge_health"] == 78)
    check("stats twin status", stats["twin_status"] == "Healthy")

    listed = div.list_reports()
    check("list has report", len(listed) == 1 and listed[0]["knowledge_status"] == "Actionable")
    check("list departments_completed", listed[0]["departments_completed"] == 12)
    check("list total_departments", listed[0]["total_departments"] == 12)
    check("list predictions", listed[0]["predictions"] >= 1)
    check("list patterns", listed[0]["patterns"] >= 1)
    check("list decisions", listed[0]["decisions"] >= 1)

    # --- architect failure still produces a deterministic status ---
    class FailArchitectLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            system = messages[0]["content"]
            if system.startswith("You are the Knowledge Architect Agent"):
                raise RuntimeError("Rate limited (429). Retry after 60s., reset=1786060800000, remaining=0")
            return DEPT_TEXT

    with tempfile.TemporaryDirectory() as tmp:
        div2 = EkdtDivision(StubConfig(), FailArchitectLLM(), kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result2 = await div2.run_review_sync("Twin the new Invoice SaaS product idea.", subject_type="idea")
    check("fallback status completed", result2["status"] == "completed")
    check("fallback status deterministic", result2["knowledge_status"] in ("Optimal", "Actionable", "Stale"))
    check("fallback knowledge score set", result2["knowledge_score"] is not None)
    check("fallback product snapshot filled from depts", len(result2["product_snapshot"]) >= 1)
    check("fallback decisions filled from depts", len(result2["decisions_logged"]) >= 1)
    check("fallback brief deterministic", "Twin health" in result2["knowledge_brief"])

    # --- all-systems-fail marks report failed ---
    class AlwaysFailLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            raise RuntimeError("Rate limited (429). reset=1786060800000, remaining=0")

    with tempfile.TemporaryDirectory() as tmp:
        div3 = EkdtDivision(StubConfig(), AlwaysFailLLM(), kb=None, data_file=os.path.join(tmp, "reports.json"))
        result3 = await div3.run_review_sync("Twin a process.", subject_type="process")
    check("all-fail status failed", result3["status"] == "failed")
    check("all-fail error mentions LLM", "LLM" in (result3["error"] or ""))

    # --- department card apply + delete ---
    dept_report = EkdtDepartmentReport(
        department_id="product-twin",
        department_name="Product Digital Twin",
        department_title="Product Digital Twin",
    )
    div._apply_parsed(dept_report, parsed)
    check("apply_parsed sets fields", dept_report.verdict == "recommend" and dept_report.score == 64 and dept_report.status == "completed")
    check("findings_text", "recurring invoices" in dept_report.findings_text())

    rid = p["id"]
    check("get_report works", div.get_report(rid) is not None)
    check("get_report_dict", div.get_report_dict(rid)["id"] == rid)
    check("delete_report", div.delete_report(rid) is True)
    check("delete_report twice", div.delete_report(rid) is False)

    # --- board request text carries the status ---
    br = DigitalTwinReport(id=rid, request="x", knowledge_status="Actionable", executive_summary="Actionable twin update.")
    check("board text status", "Actionable" in div.board_request_text(br))
    check("board text carries request", div.board_request_text(br).startswith("x"))

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
