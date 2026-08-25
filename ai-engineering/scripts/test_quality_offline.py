"""Offline test for the Layer 7 quality engine (no LLM calls)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality.engine import (
    _bullets,
    _decision_from_score,
    _find_section,
    _find_section_until,
    _parse_department_output,
    _parse_final_decision,
    _parse_package,
    _salvage_department_text,
    QualityDivision,
)
from quality.models import QualityDepartmentReport, ReleaseExcellenceReport
from quality.prompts import QUALITY_DEPARTMENTS, QUALITY_DEPARTMENTS_LIST, QUALITY_ORDER, SUBJECT_TYPES

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
- authentication flow - pass
- rate limiting - missing
- invoice search 4.8s vs 0.3s target - fail
## FINDINGS
- No rate limiting on the login endpoint.
- Invoice search returns in 4.8s on large accounts.
## RECOMMENDATIONS
- Add an index on customer_number for the invoice search query.
- Add server-side rate limiting to the login endpoint.
## EVIDENCE
- OWASP ASVS rate limiting control.
- Measured API latency in staging.

The release is functional but has blocking issues.
"""

parsed = _parse_department_output(DEPT_TEXT)
check("dept verdict", parsed["verdict"] == "caution")
check("dept confidence", parsed["confidence"] == 0.6)
check("dept score", parsed["score"] == 62)
check("dept checks", len(parsed["checks"]) == 3 and "authentication flow - pass" in parsed["checks"])
check("dept findings", len(parsed["findings"]) == 2)
check("dept recommendations", len(parsed["recommendations"]) == 2)
check("dept evidence", len(parsed["evidence"]) >= 2)

salvaged = _salvage_department_text("Some loose text about the release.\n- an action item\n- another action item")
check("salvage checks", len(salvaged["checks"]) >= 2)
check("salvage verdict", salvaged["verdict"] == "caution")
check("salvage confidence", salvaged["confidence"] == 0.3)
check("salvage report kept", "loose text" in salvaged["report"])

# --- final decision parsing ---

check("decision Go", _parse_final_decision("## Final Decision\nGo\n\nNothing blocks release.") == "Go")
check("decision Conditional Go", _parse_final_decision("## Final Decision\nConditional Go\n\nFix the rate limit first.") == "Conditional Go")
check("decision No Go", _parse_final_decision("## Final Decision\nNo Go\n\nCritical vuln unresolved.") == "No Go")
check("decision pending", _parse_final_decision("## Unrelated\nNothing here.") == "pending")
check("decision inline", _parse_final_decision("## Final Decision: Conditional Go") == "Conditional Go")
check("decision no-go not go", _parse_final_decision("## Final Decision: No Go") == "No Go")

check("fallback 80 -> Go", _decision_from_score(80) == "Go")
check("fallback 60 -> Go", _decision_from_score(60) == "Go")
check("fallback 50 -> Conditional Go", _decision_from_score(50) == "Conditional Go")
check("fallback 30 -> No Go", _decision_from_score(30) == "No Go")
check("fallback none -> Conditional Go", _decision_from_score(None) == "Conditional Go")

# --- package / director output parsing ---

DIRECTOR_TEXT = """## Overall Quality Score
72. The release is solid across the board with two medium risks.

## Release Version
v3.2

## Functional QA
- all business workflows pass except one low-priority issue.

## Performance Review
- dashboard reduced from 2.1s to 0.8s.

## Security Review
- API rate limiting added.

## Compliance Review
- privacy policy updated.

## Accessibility Review
- keyboard navigation passes all mandatory checks.

## Documentation Status
- user guide and API documentation completed.

## Architecture Review
- no long-term concerns identified.

## Deployment Readiness
- rollback plan verified.

## Monitoring Status
- alerts configured.

## Enterprise Readiness
- audit logging and role permissions verified.

## Known Risks
- Low-priority invoice edge case not yet fixed.
- No automated rollback drill performed this cycle.

## Rollback Strategy
- Keep the previous build deployable for one-click rollback.
- Feature flag the invoice search behind release-v3.2.

## Final Decision
Conditional Go
- Ship after the low-priority edge case is fixed.

## Release Certificate
## Release Version: v3.2
## Final Decision: Conditional Go
## Required Fixes
- Fix the low-priority invoice edge case.
## Conditions
- Run one automated rollback drill after deploy.
## Sign-off
Quality, Security & Release Excellence Division - Release Director

## Executive Summary
The release is ready with two conditions. Overall quality score 72/100.
"""

