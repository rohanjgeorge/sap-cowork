import pytest
from backend.app.runtime import Runtime


@pytest.mark.parametrize("kind,capability", [("UAT", "UAT_GENERATOR"), ("AUDIT_REPORT", "AUDIT_WORKER")])
def test_testing_capabilities_use_shared_worker_and_stop_before_deployment(
    storage, tmp_path, kind, capability
):
    runtime = Runtime(storage, tmp_path)
    result = runtime.orchestrator.run("p", kind)
    assert result["artifact"].artifact_type == kind
    assert result["state"].current_stage == "Testing"
    assert result["state"].active_capability_id == capability
    runtime.approvals.review("p", kind, "1", True)
    assert storage.load_state("p").recommended_stage is None
