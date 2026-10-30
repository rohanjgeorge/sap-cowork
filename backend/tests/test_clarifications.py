from backend.app.capabilities import CapabilityRegistry
from backend.app.clarifications import ClarificationService
from backend.app.context_handler import ContextHandler
from backend.app.context_planner import ContextPlanner
from backend.app.orchestrator import Orchestrator
from backend.app.models import CapabilityResponse


class Success:
    def invoke(self, r):
        return CapabilityResponse(task_id=r.task_id, capability_id=r.capability_id, status="success")


def setup(storage):
    registry = CapabilityRegistry()
    registry.register("BRD_GENERATOR", Success())
    registry.register("FRD_GENERATOR", Success())
    orchestrator = Orchestrator(storage, registry, ContextPlanner(), ContextHandler(storage))
    orchestrator.clarifications = ClarificationService(storage)
    return orchestrator


def test_missing_requirement_blocks_brd_and_answer_resumes(storage):
    state = storage.load_state("p")
    state.requirement = ""
    storage.save_state("p", state)
    o = setup(storage)
    result = o.run("p", "BRD")
    assert result["state"].task_status == "awaiting_input"
    q = result["state"].open_clarifications[0]
    resumed = o.clarifications.answer(o, "p", q.clarification_id, "Automate delivery creation")
    assert resumed["state"].task_status == "completed"
    assert "Automate delivery creation" in storage.load_memory("p").content


def test_material_clarification_pauses_and_resumes_same_task(storage):
    state = storage.load_state("p")
    state.requirement = "Create STO deliveries when material available"
    storage.save_state("p", state)
    o = setup(storage)
    result = o.run("p", "FRD", task_id="stable")
    assert result["state"].task_status == "awaiting_input"
    q = result["state"].open_clarifications[0]
    resumed = o.clarifications.answer(o, "p", q.clarification_id, "Unrestricted stock, full quantity only")
    assert resumed["state"].task_status == "completed"
    assert resumed["state"].active_task_id == "stable"
    assert o.context_handler.requests[-1].task_id == "stable"
