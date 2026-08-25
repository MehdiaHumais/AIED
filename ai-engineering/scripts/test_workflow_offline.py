"""Offline test for the Cross-Layer Workflow Orchestration engine (no LLM calls).

Uses fake layer engines and a fake board so the gate loop is tested in
isolation and deterministically: happy path, reject -> edit -> retry at every
stage position, cancel, persistence, and delete.
"""
import asyncio
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.engine import WorkflowEngine
from workflow.models import WorkflowRun, WorkflowStage

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name}")


class StubLLM:
    async def chat(self, messages=None, model=None, **kw):
        return "stub"


class FakeItem:
    def __init__(self, item_id, request):
        self.id = item_id
        self.request = request
        self.summary = f"summary of {request}"


class FakeLayer:
    """One fake Layer 3-7 engine exposing every run_sync/get name."""

    def __init__(self, key, reject=False, delay=0.0):
        self.key = key
        self.reject = reject
        self.delay = delay
        self.items = {}
        self.run_count = 0

    async def _run(self, request, subject_type=None):
        self.run_count += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        item_id = str(uuid.uuid4())
        item = FakeItem(item_id, request)
        self.items[item_id] = item
        return {"id": item_id, "request": request}

    async def run_research_sync(self, request, subject_type=None):
        return await self._run(request, subject_type)

    async def run_review_sync(self, request, subject_type=None):
        return await self._run(request, subject_type)

    async def run_design_sync(self, request, subject_type=None):
        return await self._run(request, subject_type)

    def get_dossier(self, item_id):
        return self.items.get(item_id)

    def get_review(self, item_id):
        return self.items.get(item_id)

    def get_package(self, item_id):
        return self.items.get(item_id)

    def get_report(self, item_id):
        return self.items.get(item_id)

    def board_request_text(self, item):
        text = f"{item.request}\n\n[{self.key} artifact {item.id[:8]}: {item.summary}]"
        if self.reject:
            text += "\nBOARD_REQUEST_REJECTED"
        return text


class FakeBoard:
    def __init__(self, reject_requests=(), reject_markers=()):
        self.reviews = {}
        self.reject_requests = set(reject_requests)
        self.reject_markers = tuple(reject_markers)

    async def run_review_sync(self, request, project_id=None):
        review_id = str(uuid.uuid4())
        review = {
            "id": review_id,
            "request": request,
            "final_verdict": "approved",
            "total_score": 85.0,
            "status": "completed",
            "error": "",
        }
        if request in self.reject_requests or any(m in request for m in self.reject_markers):
            review["final_verdict"] = "rejected"
            review["total_score"] = 25.0
        self.reviews[review_id] = review
        return review

    def get_review(self, review_id):
        return self.reviews.get(review_id)


class SwallowingBoard(FakeBoard):
    """Simulates the real board engine which catches CancelledError, marks its
    review cancelled and returns normally instead of propagating."""

    async def run_review_sync(self, request, project_id=None):
        try:
            await asyncio.sleep(60)
            return await super().run_review_sync(request, project_id)
        except asyncio.CancelledError:
            review_id = str(uuid.uuid4())
            review = {
                "id": review_id,
                "request": request,
                "final_verdict": "pending",
                "total_score": None,
                "status": "cancelled",
                "error": "Review cancelled",
            }
            return review


def make_engine(tmp, board=None, layers=None):
    layers = layers or {}
    data_file = os.path.join(tmp, "runs.json")
    engine = WorkflowEngine(
        config=None,
        llm_manager=StubLLM(),
        board=board or FakeBoard(),
        research=layers.get("research") or FakeLayer("research"),
        ux=layers.get("ux") or FakeLayer("ux"),
        design=layers.get("design") or FakeLayer("design"),
        growth=layers.get("growth") or FakeLayer("growth"),
        quality=layers.get("quality") or FakeLayer("quality"),
        data_file=data_file,
    )
    return engine


# --- registry ---

