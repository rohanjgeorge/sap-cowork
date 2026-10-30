from backend.app.runtime import Runtime


def test_approval_updates_registry_and_recommends_analysis(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD")
    r.approvals.review("p", "BRD", "1", True)
    state = storage.load_state("p")
    assert state.artifact_registry[0].approval_status == "approved"
    assert state.recommended_stage == "Analysis"
    assert state.expected_next_artifact == "FRD"


def test_rejection_feedback_and_new_version_preserve_old(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD")
    first = storage.load_artifact("p", "BRD", "1").content
    r.approvals.review("p", "BRD", "1", False, "Include exception report")
    r.orchestrator.run("p", "BRD")
    assert storage.load_artifact("p", "BRD", "1").content == first
    assert storage.load_artifact("p", "BRD", "1").approval_status == "rejected"
    assert storage.load_artifact("p", "BRD", "2").approval_status == "pending_approval"
    assert r.gateway.fake.calls[-1].context["revision_instructions"] == "Include exception report"
