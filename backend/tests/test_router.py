import pytest
from backend.app.models import ProjectState, ArtifactReference
from backend.app.router import route, dependency_issues


@pytest.mark.parametrize(
    "stage,capability",
    [
        ("Planning", "BRD_GENERATOR"),
        ("Analysis", "FRD_GENERATOR"),
        ("Design", "TDD_GENERATOR"),
        ("Development", "ABAP_GENERATOR"),
        ("Testing", "UAT_GENERATOR"),
    ],
)
def test_stage_router(stage, capability):
    assert route(stage)[0] == capability


def test_missing_brd_warning_and_draft_abap_error_nonblocking():
    state = ProjectState(project_id="p")
    assert dependency_issues(state, "FRD")[0].severity == "warning"
    assert not dependency_issues(state, "FRD")[0].blocking
    state.artifact_registry.append(
        ArtifactReference(artifact_id="TDD", artifact_type="TDD", version="1", approval_status="draft")
    )
    issue = dependency_issues(state, "ABAP")[0]
    assert issue.severity == "error" and not issue.blocking
