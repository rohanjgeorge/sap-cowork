import pytest

from backend.app.local_storage import LocalStorageProvider
from backend.app.models import Artifact, Project, ProjectState
from backend.app.state_management import StateError, StateManagementService


def setup(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    service = StateManagementService(storage)
    service.create_project(Project(project_id="p", project_name="CR"))
    return storage, service


def register(storage, service, kind, version="1"):
    artifact = Artifact(
        artifact_id=kind,
        project_id="p",
        artifact_type=kind,
        artifact_version=version,
        content="A valid source",
        template_version="test.md",
    )
    storage.save_artifact("p", artifact)
    service.apply("p", "register_artifact", {"artifact_id": kind, "version": version})
    return service.apply("p", "approve_artifact", {"artifact_id": kind, "version": version})


def test_stage_progression_navigation_and_old_state_migration(tmp_path):
    storage, service = setup(tmp_path)
    old = ProjectState.model_validate(
        {"project_id": "old", "current_stage": "Design", "open_clarifications": []}
    )
    assert old.current_draft_stage == "Design" and old.clarifications == []
    register(storage, service, "FRD")
    assert register(storage, service, "TDD").current_approved_stage == "Planning"
    assert register(storage, service, "BRD").current_approved_stage == "Analysis"
    assert register(storage, service, "USER_STORIES").current_approved_stage == "Development"
    state = service.apply("p", "change_draft_stage", {"stage": "Testing"})
    assert state.current_draft_stage == "Testing" and state.current_approved_stage == "Development"
    # Draft revisions retain the previously approved baseline.
    storage.save_artifact(
        "p",
        Artifact(
            artifact_id="BRD",
            project_id="p",
            artifact_type="BRD",
            artifact_version="2",
            content="new draft",
            template_version="brd.md",
        ),
    )
    state = service.apply("p", "register_artifact", {"artifact_id": "BRD", "version": "2"})
    assert state.artifacts["BRD"].latest_version == 2
    assert state.artifacts["BRD"].latest_approved_version == 1
    assert state.current_approved_stage == "Development"


def test_revision_idempotency_authorization_and_closed_project(tmp_path):
    storage, service = setup(tmp_path)
    state = service.apply(
        "p", "change_draft_stage", {"stage": "Design"}, expected_revision=1, request_id="once"
    )
    replay = service.apply(
        "p", "change_draft_stage", {"stage": "Design"}, expected_revision=1, request_id="once"
    )
    assert replay == state and storage.load_state("p").state_revision == 2
    with pytest.raises(StateError, match="Request ID already used"):
        service.apply("p", "change_draft_stage", {"stage": "Testing"}, request_id="once")
    with pytest.raises(StateError, match="REVISION_CONFLICT"):
        service.apply("p", "change_draft_stage", {"stage": "Testing"}, expected_revision=1)
    with pytest.raises(StateError, match="UNAUTHORIZED"):
        service.apply("p", "close_project", actor="worker")
    assert service.apply("p", "close_project").project_status == "incomplete"
    with pytest.raises(StateError, match="PROJECT_CLOSED"):
        service.apply("p", "set_requirement", {"requirement": "changed"})
    assert service.apply("p", "reopen_project").project_status == "active"


def test_invalid_state_operations_and_backup_recovery(tmp_path):
    storage, service = setup(tmp_path)
    before = storage.load_state("p")
    with pytest.raises(StateError, match="VALIDATION_ERROR"):
        service.apply("p", "change_draft_stage", {})
    assert storage.load_state("p") == before
    service.apply("p", "change_draft_stage", {"stage": "Design"})
    (tmp_path / "project/p/state/project_state.json").write_text("invalid JSON")
    recovered = storage.load_state("p")
    assert recovered.project_id == "p" and recovered.current_draft_stage == "Design"
    assert storage.load_state("p") == recovered


def test_editing_same_test_version_invalidates_testing_confirmation(tmp_path):
    from backend.app.artifact_lifecycle import ArtifactLifecycle
    from backend.app.state_management import accepted

    storage, service = setup(tmp_path)
    for kind in ("ABAP", "SIT", "UAT"):
        register(storage, service, kind)
    state = service.apply("p", "confirm_testing")
    assert accepted(state, "testing")
    # An approved test edit forks a new draft and requires a fresh baseline.
    ArtifactLifecycle(storage, service).edit("p", "UAT", "Changed test expectations")
    assert not accepted(storage.load_state("p"), "testing")


def test_confirmation_baselines_survive_restart_and_withdrawal(tmp_path):
    storage, service = setup(tmp_path)
    for kind in ("BRD", "FRD", "USER_STORIES", "TDD", "ABAP", "SIT", "UAT"):
        register(storage, service, kind)
    state = service.apply("p", "confirm_code")
    assert state.current_approved_stage == "Testing"
    state = StateManagementService(LocalStorageProvider(tmp_path)).apply("p", "confirm_testing")
    assert state.follow_ups["audit_report"] == "pending"
    state = service.apply("p", "withdraw_confirmation", {"kind": "testing"})
    assert state.current_approved_stage == "Testing"
    assert not state.confirmations[-1].active
    state = service.apply("p", "withdraw_confirmation", {"kind": "development"})
    assert state.current_approved_stage == "Development"
    assert storage.load_artifact("p", "ABAP").approval_status == "approved"
    service.apply("p", "confirm_code")
    service.apply("p", "confirm_testing")
    assert service.apply("p", "close_project").project_status == "completed"