def test_stage_defs(engine):
    stages = engine.stage_defs()
    check("six stages", len(stages) == 6)
    check("correct order", [s["key"] for s in stages] == ["board", "research", "ux", "design", "growth", "quality"])
    check("board is layer 2", stages[0]["layer"] == 2)
    check("quality is layer 7", stages[5]["layer"] == 7)


# --- happy path ---

async def test_happy_path(tmp):
    engine = make_engine(tmp)
    run = engine.get_run(((await engine.start_sync(request="Build a warehouse inventory app"))["id"]))
    check("happy path completed", run.status == "completed")
    check("all stages approved", all(s.status == "approved" for s in run.stages))
    check("stage_index past end", run.stage_index == 6)
    check("every stage has a board review", all(s.board_review_id for s in run.stages))
    check("non-board stages have artifacts", all(run.stages[i].item_id for i in (1, 2, 3, 4, 5)))
    check("board stage has no artifact", run.stages[0].item_id is None)
    check("final score recorded", run.stages[5].score == 85.0)
    check("completed_at set", run.completed_at is not None)


# --- reject at the board gate (stage 0) ---

async def test_reject_at_board(tmp):
    board = FakeBoard(reject_requests={"Build a warehouse inventory app"})
    engine = make_engine(tmp, board=board)
    run = engine.get_run(((await engine.start_sync(request="Build a warehouse inventory app"))["id"]))
    check("board reject pauses run", run.status == "needs_review")
    check("stage 0 needs_review", run.stages[0].status == "needs_review")
    check("stage 0 rejected verdict", run.stages[0].verdict == "rejected")
    check("stage 0 score recorded", run.stages[0].score == 25.0)
    check("still at stage 0", run.stage_index == 0)
    check("later stages untouched", all(s.status == "pending" for s in run.stages[1:]))


# --- retry after board reject updates the brief and advances ---

async def test_retry_at_board(tmp):
    board = FakeBoard(reject_requests={"Build a warehouse inventory app"})
    engine = make_engine(tmp, board=board)
    run_id = ((await engine.start_sync(request="Build a warehouse inventory app"))["id"])
    run = engine.get_run(run_id)
    check("board reject pauses run", run.status == "needs_review")
    result = await engine.retry_sync(run_id, "Build a warehouse inventory app v2")
    check("retry returns run dict", "stages" in result)
    run = engine.get_run(run_id)
    check("retry approved then completed", run.status == "completed")
    check("brief updated by edit", run.request == "Build a warehouse inventory app v2")
    check("stage 0 approved", run.stages[0].status == "approved")
    check("all stages approved after retry", all(s.status == "approved" for s in run.stages))


# --- reject at a later gate (ux, stage 2) keeps earlier work ---

async def test_reject_at_ux(tmp):
    ux = FakeLayer("ux", reject=True)
    board = FakeBoard(reject_markers=("BOARD_REQUEST_REJECTED",))
    engine = make_engine(tmp, board=board, layers={"ux": ux})
    run = engine.get_run(((await engine.start_sync(request="Build a warehouse inventory app"))["id"]))
    check("ux reject pauses run", run.status == "needs_review")
    check("board and research approved", run.stages[0].status == "approved" and run.stages[1].status == "approved")
    check("ux needs_review", run.stages[2].status == "needs_review")
    check("ux rejected verdict", run.stages[2].verdict == "rejected")
    check("later stages pending", all(s.status == "pending" for s in run.stages[3:]))
    check("at stage 2", run.stage_index == 2)
    check("ux artifact exists", run.stages[2].item_id is not None)
    check("board run_count 3", board_run_count(board) == 3)
    return engine, ux, board


def board_run_count(board):
    return len(board.reviews)


# --- retry at a later gate reuses the artifact and advances ---

