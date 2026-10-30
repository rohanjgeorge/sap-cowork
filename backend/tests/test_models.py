import pytest
from pydantic import ValidationError
from backend.app.models import (
    ProjectState,
    Project,
    TaskStatus,
    SDLCStage,
    ApprovalStatus,
    ContextItem,
    CapabilityResponse,
    CapabilityStatus,
    ProjectIssue,
    ModelRequest,
    Decision,
)


def test_state_roundtrip_and_list_isolation():
    state = ProjectState(project_id="one")
    state.decisions.append(Decision(decision_id="d", description="plant 1000"))
    encoded = state.model_dump_json()
    assert ProjectState.model_validate_json(encoded).current_stage == SDLCStage.PLANNING
    assert ProjectState(project_id="two").decisions == []
    assert "api_key" not in encoded


@pytest.mark.parametrize("enum", [TaskStatus, SDLCStage, ApprovalStatus, CapabilityStatus])
def test_enum_serialization(enum):
    for value in enum:
        assert enum(value.value) == value


def test_invalid_contracts_rejected():
    with pytest.raises(ValidationError):
        Project(project_name="")
    with pytest.raises(ValidationError):
        ContextItem(content="fact")
    with pytest.raises(ValidationError):
        CapabilityResponse(task_id="t", capability_id="x", status="clarification_required")
    with pytest.raises(ValidationError):
        ProjectState(project_id="p", api_key="secret")


def test_error_does_not_imply_blocking_and_request_roundtrip():
    issue = ProjectIssue(
        code="TDD_UNAPPROVED", message="Approval missing", severity="error", stage="Development"
    )
    assert not issue.blocking
    request = ModelRequest(task_id="t", messages=[{"role": "user", "content": "Hello"}])
    assert ModelRequest.model_validate_json(request.model_dump_json()) == request
