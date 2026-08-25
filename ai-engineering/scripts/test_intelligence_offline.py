"""Offline test for the Layer 8 intelligence engine (no LLM calls)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.engine import (
    _bullets,
    _find_section,
    _find_section_until,
    _parse_department_output,
    _parse_package,
    _salvage_department_text,
    IntelligenceDivision,
)
from intelligence.models import IntelligenceDepartmentReport, IntelligenceReport
from intelligence.prompts import (
    INTELLIGENCE_DEPARTMENTS,
    INTELLIGENCE_DEPARTMENTS_LIST,
    INTELLIGENCE_ORDER,
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

DEPT_TEXT = """## VERDICT: caution
## CONFIDENCE: 0.6
## SCORE: 62
## CHECKS
- project close-out review - pass
- advanced reports conversion - 18%
- prompt v3 failure rate - measured
## FINDINGS
- Users ignored advanced reports for 6 months.
- Invoice search was the most used feature.
## RECOMMENDATIONS
- Move advanced reports into an optional analytics module.
- Add an index on customer_number for the invoice search query.
## EVIDENCE
- Feature analytics for the invoice SaaS.
- Support tickets filed about report search.

The project taught us that advanced reports are ignored.
"""

parsed = _parse_department_output(DEPT_TEXT)
check("dept verdict", parsed["verdict"] == "caution")
check("dept confidence", parsed["confidence"] == 0.6)
check("dept score", parsed["score"] == 62)
check("dept checks", len(parsed["checks"]) == 3 and "project close-out review - pass" in parsed["checks"])
check("dept findings", len(parsed["findings"]) == 2)
check("dept recommendations", len(parsed["recommendations"]) == 2)
check("dept evidence", len(parsed["evidence"]) >= 2)

salvaged = _salvage_department_text("Some loose text about the subject.\n- an action item\n- another action item")
check("salvage checks", len(salvaged["checks"]) >= 2)
check("salvage verdict", salvaged["verdict"] == "caution")
check("salvage confidence", salvaged["confidence"] == 0.3)
check("salvage report kept", "loose text" in salvaged["report"])

# --- package / director output parsing ---

DIRECTOR_TEXT = """## Overall Intelligence Score
74. The project delivered strong business value and the lessons make the next project faster.

## Project Summary
- Invoice SaaS delivered on time with high adoption.

## Objectives Achieved
- Automated accounting workflows - achieved.

## Customer Impact
- Invoice search adoption at 92%.

## Business Impact
- Billing time cut from 2h to 25m per month.

## Feature Adoption
- Invoice search used daily - high adoption.

## Support Trends
- Ticket volume down 40% after the search release.

## Performance
- Invoice search 4.8s -> 0.3s after indexing.

## Security
- Rate limiting added to the login endpoint.

## UX Outcomes
- Keyboard navigation passes all mandatory checks.

## Growth Outcomes
- Monthly active users up 15% after the release.

## Lessons Learned
- Advanced reports were ignored for 6 months; move them to an optional module.

## Process Improvements
- Run UX and Growth reviews in parallel after Research.

## Updated Standards
- Retire the stale design-system token for report cards.

## Future Recommendations
- Add an index on customer_number for the invoice search query.

## Confidence Levels
- high: advanced reports are ignored (92%)
- medium: split invoice module reduces delay risk (87%)

## Knowledge Graph
Invoice SaaS (product) -> invoice search (feature) -> faster accounting (business goal)
invoice search (feature) -> index customer_number (standard) -> slow search hurts adoption (lesson)
slow search hurts adoption (lesson) -> add index on customer_number (recommendation) -> invoice performance release (future project)

