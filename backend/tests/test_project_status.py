from backend.app.runtime import Runtime


def test_stage_colors_and_recommendations(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    assert [s["color"] for s in r.status.get("p")["stages"]] == ["amber", "grey", "grey", "grey", "grey"]
    r.orchestrator.run("p", "BRD")
    assert r.status.get("p")["stages"][0]["color"] == "amber"
    r.approvals.review("p", "BRD", "1", True)
    status = r.status.get("p")
    assert status["stages"][0]["color"] == "green"
    assert status["recommended_stage"] == "Analysis"
    assert status["stages"][0]["documents"][0]["approval_status"] == "approved"


def test_pm_error_is_visible_and_does_not_block_abap(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "TDD")
    assert r.orchestrator.run("p", "ABAP")["artifact"]
    issue = next(i for i in r.status.get("p")["issues"] if i["code"] == "TDD_UNAPPROVED")
    assert issue["severity"] == "error" and not issue["blocking"]
