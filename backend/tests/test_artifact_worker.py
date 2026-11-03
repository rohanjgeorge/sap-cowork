from backend.app.artifact_worker import ArtifactWorker
from backend.app.model_gateway import ModelGateway
from backend.app.settings import SettingsService
from backend.app.models import ArtifactGenerationRequest, ContextPackage, ContextItem, ProjectState
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
            context_package=ContextPackage(
                project_id="p",
                task_id="t",
                business_context=[
                    ContextItem(
                        content="Qualified source",
                        source="source:1",
                        source_type="curated",
                        qualification="inferred",
                        conflict="Conflicting evidence needs user review",
                        source_version="1",
                    )
                ],
            ),
            relevant_state=ProjectState(project_id="p", requirement="STO automation"),
        )
    )
    assert result.status == "success"
    assert result.artifact.template_version == "brd.md"
    assert result.artifact.approval_status == "draft"
    assert "## 7. Business Rules" in result.artifact.content
    assert gateway.fake.calls[0].task_id == "t"
    evidence = gateway.fake.calls[0].context["knowledge_evidence"][0]
    assert evidence["qualification"] == "inferred" and evidence["conflict"]
    assert evidence["source_version"] == "1"
