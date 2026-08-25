"""Layer 5 - Visual Design & Design System Division (VDDS). Design engine.

Runs a design subject through the eleven design departments, the Creative
Director merges their specifications into one Visual Design Package plus an
implementation-ready visual specification for the Frontend Development Agent,
and the package is persisted to ``data/design/packages.json``.

The engine is resilient: an LLM outage marks individual departments as failed
and the package still completes using whatever specifications were gathered.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from statistics import mean
from typing import Any, Optional

from design.models import DesignDepartmentReport, VisualDesignPackage
from design.prompts import (
    DESIGN_DEPARTMENTS,
    DESIGN_DEPARTMENTS_LIST,
    DESIGN_ORDER,
    SUBJECT_TYPES,
    build_department_request_prompt,
    build_director_prompt,
    get_design_department_prompt,
)

logger = logging.getLogger(__name__)

_DESIGN_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "design")
_DESIGN_DATA_FILE = os.path.join(_DESIGN_DATA_DIR, "packages.json")

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEPARTMENT_TIMEOUT = 240
_DIRECTOR_TIMEOUT = 300

_STRICT_FORMAT_REMINDER = (
    "\n\nIMPORTANT: your previous reply did not follow the required format. "
    "Reply AGAIN using EXACTLY these headings, one per line: "
    "## VERDICT: <support|recommend|caution|risk>, ## CONFIDENCE: <0.0-1.0>, "
    "## SCORE: <0-100>, ## TOKENS, ## COMPONENT SPECIFICATIONS, ## FINDINGS, "
    "## RECOMMENDATIONS, ## EVIDENCE. Put at least one bullet under TOKENS, "
    "COMPONENT SPECIFICATIONS, FINDINGS, and RECOMMENDATIONS."
)


def _err_text(e: Exception) -> str:
    """Human-readable error message (asyncio.TimeoutError has an empty str())."""
    if isinstance(e, asyncio.TimeoutError):
        return f"Timed out after {_DEPARTMENT_TIMEOUT}s"
    return str(e)[:300] or type(e).__name__


def _quota_exhausted(e: Exception) -> bool:
    """True when the error is a definitive provider quota/rate-limit
    exhaustion, which a retry cannot succeed past. The LLM manager already
    waited through its internal 60s backoff, so retrying only burns time."""
    msg = str(e)
    return ("Rate limited" in msg or "remaining=0" in msg or "quota" in msg.lower())


# --- Parsing helpers (robust against free-form LLM output) ---

def _find_section(text: str, header: str) -> str:
    """Return the text of a '## HEADER' section up to the next '##' or end."""
    pattern = rf"^##\s*{re.escape(header)}\s*:?\s*$"
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip(), re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        m = re.search(rf"^##\s*{re.escape(header)}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
        return ""
    out = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        out.append(line)
    return "\n".join(out).strip()


def _bullets(section: str) -> list[str]:
    out = []
    for line in section.splitlines():
        line = line.strip().lstrip("*-•").strip()
        if line and not line.lower().startswith(("##", "section")):
            out.append(line)
    return out


def _inline_value(text: str, header: str) -> str:
    m = re.search(rf"^##\s*{re.escape(header)}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else ""


def _find_section_until(text: str, header: str, stop_headers: list[str]) -> str:
    """Return a section's full text, capturing inner '##' sub-headers, until
    one of the given stop headers. Used for sections like the Visual
    Specification whose body itself contains '##' headings."""
    m = re.search(
        rf"^##\s*{re.escape(header)}\s*:?\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in stop_headers)})\s*:?\s*$|\Z)",
        text, re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _parse_department_output(text: str) -> dict[str, Any]:
    verdict_match = re.search(
        r"##\s*VERDICT\s*:?\s*(support|recommend|caution|risk|neutral)",
        text, re.IGNORECASE,
    )
    verdict = "neutral"
    if verdict_match:
        verdict = verdict_match.group(1).lower()

    confidence = 0.5
    conf_match = re.search(r"##\s*CONFIDENCE\s*:?\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
    if conf_match:
        try:
            confidence = max(0.0, min(1.0, float(conf_match.group(1))))
        except ValueError:
            confidence = 0.5

    score: Optional[int] = None
    score_match = re.search(r"##\s*SCORE\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None

    tokens = _bullets(_find_section(text, "TOKENS"))
    components = _bullets(_find_section(text, "COMPONENT SPECIFICATIONS"))
    findings = _bullets(_find_section(text, "FINDINGS"))
    recommendations = _bullets(_find_section(text, "RECOMMENDATIONS"))
    evidence = _bullets(_find_section(text, "EVIDENCE"))
    return {
        "verdict": verdict,
        "confidence": confidence,
        "score": score,
        "tokens": tokens,
        "components": components,
        "findings": findings,
        "recommendations": recommendations,
        "evidence": evidence,
        "report": text,
    }


def _salvage_department_text(text: str) -> dict[str, Any]:
    """Salvage a non-empty but off-format reply instead of failing the department.

    Keeps the raw text as the report (the Creative Director still reads it) and
    extracts usable bullet points as components so the department counts as done.
    """
    lines = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("*-•#").strip()
        if line and len(line) > 3 and not line.lower().startswith(("##", "section", "verdict", "confidence")):
            lines.append(line)
    return {
        "verdict": "caution",
        "confidence": 0.3,
        "score": None,
        "tokens": [],
        "components": lines[:10],
        "findings": lines[:10],
        "recommendations": [],
        "evidence": [],
        "report": text,
    }


_PACKAGE_LIST_SECTIONS = {
    "Design System Components": "design_components",
    "Layout Specification": "layout_specification",
    "Spacing Rules": "spacing_rules",
    "Typography": "typography",
    "Color Tokens": "color_tokens",
    "Icon Selection": "icon_selection",
    "Responsive Behavior": "responsive_behavior",
    "Animation Rules": "animation_rules",
    "Accessibility Requirements": "accessibility_requirements",
    "Component Variants": "component_variants",
    "Design Assets": "design_assets",
    "Acceptance Checklist": "acceptance_checklist",
}

_PACKAGE_TEXT_SECTIONS = {
    "Visual Specification": "visual_specification",
    "Executive Summary": "executive_summary",
}


def _parse_package(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for header, key in _PACKAGE_LIST_SECTIONS.items():
        data[key] = _bullets(_find_section(text, header))
    for header, key in _PACKAGE_TEXT_SECTIONS.items():
        data[key] = _find_section(text, header) or _inline_value(text, header)
    # The Visual Specification body contains its own ## sub-headers (Goal,
    # Layout, Components, Tokens, Rules, Acceptance Criteria), so parse it with
    # a dedicated extractor that runs until the Executive Summary.
    data["visual_specification"] = _find_section_until(text, "Visual Specification", ["Executive Summary"])

    score: Optional[int] = None
    score_match = re.search(r"##\s*Visual Quality Score\s*:?\s*(\d{1,3})", text, re.IGNORECASE)
    if score_match:
        try:
            score = max(0, min(100, int(score_match.group(1))))
        except ValueError:
            score = None
    data["visual_quality_score"] = score
    return data


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        key = it.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _package_markdown(p: dict[str, Any]) -> str:
    lines = ["# Visual Design & Design System Division - Visual Design Package"]
    lines.append("")
    if p.get("visual_quality_score") is not None:
        lines.append(f"**Visual Quality Score:** {p['visual_quality_score']}/100")
    for label, key in _PACKAGE_LIST_SECTIONS.items():
        values = p.get(key) or []
        if values:
            lines.append("")
            lines.append(f"## {label}")
            lines.extend(f"- {v}" for v in values)
    if p.get("visual_specification"):
        lines.append("")
        lines.append("## Visual Specification")
        lines.append(p["visual_specification"])
    if p.get("executive_summary"):
        lines.append("")
        lines.append("## Executive Summary")
        lines.append(p["executive_summary"])
    return "\n".join(lines)


class DesignDivision:
    """The Visual Design & Design System Division (Layer 5)."""

    def __init__(
        self,
        config,
        llm_manager,
        kb=None,
        data_file: str | None = None,
        model: str | None = None,
    ) -> None:
        self.config = config
        self.llm = llm_manager
        self.kb = kb
        self.model = model or _DEFAULT_MODEL
        self.packages: dict[str, VisualDesignPackage] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _DESIGN_DATA_FILE
        self._load()

    # --- Persistence ---

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump({"packages": [p.model_dump() for p in self.packages.values()]}, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("packages", []):
                package = VisualDesignPackage.model_validate(raw)
                self.packages[package.id] = package
            logger.info(f"Loaded {len(self.packages)} Visual Design Packages from disk")
        except Exception as e:
            logger.error(f"Failed to load Visual Design Packages: {e}")

    # --- Accessors ---

    def departments(self) -> list[dict[str, Any]]:
        return [
            {
                "id": did,
                "name": DESIGN_DEPARTMENTS[did]["name"],
                "title": DESIGN_DEPARTMENTS[did]["title"],
                "order": DESIGN_ORDER.index(did),
                "is_coordinator": did == "creative-director",
            }
            for did in DESIGN_ORDER
        ]

    def stats(self) -> dict[str, Any]:
        completed = [p for p in self.packages.values() if p.status == "completed"]
        confidences = [p.avg_confidence for p in completed if p.avg_confidence is not None]
        scores = [p.visual_quality_score for p in completed if p.visual_quality_score is not None]
        return {
            "total": len(self.packages),
            "in_progress": sum(1 for p in self.packages.values() if p.status == "in_progress"),
            "completed": len(completed),
            "failed": sum(1 for p in self.packages.values() if p.status == "failed"),
            "avg_confidence": round(mean(confidences), 2) if confidences else None,
            "avg_visual_quality": round(mean(scores)) if scores else None,
            "total_components": sum(p.total_components for p in completed),
            "total_tokens": sum(p.total_tokens for p in completed),
            "departments": len(DESIGN_DEPARTMENTS_LIST),
            "subject_types": SUBJECT_TYPES,
        }

    def list_packages(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.packages.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": p.id,
                "request": p.request[:120],
                "subject_type": p.subject_type,
                "status": p.status,
                "stage": p.stage,
                "created_at": p.created_at,
                "completed_at": p.completed_at,
                "avg_confidence": p.avg_confidence,
                "visual_quality_score": p.visual_quality_score,
                "total_components": p.total_components,
                "total_tokens": p.total_tokens,
                "departments_completed": sum(1 for rep in p.reports if rep.status == "completed"),
                "total_departments": len(p.reports),
                "board_review_id": p.board_review_id,
            })
        return out

    def get_package(self, package_id: str) -> VisualDesignPackage | None:
        return self.packages.get(package_id)

    def get_package_dict(self, package_id: str) -> dict[str, Any] | None:
        p = self.packages.get(package_id)
        return p.model_dump() if p else None

    def delete_package(self, package_id: str) -> bool:
        if package_id not in self.packages:
            return False
        if package_id in self._running:
            self._running[package_id].cancel()
            del self._running[package_id]
        del self.packages[package_id]
        self.persist()
        return True

    def board_request_text(self, package: VisualDesignPackage) -> str:
        """Build a board review request that carries this package's findings."""
        summary = package.executive_summary or "Visual Design Package completed; see the package for details."
        return f"{package.request}\n\n[Visual Design Package from VDDS review {package.id[:8]}: {summary}]"

    # --- Design workflow ---

    async def run_design(self, request: str, subject_type: str = "screen") -> dict[str, Any]:
        """Run a full design review in the background. Updates the stored package."""
        package_id = str(uuid.uuid4())
        package = VisualDesignPackage(id=package_id, request=request, subject_type=subject_type)
        self.packages[package_id] = package

        task = asyncio.create_task(self._execute(package))
        self._running[package_id] = task
        task.add_done_callback(lambda t: self._running.pop(package_id, None) and None)
        return {"status": "started", "package_id": package_id, "package": package.model_dump()}

    async def run_design_sync(self, request: str, subject_type: str = "screen") -> dict[str, Any]:
        """Run a full design review synchronously (blocks until finished). For tests/CLI."""
        package_id = str(uuid.uuid4())
        package = VisualDesignPackage(id=package_id, request=request, subject_type=subject_type)
        self.packages[package_id] = package
        await self._execute(package)
        return package.model_dump()

    async def _execute(self, package: VisualDesignPackage) -> None:
        try:
            await self._run_departments(package)
            await self._run_director(package)
            self._finalize(package)
            if package.status != "failed":
                package.status = "completed"
            package.stage = "done"
            package.completed_at = datetime.utcnow().isoformat() + "Z"
        except asyncio.CancelledError:
            package.status = "cancelled"
            package.error = "Visual Design Package cancelled"
        except Exception as e:
            logger.exception("Visual Design Package failed")
            package.status = "failed"
            package.error = str(e)[:300]
        self.persist()

    def _foundation_block(self, text: str, max_items: int = 5) -> str:
        if self.kb is None:
            return ""
        try:
            return self.kb.briefing_markdown(text, max_items=max_items)
        except Exception as e:
            logger.warning(f"KB briefing failed for design review: {e}")
            return ""

    async def _call_department(self, department_id: str, user_prompt: str, max_tokens: int = 2000) -> str:
        messages = [
            {"role": "system", "content": get_design_department_prompt(department_id)},
            {"role": "user", "content": user_prompt},
        ]
        response = await asyncio.wait_for(
            self.llm.chat(messages=messages, model=self.model, temperature=0.4, max_tokens=max_tokens),
            timeout=_DEPARTMENT_TIMEOUT,
        )
        return response

    def _report_skeleton(self, department_id: str) -> DesignDepartmentReport:
        dept = DESIGN_DEPARTMENTS[department_id]
        return DesignDepartmentReport(
            department_id=department_id,
            department_name=dept["name"],
            department_title=dept["title"],
        )

    async def _run_departments(self, package: VisualDesignPackage) -> None:
        package.stage = "design"

        async def run_one(department_id: str) -> None:
            report = self._report_skeleton(department_id)
            report.started_at = datetime.utcnow().isoformat() + "Z"
            package.reports.append(report)
            dept = DESIGN_DEPARTMENTS[department_id]
            focus = " ".join(dept.get("focus_areas", []))
            try:
                user_prompt = build_department_request_prompt(
                    department_id, package.request, package.subject_type,
                    foundation_block=self._foundation_block(package.request + " " + focus),
                )
                parsed = await self._department_parsed(department_id, user_prompt)
                self._apply_parsed(report, parsed)
                report.completed_at = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                report.status = "failed"
                report.error = _err_text(e)
                logger.warning(f"Design department {department_id} failed: {e}")

        # The LLM manager serializes all requests, so departments run one at a
        # time. Sequential execution gives each call a full timeout window
        # instead of burning it waiting in the queue.
        for department_id in DESIGN_DEPARTMENTS_LIST:
            await run_one(department_id)

    async def _department_parsed(self, department_id: str, user_prompt: str) -> dict[str, Any]:
        """Call a department, retrying once on transient failures / empty
        replies (the LLM manager retries internally, but a single extra attempt
        catches brief provider outages)."""
        last_exc: Exception | None = None
        for attempt in range(2):
            prompt = user_prompt + (_STRICT_FORMAT_REMINDER if attempt else "")
            try:
                text = await self._call_department(department_id, prompt)
                parsed = _parse_department_output(text)
                if not parsed["findings"] and not parsed["recommendations"] and not parsed["evidence"]:
                    if attempt == 0:
                        continue  # retry once with a strict format reminder
                    if text and text.strip():
                        return _salvage_department_text(text)
                    raise ValueError("Empty response from LLM - no parsable sections in reply")
                return parsed
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                if attempt == 0 and not _quota_exhausted(e):
                    logger.warning(f"Design department {department_id} attempt 1 failed ({e}); retrying once")
                    continue
                raise last_exc
        raise last_exc

    def _apply_parsed(self, report: DesignDepartmentReport, parsed: dict[str, Any]) -> None:
        report.verdict = parsed["verdict"]
        report.confidence = parsed["confidence"]
        report.score = parsed.get("score")
        report.tokens = parsed["tokens"]
        report.components = parsed["components"]
        report.findings = parsed["findings"]
        report.recommendations = parsed["recommendations"]
        report.evidence = parsed["evidence"]
        report.report = parsed["report"]
        report.status = "completed"

    # --- Creative Director + package ---

    async def _run_director(self, package: VisualDesignPackage) -> None:
        package.stage = "synthesis"
        director = self._report_skeleton("creative-director")
        director.started_at = datetime.utcnow().isoformat() + "Z"
        package.reports.append(director)

        reports = []
        for r in package.reports:
            if r.department_id == "creative-director":
                continue
            header = f"### {r.department_title} ({r.department_id})\n"
            if r.status == "completed":
                body = r.report or r.findings_text()
                reports.append(header + body[:3000])
            else:
                reports.append(header + f"_(department specification unavailable: {r.error or 'failed'})_")

        data: dict[str, Any] = {}
        try:
            user_prompt = build_director_prompt(
                package.request, reports, package.subject_type,
                foundation_block=self._foundation_block(package.request + " visual design", 3),
            )
            text = await self._call_department("creative-director", user_prompt, max_tokens=4000)
            parsed = _parse_package(text)
            self._apply_parsed(director, {
                "verdict": "recommend",
                "confidence": 0.7,
                "score": parsed.get("visual_quality_score"),
                "tokens": _bullets(_find_section(text, "COLOR TOKENS")) or _bullets(_find_section(text, "SPACING RULES")),
                "components": _bullets(_find_section(text, "DESIGN SYSTEM COMPONENTS")),
                "findings": _bullets(_find_section(text, "DESIGN SYSTEM COMPONENTS")),
                "recommendations": _bullets(_find_section(text, "ACCEPTANCE CHECKLIST")),
                "evidence": _bullets(_find_section(text, "ACCESSIBILITY REQUIREMENTS")),
                "report": text,
            })
            director.completed_at = datetime.utcnow().isoformat() + "Z"
            data = parsed
        except Exception as e:
            director.status = "failed"
            director.error = _err_text(e)
            logger.warning(f"Creative Director failed: {e}")

        self._apply_package(package, data)

    def _confidence_fallback(self, package: VisualDesignPackage) -> list[str]:
        out = []
        for r in package.reports:
            if r.department_id == "creative-director":
                continue
            if r.status == "completed":
                out.append(f"{r.department_title}: {r.confidence:.2f} - reported")
            else:
                out.append(f"{r.department_title}: unavailable - {r.error or 'failed'}")
        return out

    def _apply_package(self, package: VisualDesignPackage, data: dict[str, Any]) -> None:
        package.visual_quality_score = data.get("visual_quality_score")
        for header, key in _PACKAGE_LIST_SECTIONS.items():
            setattr(package, key, data.get(key) or [])
        for header, key in _PACKAGE_TEXT_SECTIONS.items():
            setattr(package, key, data.get(key) or "")

        # Fill gaps from department reports so the package is never empty.
        all_components: list[str] = []
        all_tokens: list[str] = []
        all_recs: list[str] = []
        all_findings: list[str] = []
        scores: list[int] = []
        for r in package.reports:
            if r.department_id == "creative-director":
                continue
            all_components.extend(r.components)
            all_tokens.extend(r.tokens)
            all_recs.extend(r.recommendations)
            all_findings.extend(r.findings)
            if r.score is not None:
                scores.append(r.score)

        if not package.design_components:
            package.design_components = _dedupe(all_components)[:8]
        if not package.component_variants:
            package.component_variants = _dedupe(all_components)[:5]
        if not package.color_tokens:
            package.color_tokens = _dedupe(t for t in all_tokens if "color" in t.lower() or t.startswith("--") and ("#" in t))[:12]
        if not package.spacing_rules:
            package.spacing_rules = _dedupe(t for t in all_tokens if "space" in t.lower() or "gap" in t.lower() or "margin" in t.lower())[:10]
        if not package.acceptance_checklist:
            package.acceptance_checklist = _dedupe(all_recs)[:6]
        if not package.responsive_behavior:
            package.responsive_behavior = _dedupe(all_findings)[:6]
        if package.visual_quality_score is None and scores:
            package.visual_quality_score = round(mean(scores))
        if package.visual_quality_score is None:
            package.visual_quality_score = 50
        if not package.visual_specification:
            components = package.design_components or package.component_variants
            package.visual_specification = (
                "## Goal\nApply the Visual Design Package recommendations.\n\n"
                "## Components\n" + "\n".join(f"- {c}" for c in components[:8]) +
                "\n\n## Rules\n- Use the approved design tokens and component library.\n"
                "- No custom components unless approved by the Design System Department.\n"
                "- Support light and dark mode; keyboard navigation and screen reader labels required.\n\n"
                "## Acceptance Criteria\n- All text passes WCAG AA contrast.\n"
                "- The interface matches the layout and spacing specification."
            )
        if not package.executive_summary:
            done = sum(1 for r in package.reports if r.status == "completed")
            package.executive_summary = (
                f"Visual Design Package completed across {done} of {len(DESIGN_DEPARTMENTS_LIST)} departments. "
                f"Visual quality score: {package.visual_quality_score}/100. See the department "
                f"reports and the visual specification for what the frontend agent must build."
            )

    def _finalize(self, package: VisualDesignPackage) -> None:
        done = [r for r in package.reports if r.status == "completed" and r.department_id != "creative-director"]
        if not done:
            package.status = "failed"
            package.error = "No design departments completed (LLM unavailable)"
        if done:
            package.avg_confidence = round(mean(r.confidence for r in done), 2)
        package.total_components = sum(len(r.components) for r in done)
        package.total_tokens = sum(len(r.tokens) for r in done)
        package.package_markdown = _package_markdown(package.model_dump())