async def test_retry_at_ux(tmp):
    ux = FakeLayer("ux", reject=True)
    board = FakeBoard(reject_markers=("BOARD_REQUEST_REJECTED",))
    engine = make_engine(tmp, board=board, layers={"ux": ux})
    run_id = ((await engine.start_sync(request="Build a warehouse inventory app"))["id"])
    run = engine.get_run(run_id)
    artifact_before = run.stages[2].item_id
    check("paused at ux", run.status == "needs_review")
    ux.reject = False
    result = await engine.retry_sync(run_id, "UX brief edited after board feedback")
    run = engine.get_run(run_id)
    check("retry completed the run", run.status == "completed")
    check("ux artifact reused (not recreated)", run.stages[2].item_id == artifact_before)
    check("ux run_count 1", ux.run_count == 1)
    check("ux approved after edit", run.stages[2].status == "approved")
    check("all stages approved", all(s.status == "approved" for s in run.stages))
    check("edited text recorded", run.stages[2].request_sent == "UX brief edited after board feedback")


# --- retry on a non-paused run is rejected ---

async def test_retry_not_paused(tmp):
    engine = make_engine(tmp)
    run_id = ((await engine.start_sync(request="Build a warehouse inventory app"))["id"])
    result = await engine.retry_sync(run_id, "edited")
    check("retry on completed run refused", result.get("status") == "not_paused")


# --- cancel ---

async def test_cancel(tmp):
    slow = FakeLayer("research", delay=60)
    engine = make_engine(tmp, layers={"research": slow})
    started = await engine.start(request="Build a warehouse inventory app")
    run_id = started["run_id"]
    await asyncio.sleep(0.2)
    ok = await engine.cancel(run_id)
    check("cancel returns True", ok is True)
    run = engine.get_run(run_id)
    check("run cancelled", run.status == "cancelled")


# --- cancel mid-board when the board swallows CancelledError ---

async def test_cancel_mid_board(tmp):
    board = SwallowingBoard()
    engine = make_engine(tmp, board=board)
    started = await engine.start(request="Build a warehouse inventory app")
    run_id = started["run_id"]
    await asyncio.sleep(0.2)
    ok = await engine.cancel(run_id)
    check("cancel returns True", ok is True)
    run = engine.get_run(run_id)
    check("run forced to cancelled", run.status == "cancelled")
    check("in-flight stage marked cancelled", run.stages[0].status == "cancelled")


# --- cancel on a non-running run is refused ---

async def test_cancel_not_running(tmp):
    engine = make_engine(tmp)
    run_id = (await engine.start_sync(request="Build a warehouse inventory app"))["id"]
    check("cancel on completed run refused", await engine.cancel(run_id) is False)


# --- persistence ---

async def test_persistence(tmp):
    data_file = os.path.join(tmp, "runs.json")
    engine1 = WorkflowEngine(
        config=None,
        llm_manager=StubLLM(),
        board=FakeBoard(),
        research=FakeLayer("research"),
        ux=FakeLayer("ux"),
        design=FakeLayer("design"),
        growth=FakeLayer("growth"),
        quality=FakeLayer("quality"),
        data_file=data_file,
    )
    run_id = ((await engine1.start_sync(request="Build a warehouse inventory app"))["id"])
    engine2 = WorkflowEngine(
        config=None,
        llm_manager=StubLLM(),
        board=FakeBoard(),
        research=FakeLayer("research"),
        ux=FakeLayer("ux"),
        design=FakeLayer("design"),
        growth=FakeLayer("growth"),
        quality=FakeLayer("quality"),
        data_file=data_file,
    )
    run = engine2.get_run(run_id)
    check("persisted run reloaded", run is not None)
    check("persisted status kept", run.status == "completed")
    check("persisted stages kept", len(run.stages) == 6 and all(s.status == "approved" for s in run.stages))
    check("delete missing returns False", engine2.delete_run("nope") is False)


async def main():
    tmp = tempfile.mkdtemp(prefix="workflow_test_")
    engine = make_engine(tmp)
    test_stage_defs(engine)
    await test_happy_path(tmp)
    await test_reject_at_board(tmp)
    await test_retry_at_board(tmp)
    await test_reject_at_ux(tmp)
    await test_retry_at_ux(tmp)
    await test_retry_not_paused(tmp)
    await test_cancel(tmp)
    await test_cancel_mid_board(tmp)
    await test_cancel_not_running(tmp)
    await test_persistence(tmp)
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