## Executive Summary
The invoice SaaS shipped strong value at 74/100 intelligence. The most important
lesson is that advanced reports were ignored, and the top recommendation moves
them into an optional analytics module. Standards for report cards are updated,
and the next project starts from this knowledge.
"""

pkg = _parse_package(DIRECTOR_TEXT)
check("pkg intelligence score", pkg["intelligence_score"] == 74)
check("pkg project summary", len(pkg["project_summary"]) == 1)
check("pkg objectives", any("automated accounting workflows" in x.lower() for x in pkg["objectives_achieved"]))
check("pkg customer impact", len(pkg["customer_impact"]) == 1)
check("pkg lessons", len(pkg["lessons_learned"]) == 1)
check("pkg updated standards", len(pkg["updated_standards"]) == 1)
check("pkg confidence levels", len(pkg["confidence_levels"]) == 2)
check("pkg exec summary", "74/100" in pkg["executive_summary"])
check("pkg knowledge graph has relationship", "FUTURE PROJECT" not in pkg["knowledge_graph"])
check("pkg knowledge graph non-empty", len(pkg["knowledge_graph"]) > 50)
check("kg stops before exec", "Executive Summary" not in pkg["knowledge_graph"])

check("find_section exact", "Invoice SaaS delivered on time with high adoption." in _find_section(DIRECTOR_TEXT, "Project Summary"))
check("find_section until", "Invoice SaaS (product)" in _find_section_until(DIRECTOR_TEXT, "Knowledge Graph", ["Executive Summary"]))
check("bullets strips dashes", _bullets("- item\n- item2") == ["item", "item2"])

# --- registry integrity ---

check("12 departments total", len(INTELLIGENCE_DEPARTMENTS) == 12)
check("11 evidence departments", len(INTELLIGENCE_DEPARTMENTS_LIST) == 11)
check("12 in order", len(INTELLIGENCE_ORDER) == 12)
check("director is coordinator", INTELLIGENCE_ORDER[-1] == "intelligence-director")
check("director excluded from evidence list", "intelligence-director" not in INTELLIGENCE_DEPARTMENTS_LIST)
check("order has no dupes", len(INTELLIGENCE_ORDER) == len(set(INTELLIGENCE_ORDER)))
check("order matches registry", set(INTELLIGENCE_ORDER) == set(INTELLIGENCE_DEPARTMENTS))
check("every dept has prompt", all(INTELLIGENCE_DEPARTMENTS[d]["prompt"] for d in INTELLIGENCE_DEPARTMENTS))
check("every dept has title", all(INTELLIGENCE_DEPARTMENTS[d]["title"] for d in INTELLIGENCE_DEPARTMENTS))
check("subject types", SUBJECT_TYPES == ["project", "release", "product", "organization", "learning_topic"])

# --- engine run with a stub LLM + gap-fill + director parsing ---

class StubConfig:
    version = "test"


class StubLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
        self.calls += 1
        system = messages[0]["content"]
        if system.startswith("You are the Intelligence Director"):
            return DIRECTOR_TEXT
        return DEPT_TEXT


class StubKB:
    def briefing_markdown(self, text, max_items=5):
        return "## Company Standards\n- security standards\n- compliance playbooks"


async def main():
    llm = StubLLM()
    with tempfile.TemporaryDirectory() as tmp:
        div = IntelligenceDivision(StubConfig(), llm, kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result = await div.run_review_sync("Learn from the completed Invoice SaaS project.", subject_type="project")

    p = result
    check("engine status completed", p["status"] == "completed")
    check("engine stage done", p["stage"] == "done")
    check("engine has 12 reports", len(p["reports"]) == 12)
    check("engine intelligence score", p["intelligence_score"] == 74)
    check("engine report_markdown non-empty", len(p["report_markdown"]) > 100)
    check("engine total_lessons", p["total_lessons"] >= 2)
    check("engine total_recommendations", p["total_recommendations"] >= 2)
    check("engine avg_confidence", p["avg_confidence"] == 0.6)
    check("engine knowledge_graph filled", "Invoice SaaS" in p["knowledge_graph"])
    check("engine exec summary", "74/100" in p["executive_summary"])
    check("engine report id", len(p["id"]) == 36)

    # --- stats and list endpoints ---
    stats = div.stats()
    check("stats total", stats["total"] == 1)
    check("stats completed", stats["completed"] == 1)
    check("stats avg intelligence", stats["avg_intelligence_score"] == 74)
    check("stats departments", stats["departments"] == 11)
    check("stats subject types", "project" in stats["subject_types"])
    check("stats total lessons", stats["total_lessons"] >= 2)

    listed = div.list_reports()
    check("list has report", len(listed) == 1 and listed[0]["intelligence_score"] == 74)
    check("list departments_completed", listed[0]["departments_completed"] == 12)
    check("list total_departments", listed[0]["total_departments"] == 12)

    # --- director failure still produces a deterministic knowledge graph ---
    class FailDirectorLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            system = messages[0]["content"]
            if system.startswith("You are the Intelligence Director"):
                raise RuntimeError("Rate limited (429). Retry after 60s., reset=1786060800000, remaining=0")
            return DEPT_TEXT

    with tempfile.TemporaryDirectory() as tmp:
        div2 = IntelligenceDivision(StubConfig(), FailDirectorLLM(), kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result2 = await div2.run_review_sync("Learn from the completed Invoice SaaS project.", subject_type="project")
    check("fallback status completed", result2["status"] == "completed")
    check("fallback score set", result2["intelligence_score"] is not None)
    check("fallback lessons filled from depts", len(result2["lessons_learned"]) >= 1)
    check("fallback recommendations filled from depts", len(result2["future_recommendations"]) >= 1)
    check("fallback knowledge graph deterministic", "SUBJECT -> PRODUCT/FEATURE" in result2["knowledge_graph"])
    check("fallback exec summary", "Project Intelligence Report completed" in result2["executive_summary"])

    # --- all-departments-fail marks report failed ---
    class AlwaysFailLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            raise RuntimeError("Rate limited (429). reset=1786060800000, remaining=0")

    with tempfile.TemporaryDirectory() as tmp:
        div3 = IntelligenceDivision(StubConfig(), AlwaysFailLLM(), kb=None, data_file=os.path.join(tmp, "reports.json"))
        result3 = await div3.run_review_sync("Learn from a project.", subject_type="project")
    check("all-fail status failed", result3["status"] == "failed")
    check("all-fail error mentions LLM", "LLM" in (result3["error"] or ""))

    # --- department card apply + delete ---
    dept_report = IntelligenceDepartmentReport(
        department_id="organizational-learning",
        department_name="Organizational Learning Department",
        department_title="Organizational Learning Director",
    )
    div._apply_parsed(dept_report, parsed)
    check("apply_parsed sets fields", dept_report.verdict == "caution" and dept_report.score == 62 and dept_report.status == "completed")
    check("findings_text", "advanced reports" in dept_report.findings_text())

    rid = p["id"]
    check("get_report works", div.get_report(rid) is not None)
    check("get_report_dict", div.get_report_dict(rid)["id"] == rid)
    check("delete_report", div.delete_report(rid) is True)
    check("delete_report twice", div.delete_report(rid) is False)

    # --- board request text carries the learning ---
    br = IntelligenceReport(id=rid, request="x", intelligence_score=74, executive_summary="Report done.")
    check("board text carries request", div.board_request_text(br).startswith("x"))
    check("board text mentions report", "Project Intelligence Report" in div.board_request_text(br))

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