pkg = _parse_package(DIRECTOR_TEXT)
check("pkg quality score", pkg["quality_score"] == 72)
check("pkg release version", pkg["release_version"] == "v3.2")
check("pkg final decision", pkg["final_decision"] == "Conditional Go")
check("pkg functional qa", len(pkg["functional_qa"]) == 1)
check("pkg security", "API rate limiting added." in pkg["security_review"])
check("pkg known risks", len(pkg["known_risks"]) == 2)
check("pkg rollback", len(pkg["rollback_strategy"]) == 2)
check("pkg exec summary", "ready with two conditions" in pkg["executive_summary"])
check("pkg certificate has subheaders", "## Required Fixes" in pkg["release_certificate"])
check("pkg certificate stops before exec", "Executive Summary" not in pkg["release_certificate"])
check("certificate version line", "## Release Version: v3.2" in pkg["release_certificate"])
check("certificate sign-off", "Release Director" in pkg["release_certificate"])

check("find_section exact", "all business workflows pass except one low-priority issue." in _find_section(DIRECTOR_TEXT, "Functional QA"))
check("find_section until", "## Release Version: v3.2" in _find_section_until(DIRECTOR_TEXT, "Release Certificate", ["Executive Summary"]))
check("bullets strips dashes", _bullets("- item\n- item2") == ["item", "item2"])

# --- registry integrity ---

check("13 departments total", len(QUALITY_DEPARTMENTS) == 13)
check("12 evidence departments", len(QUALITY_DEPARTMENTS_LIST) == 12)
check("13 in order", len(QUALITY_ORDER) == 13)
check("director is coordinator", QUALITY_ORDER[-1] == "release-director")
check("director excluded from evidence list", "release-director" not in QUALITY_DEPARTMENTS_LIST)
check("order has no dupes", len(QUALITY_ORDER) == len(set(QUALITY_ORDER)))
check("order matches registry", set(QUALITY_ORDER) == set(QUALITY_DEPARTMENTS))
check("every dept has prompt", all(QUALITY_DEPARTMENTS[d]["prompt"] for d in QUALITY_DEPARTMENTS))
check("every dept has title", all(QUALITY_DEPARTMENTS[d]["title"] for d in QUALITY_DEPARTMENTS))
check("subject types", SUBJECT_TYPES == ["release", "feature", "service", "whole_product", "enterprise"])

# --- engine run with a stub LLM + gap-fill + deterministic decision ---

class StubConfig:
    version = "test"


class StubLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
        self.calls += 1
        system = messages[0]["content"]
        if "Release Director in the Quality" in system:
            return DIRECTOR_TEXT
        return DEPT_TEXT


class StubKB:
    def briefing_markdown(self, text, max_items=5):
        return "## Company Standards\n- security standards\n- compliance playbooks"


