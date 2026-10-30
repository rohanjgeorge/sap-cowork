from backend.app.orchestrator import Orchestrator
from backend.app.capabilities import CapabilityRegistry
from backend.app.models import CapabilityResponse, Artifact


class ArtifactStub:
    def invoke(self, request):
        artifact = Artifact(
            artifact_id="BRD",
            project_id=request.project_id,
            artifact_type="BRD",
            content="# BRD",
            artifact_version="1",
            template_version="1",
            source_task_id=request.task_id,
        )
        return CapabilityResponse(
            task_id=request.task_id,
            capability_id=request.capability_id,
            status="success",
            output={"artifact": artifact.model_dump(mode="json")},
        )


def test_machine_persists_result_and_retry_is_idempotent(storage):
    registry = CapabilityRegistry()
    registry.register("BRD_GENERATOR", ArtifactStub())
    orchestrator = Orchestrator(storage, registry)
    result = orchestrator.run("p", "BRD", task_id="same-task")
    assert result["state"].task_status == "awaiting_approval"
    assert storage.load_state("p").active_task_id == "same-task"
    assert orchestrator.run("p", "BRD", task_id="same-task")["replayed"]
    assert len(storage.list_artifacts("p")) == 1


def test_capability_failure_sets_failed(storage):
    orchestrator = Orchestrator(storage, CapabilityRegistry())
    assert orchestrator.run("p", "BRD")["state"].task_status == "failed"
    assert storage.list_artifacts("p") == []


def test_storage_failure_does_not_commit_or_advance(storage, monkeypatch):
    import pytest

    registry = CapabilityRegistry()
    registry.register("BRD_GENERATOR", ArtifactStub())
    before = storage.load_state("p")
    monkeypatch.setattr(storage, "save_artifact", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        Orchestrator(storage, registry).run("p", "BRD")
    assert storage.load_state("p") == before
    assert storage.list_artifacts("p") == []
