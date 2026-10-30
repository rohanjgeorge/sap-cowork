from backend.app.runtime import Runtime


def test_brd_vertical_slice(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    result = runtime.orchestrator.run("p", "BRD")
    artifact = storage.load_artifact("p", "BRD", "1")
    assert artifact.content and artifact.template_version == "1.0"
    assert artifact.approval_status == "pending_approval"
    assert result["state"].current_stage == "Planning"
    assert result["state"].task_status == "awaiting_approval"
    assert result["state"].artifact_registry[0].version == "1"
