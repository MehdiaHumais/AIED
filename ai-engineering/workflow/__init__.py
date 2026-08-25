"""Cross-Layer Workflow Orchestration.

Walks a product request through the gated layer chain:

    Layer 2 Board -> Layer 3 Research -> Layer 4 UX -> Layer 5 Design
                  -> Layer 6 Growth -> Layer 7 Quality

Every gate is an Executive Product Board review. Approved gates auto-advance
to the next layer; a rejected/revision gate pauses the run so the user can
edit the pending request and retry. Earlier approved work is kept.
"""

from workflow.engine import WorkflowEngine, _STAGE_DEFS
from workflow.models import WorkflowRun, WorkflowStage

__all__ = ["WorkflowEngine", "WorkflowRun", "WorkflowStage", "_STAGE_DEFS"]
