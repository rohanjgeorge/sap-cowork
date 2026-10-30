from backend.app.context_planner import ContextPlanner
from backend.app.models import ProjectState


def test_task_specific_context_profiles():
    state = ProjectState(project_id="p", active_task_id="t", current_task="Generate BRD")
    planner = ContextPlanner()
    assert planner.plan(state, "BRD").required_domains == ["BUSINESS", "SDLC"]
    assert "HISTORICAL_DEVELOPMENT" in planner.plan(state, "TDD").required_domains
    assert "BUSINESS" not in planner.plan(state, "ABAP").required_domains
