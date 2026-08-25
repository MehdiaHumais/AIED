"""Cross-Layer Workflow Orchestration. Workflow engine.

Coordinates the gated layer chain across all 10 layers:

    Board -> Research -> UX -> Design -> Growth -> Quality
    -> Intelligence -> Governance -> EKDT

Layers 2-7 are board-gated: each produces an artifact, submits it to the
Executive Product Board, and only advances on approval. Layers 8-10 are
internal learning/memory layers that auto-approve after running their
analysis (no board gate needed — they store knowledge and learn from the
project).

Persistence lives at ``data/workflow/runs.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Optional

from workflow.models import WorkflowRun, WorkflowStage

logger = logging.getLogger(__name__)

_WORKFLOW_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "workflow")
_WORKFLOW_DATA_FILE = os.path.join(_WORKFLOW_DATA_DIR, "runs.json")

_STAGE_DEFS: list[dict[str, Any]] = [
    {
        "key": "board",
        "name": "Executive Product Board",
        "layer": 2,
        "short": "Board",
        "engine_attr": "board",
        "run_sync": "run_review_sync",
        "get_item": "get_review",
        "subject_type": None,
    },
    {
        "key": "research",
        "name": "Product Research & Discovery",
        "layer": 3,
        "short": "Research",
        "engine_attr": "research",
        "run_sync": "run_research_sync",
        "get_item": "get_dossier",
        "subject_type": "new_product",
    },
    {
        "key": "ux",
        "name": "UX & Human Experience",
        "layer": 4,
        "short": "UX",
        "engine_attr": "ux",
        "run_sync": "run_review_sync",
        "get_item": "get_review",
        "subject_type": "whole_product",
    },
    {
        "key": "design",
        "name": "Visual Design & Design System",
        "layer": 5,
        "short": "Design",
        "engine_attr": "design",
        "run_sync": "run_design_sync",
        "get_item": "get_package",
        "subject_type": "screen",
    },
    {
        "key": "growth",
        "name": "Growth, Conversion & Customer Success",
        "layer": 6,
        "short": "Growth",
        "engine_attr": "growth",
        "run_sync": "run_review_sync",
        "get_item": "get_review",
        "subject_type": "landing_page",
    },
    {
        "key": "quality",
        "name": "Quality, Security & Release",
        "layer": 7,
        "short": "Quality",
        "engine_attr": "quality",
        "run_sync": "run_review_sync",
        "get_item": "get_report",
        "subject_type": "release",
    },
    {
        "key": "intelligence",
        "name": "Learning & Continuous Improvement",
        "layer": 8,
        "short": "Intelligence",
        "engine_attr": "intelligence",
        "run_sync": "run_review_sync",
        "get_item": "get_report",
        "subject_type": "project",
        "auto_approve": True,
    },
    {
        "key": "governance",
        "name": "AI Governance & Orchestration",
        "layer": 9,
        "short": "Governance",
        "engine_attr": "governance",
        "run_sync": "run_review_sync",
        "get_item": "get_report",
        "subject_type": "operation",
        "auto_approve": True,
    },
    {
        "key": "ekdt",
        "name": "Enterprise Knowledge & Digital Twin",
        "layer": 10,
        "short": "EKDT",
        "engine_attr": "ekdt",
        "run_sync": "run_review_sync",
        "get_item": "get_report",
        "subject_type": "project",
        "auto_approve": True,
    },
]

_APPROVED_VERDICTS = ("approved",)
_PAUSED_VERDICTS = ("revision", "rejected")
_FAILED_VERDICTS = (None, "", "failed")


class WorkflowEngine:
    """The cross-layer workflow orchestrator."""

    def __init__(
        self,
        config,
        llm_manager,
        board=None,
        research=None,
        ux=None,
        design=None,
        growth=None,
        quality=None,
        intelligence=None,
        governance=None,
        ekdt=None,
        kb=None,
        data_file: str | None = None,
        model: str | None = None,
    ) -> None:
        self.config = config
        self.llm = llm_manager
        self.kb = kb
        self.model = model or "gemini-2.5-flash"
        self.board = board
        self.research = research
        self.ux = ux
        self.design = design
        self.growth = growth
        self.quality = quality
        self.intelligence = intelligence
        self.governance = governance
        self.ekdt = ekdt
        self.runs: dict[str, WorkflowRun] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._data_file = data_file or _WORKFLOW_DATA_FILE
        self._load()

    # --- Persistence ---

    def persist(self) -> None:
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump({"runs": [r.model_dump() for r in self.runs.values()]}, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._data_file):
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("runs", []):
                run = WorkflowRun.model_validate(raw)
                self.runs[run.id] = run
            logger.info(f"Loaded {len(self.runs)} workflow runs from disk")
        except Exception as e:
            logger.error(f"Failed to load workflow runs: {e}")

    # --- Accessors ---

    def stage_defs(self) -> list[dict[str, Any]]:
        return [
            {
                "key": s["key"],
                "name": s["name"],
                "layer": s["layer"],
                "short": s["short"],
                "subject_type": s.get("subject_type"),
            }
            for s in _STAGE_DEFS
        ]

    def list_runs(self) -> list[dict[str, Any]]:
        out = []
        for r in sorted(self.runs.values(), key=lambda x: x.created_at, reverse=True):
            out.append({
                "id": r.id,
                "name": r.name,
                "request": r.request[:120],
                "status": r.status,
                "stage_index": r.stage_index,
                "current_stage": r.stages[r.stage_index].name if r.stages and r.stage_index < len(r.stages) else None,
                "approved_stages": sum(1 for s in r.stages if s.status == "approved"),
                "total_stages": len(r.stages),
                "created_at": r.created_at,
                "completed_at": r.completed_at,
            })
        return out

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self.runs.get(run_id)

    def get_run_dict(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        return run.model_dump() if run else None

    def delete_run(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if not run:
            return False
        task = self._running.get(run_id)
        if task and not task.done():
            task.cancel()
        self._running.pop(run_id, None)
        self.runs.pop(run_id, None)
        self.persist()
        return True

    def stats(self) -> dict[str, Any]:
        statuses = {}
        for r in self.runs.values():
            statuses[r.status] = statuses.get(r.status, 0) + 1
        return {
            "total": len(self.runs),
            "running": statuses.get("running", 0),
            "needs_review": statuses.get("needs_review", 0),
            "completed": statuses.get("completed", 0),
            "failed": statuses.get("failed", 0),
            "cancelled": statuses.get("cancelled", 0),
            "stages": [{"key": s["key"], "name": s["name"], "layer": s["layer"]} for s in _STAGE_DEFS],
        }

    # --- Start / Retry / Cancel ---

    def _new_run(self, request: str, name: str = "") -> WorkflowRun:
        run_id = str(uuid.uuid4())
        run = WorkflowRun(
            id=run_id,
            name=name or (request[:60] if request else "Untitled workflow"),
            request=request,
            stages=[WorkflowStage(key=s["key"], name=s["name"], layer=s["layer"]) for s in _STAGE_DEFS],
        )
        self.runs[run_id] = run
        self.persist()
        return run

    async def start(self, request: str, name: str = "") -> dict[str, Any]:
        run = self._new_run(request, name)
        task = asyncio.create_task(self._advance(run))
        self._running[run.id] = task
        task.add_done_callback(lambda t: self._running.pop(run.id, None) and None)
        return {"status": "started", "run_id": run.id, "run": run.model_dump()}

    async def start_sync(self, request: str, name: str = "") -> dict[str, Any]:
        run = self._new_run(request, name)
        await self._advance(run)
        return run.model_dump()

    async def retry(self, run_id: str, request: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if not run:
            return {"status": "not_found"}
        if run.status != "needs_review":
            return {"status": "not_paused"}
        task = asyncio.create_task(self._advance(run, edited_text=request))
        self._running[run.id] = task
        task.add_done_callback(lambda t: self._running.pop(run.id, None) and None)
        return {"status": "retrying", "run_id": run.id}

    async def retry_sync(self, run_id: str, request: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if not run:
            return {"status": "not_found"}
        if run.status != "needs_review":
            return {"status": "not_paused"}
        await self._advance(run, edited_text=request)
        return run.model_dump()

    async def resume(self, run_id: str) -> dict[str, Any]:
        """Resume a failed run from the stage where it stopped.

        Approved earlier layers are kept and not re-run. The failed stage
        re-runs (re-using its artifact if one was already produced, otherwise
        regenerating it) and the gate is re-submitted to the board.
        """
        run = self.runs.get(run_id)
        if not run:
            return {"status": "not_found"}
        if run.status != "failed":
            return {"status": "not_failed"}
        stage = run.stages[run.stage_index] if run.stage_index < len(run.stages) else None
        if stage:
            stage.status = "pending"
            stage.error = ""
            stage.verdict = None
        run.status = "running"
        run.error = ""
        run.updated_at = _now_iso()
        self.persist()
        task = asyncio.create_task(self._advance(run))
        self._running[run.id] = task
        task.add_done_callback(lambda t: self._running.pop(run.id, None) and None)
        return {"status": "resuming", "run_id": run.id}

    async def cancel(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if not run:
            return False
        if run.status != "running":
            return False
        task = self._running.get(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except Exception:
                pass
        # Underlying engines may swallow the CancelledError (they mark their own
        # review cancelled and return normally), so force the cancelled state here.
        run.status = "cancelled"
        run.completed_at = _now_iso()
        run.updated_at = _now_iso()
        cur = run.stages[run.stage_index] if run.stage_index < len(run.stages) else None
        if cur and cur.status in ("running", "failed"):
            cur.status = "cancelled"
            cur.completed_at = _now_iso()
        self.persist()
        return True

    # --- Core gate loop ---

    async def _advance(self, run: WorkflowRun, edited_text: Optional[str] = None) -> None:
        try:
            while run.stage_index < len(run.stages):
                stage = run.stages[run.stage_index]
                if stage.status == "approved":
                    run.stage_index += 1
                    run.updated_at = _now_iso()
                    continue
                run.status = "running"
                stage.status = "running"
                stage.started_at = stage.started_at or _now_iso()
                if edited_text is not None and stage.key == "board":
                    run.request = edited_text
                self.persist()
                verdict, error = await self._run_stage(run, stage, edited_text=edited_text)
                stage.verdict = verdict or None
                run.updated_at = _now_iso()
                if verdict in _APPROVED_VERDICTS:
                    stage.status = "approved"
                    stage.completed_at = _now_iso()
                    run.stage_index += 1
                    self.persist()
                    continue
                if verdict in _PAUSED_VERDICTS:
                    stage.status = "needs_review"
                    run.status = "needs_review"
                    self.persist()
                    return
                stage.status = "failed"
                stage.error = error or "Stage failed"
                run.status = "failed"
                run.error = error or "Stage failed"
                self.persist()
                return
            run.status = "completed"
            run.completed_at = _now_iso()
            run.updated_at = _now_iso()
            self.persist()
        except asyncio.CancelledError:
            run.status = "cancelled"
            run.error = "Workflow cancelled"
            self.persist()
        except Exception as e:
            logger.exception("Workflow advance failed")
            run.status = "failed"
            run.error = str(e)[:300]
            self.persist()

    async def _run_stage(self, run: WorkflowRun, stage: WorkflowStage, edited_text: Optional[str] = None):
        """Run one gate: produce the stage artifact (if needed) and submit it
        to the Executive Product Board. Returns (verdict, error).

        Layers 8-10 (Intelligence, Governance, EKDT) auto-approve — they run
        their analysis and store results without a board gate.
        """
        try:
            # Check if this is an auto-approve layer (L8-L10)
            stage_spec = next((s for s in _STAGE_DEFS if s["key"] == stage.key), None)
            if stage_spec and stage_spec.get("auto_approve"):
                engine = self._stage_engine(stage.key)
                if engine is None:
                    return "failed", f"Layer {stage.layer} engine is not initialized"
                # Run the layer's analysis
                if not stage.item_id:
                    result = await self._run_layer(stage.key, run.request)
                    item_id = (result or {}).get("id") or (result or {}).get("report_id")
                    if item_id:
                        stage.item_id = item_id
                    else:
                        # Even if no item_id, the layer ran — mark as complete
                        stage.item_id = f"auto-{stage.key}-{run.id[:8]}"
                stage.request_sent = run.request
                return "approved", ""

            board = getattr(self, "board")
            if board is None:
                return "failed", "Executive Product Board is not initialized"
            if stage.key == "board":
                request_text = edited_text or run.request
            else:
                engine = self._stage_engine(stage.key)
                if engine is None:
                    return "failed", f"Layer {stage.layer} engine is not initialized"
                if not stage.item_id:
                    result = await self._run_layer(stage.key, run.request)
                    item_id = (result or {}).get("id")
                    if not item_id:
                        return "failed", (result or {}).get("error") or f"{stage.name} produced no artifact"
                    stage.item_id = item_id
                    item = self._get_item(stage.key, item_id)
                    if item is None:
                        return "failed", f"{stage.name} artifact {item_id[:8]} not found"
                    request_text = self._board_request_text(stage.key, item)
                else:
                    request_text = edited_text or stage.request_sent or run.request
            review = await board.run_review_sync(request=request_text)
            if not isinstance(review, dict):
                review = getattr(review, "model_dump", lambda: {})() or {}
            review_id = review.get("id") or review.get("review_id")
            stage.board_review_id = review_id
            stage.request_sent = request_text
            verdict = review.get("final_verdict")
            stage.score = review.get("total_score")
            if verdict in _APPROVED_VERDICTS:
                return "approved", ""
            if verdict in _PAUSED_VERDICTS:
                return verdict, ""
            error = review.get("error") or (review.get("status") if review.get("status") == "failed" else "Board review failed")
            return "failed", error or "Board review failed"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Stage {stage.key} failed")
            return "failed", str(e)[:300]

    def _stage_engine(self, key: str):
        engine_attr = next((s["engine_attr"] for s in _STAGE_DEFS if s["key"] == key), None)
        return getattr(self, engine_attr, None) if engine_attr else None

    async def _run_layer(self, key: str, request: str) -> dict[str, Any]:
        engine = self._stage_engine(key)
        spec = next(s for s in _STAGE_DEFS if s["key"] == key)
        run_sync = getattr(engine, spec["run_sync"])
        result = await run_sync(request=request, subject_type=spec["subject_type"])
        if not isinstance(result, dict):
            result = getattr(result, "model_dump", lambda: {})() or {}
        return result

    def _get_item(self, key: str, item_id: str):
        engine = self._stage_engine(key)
        spec = next(s for s in _STAGE_DEFS if s["key"] == key)
        return getattr(engine, spec["get_item"])(item_id)

    def _board_request_text(self, key: str, item) -> str:
        engine = self._stage_engine(key)
        return engine.board_request_text(item)

    def build_development_package(self, run_id: str) -> dict[str, Any]:
        """Assemble the approved layer artifacts of a completed run into a
        Development Package for the build team.

        Returns a dict with ``title``, ``request`` and ``markdown`` (the full
        package spec). Only approved stages with artifacts are included.
        """
        run = self.runs.get(run_id)
        if not run:
            return {}
        sections: list[str] = []
        for stage in run.stages:
            if stage.status != "approved" or not stage.item_id:
                continue
            try:
                item = self._get_item(stage.key, stage.item_id)
                text = self._board_request_text(stage.key, item)
            except Exception as e:  # noqa: BLE001
                text = f"(artifact could not be read: {e})"
            if not text:
                continue
            verdict_line = f" (board score {stage.score})" if stage.score is not None else ""
            sections.append(
                f"## {stage.name} — Layer {stage.layer} — APPROVED{verdict_line}\n\n{text.strip()}"
            )
        header = (
            f"# Development Package: {run.name}\n\n"
            f"> Original request: {run.request}\n\n"
            f"All gates approved on {run.completed_at or 'completion'}.\n\n"
        )
        return {
            "title": run.name,
            "request": run.request,
            "markdown": header + "\n\n---\n\n".join(sections),
            "stage_count": len(sections),
        }



def _now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"
