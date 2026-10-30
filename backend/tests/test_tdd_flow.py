from backend.app.runtime import Runtime


def test_backend_vertical_slice_cr_brd_frd_tdd(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    for artifact_type, next_stage in [("BRD", "Analysis"), ("FRD", "Design"), ("TDD", "Development")]:
        result = r.orchestrator.run("p", artifact_type)
        assert result["artifact"].artifact_type == artifact_type
        assert result["artifact"].artifact_version == "1"
        r.approvals.review("p", artifact_type, "1", True)
        assert storage.load_state("p").recommended_stage == next_stage
    assert len(storage.list_artifacts("p")) == 3
    request = r.orchestrator.context_handler.requests[-1]
    assert "SAP" in request.required_domains and "ORGANIZATION" in request.required_domains
