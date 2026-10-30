import pytest
from backend.app.models import (
    Project,
    ProjectState,
    ProjectMemory,
    Artifact,
    ArtifactReference,
    Clarification,
    Decision,
    ContextRequest,
    ContextPackage,
    ContextItem,
    CapabilityRequest,
    CapabilityResponse,
    ArtifactGenerationRequest,
    ArtifactGenerationResponse,
    ModelRequest,
    ModelResponse,
)


def samples():
    state = ProjectState(project_id="p")
    package = ContextPackage(
        project_id="p",
        task_id="t",
        business_context=[ContextItem(content="Plant 1000", source="CR", source_type="user")],
    )
    artifact = Artifact(
        project_id="p",
        artifact_id="BRD",
        artifact_type="BRD",
        content="# BRD",
        artifact_version="1",
        template_version="1.0",
    )
    return [
        Project(project_name="Contract project"),
        state,
        ProjectMemory(project_id="p"),
        artifact,
        ArtifactReference(artifact_id="BRD", artifact_type="BRD", version="1", approval_status="draft"),
        Clarification(question="Which plant?"),
        Decision(description="Plant 1000"),
        ContextRequest(
            project_id="p",
            task_id="t",
            current_stage="Planning",
            current_task="BRD",
            required_domains=["BUSINESS"],
        ),
        package,
        CapabilityRequest(
            project_id="p", task_id="t", capability_id="BRD_GENERATOR", context=package, state=state
        ),
        CapabilityResponse(
            task_id="t",
            capability_id="BRD_GENERATOR",
            status="success",
            output={"artifact": artifact.model_dump(mode="json")},
        ),
        ArtifactGenerationRequest(
            project_id="p",
            task_id="t",
            artifact_type="BRD",
            template="# BRD",
            template_version="1.0",
            context_package=package,
            relevant_state=state,
        ),
        ArtifactGenerationResponse(status="success", artifact=artifact),
        ModelRequest(task_id="t", messages=[{"role": "user", "content": "CR"}]),
        ModelResponse(content="Result", provider="fake", model="demo", status="success"),
    ]


@pytest.mark.parametrize("instance", samples(), ids=lambda x: type(x).__name__)
def test_contract_survives_json_transport(instance):
    assert type(instance).model_validate_json(instance.model_dump_json()) == instance
