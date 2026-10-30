from backend.app.artifact_worker import ArtifactWorker
from backend.app.model_gateway import ModelGateway
from backend.app.settings import SettingsService
from backend.app.models import ArtifactGenerationRequest, ContextPackage, ProjectState
from backend.app.templates import TemplateRepository


def test_shared_worker_uses_template_and_returns_typed_artifact(tmp_path):
    gateway = ModelGateway(SettingsService(tmp_path))
    template, version = TemplateRepository().load("BRD")
    result = ArtifactWorker(gateway).generate(
        ArtifactGenerationRequest(
            task_id="t",
            project_id="p",
            artifact_type="BRD",
            template=template,
            template_version=version,
            context_package=ContextPackage(project_id="p", task_id="t"),
            relevant_state=ProjectState(project_id="p", requirement="STO automation"),
        )
    )
    assert result.status == "success"
    assert result.artifact.template_version == "1.0"
    assert result.artifact.approval_status == "pending_approval"
    assert "## Business Rules" in result.artifact.content
    assert gateway.fake.calls[0].task_id == "t"