async def main():
    llm = StubLLM()
    with tempfile.TemporaryDirectory() as tmp:
        div = QualityDivision(StubConfig(), llm, kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result = await div.run_review_sync("Gate release v3.2 of our recruitment SaaS for production.", subject_type="release")

    p = result
    check("engine status completed", p["status"] == "completed")
    check("engine stage done", p["stage"] == "done")
    check("engine has 13 reports", len(p["reports"]) == 13)
    check("engine quality score", p["quality_score"] == 72)
    check("engine release version", p["release_version"] == "v3.2")
    check("engine final decision", p["final_decision"] == "Conditional Go")
    check("engine report_markdown non-empty", len(p["report_markdown"]) > 100)
    check("engine total_checks", p["total_checks"] >= 3)
    check("engine total_findings", p["total_findings"] >= 2)
    check("engine avg_confidence", p["avg_confidence"] == 0.6)
    check("engine known_risks filled", len(p["known_risks"]) >= 1)
    check("engine rollback filled", len(p["rollback_strategy"]) >= 1)
    check("engine certificate", "## Final Decision" in p["release_certificate"])
    check("engine report id", len(p["id"]) == 36)

    # --- stats and list endpoints ---
    stats = div.stats()
    check("stats total", stats["total"] == 1)
    check("stats completed", stats["completed"] == 1)
    check("stats avg quality", stats["avg_quality_score"] == 72)
    check("stats decisions", stats["final_decisions"]["conditional_go"] == 1)
    check("stats departments", stats["departments"] == 12)
    check("stats subject types", "release" in stats["subject_types"])
    check("stats total checks", stats["total_checks"] >= 3)

    listed = div.list_reports()
    check("list has report", len(listed) == 1 and listed[0]["final_decision"] == "Conditional Go")
    check("list departments_completed", listed[0]["departments_completed"] == 13)
    check("list total_departments", listed[0]["total_departments"] == 13)

    # --- deterministic director failure fallback ---
    class FailLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            system = messages[0]["content"]
            if "Release Director in the Quality" in system:
                raise RuntimeError("Rate limited (429). Retry after 60s., reset=1786060800000, remaining=0")
            return DEPT_TEXT

    with tempfile.TemporaryDirectory() as tmp:
        div2 = QualityDivision(StubConfig(), FailLLM(), kb=StubKB(), data_file=os.path.join(tmp, "reports.json"))
        result2 = await div2.run_review_sync("Gate release v3.2 of our recruitment SaaS for production.", subject_type="release")
    check("fallback status completed", result2["status"] == "completed")
    check("fallback decision deterministic", result2["final_decision"] in ("Go", "Conditional Go", "No Go"))
    check("fallback quality score set", result2["quality_score"] is not None)
    check("fallback certificate", "## Sign-off" in result2["release_certificate"])
    check("fallback version default", result2["release_version"] in ("v3.2", "v1.0.0"))

    # --- all-departments-fail marks report failed ---
    class AlwaysFailLLM:
        async def chat(self, messages, model=None, temperature=0.4, max_tokens=2000):
            raise RuntimeError("Rate limited (429). reset=1786060800000, remaining=0")

    with tempfile.TemporaryDirectory() as tmp:
        div3 = QualityDivision(StubConfig(), AlwaysFailLLM(), kb=None, data_file=os.path.join(tmp, "reports.json"))
        result3 = await div3.run_review_sync("Gate release v1.0.", subject_type="release")
    check("all-fail status failed", result3["status"] == "failed")
    check("all-fail error mentions LLM", "LLM" in (result3["error"] or ""))

    # --- department card apply + delete ---
    dept_report = QualityDepartmentReport(department_id="security-review", department_name="Security Review Department", department_title="Security Review Director")
    div._apply_parsed(dept_report, parsed)
    check("apply_parsed sets fields", dept_report.verdict == "caution" and dept_report.score == 62 and dept_report.status == "completed")
    check("findings_text", "rate limiting" in dept_report.findings_text())

    rid = p["id"]
    check("get_report works", div.get_report(rid) is not None)
    check("get_report_dict", div.get_report_dict(rid)["id"] == rid)
    check("delete_report", div.delete_report(rid) is True)
    check("delete_report twice", div.delete_report(rid) is False)

    # --- board request text carries the decision ---
    br = ReleaseExcellenceReport(id=rid, request="x", final_decision="Conditional Go", executive_summary="Conditional Go decision.")
    check("board text decision", "Conditional Go" in div.board_request_text(br))
    check("board text carries request", div.board_request_text(br).startswith("x"))

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
