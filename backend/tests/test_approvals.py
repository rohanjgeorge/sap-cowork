from backend.app.runtime import Runtime


def test_approval_updates_registry_and_recommends_analysis(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD")
    r.approvals.review("p", "BRD", "1", True)
    state = storage.load_state("p")
    assert state.artifact_registry[0].approval_status == "approved"
    assert state.recommended_stage == "Analysis"
    assert state.expected_next_artifact == "FRD"


def test_draft_change_request_updates_same_version(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD")
    r.approvals.review("p", "BRD", "1", False, "Include exception report")
    r.orchestrator.run("p", "BRD")
    assert storage.load_artifact("p", "BRD", "1").version_history[-1]["edited_at"]
    assert storage.load_artifact("p", "BRD", "1").approval_status == "draft"
    assert len(storage.list_artifacts("p")) == 1
    assert r.gateway.fake.calls[-1].context["revision_instructions"] == "Include exception report"
