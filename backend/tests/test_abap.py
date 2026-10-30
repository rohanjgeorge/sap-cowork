from backend.app.abap import ABAPStub
from backend.app.runtime import Runtime


def test_draft_tdd_abap_generation_has_nonblocking_error(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "TDD")
    result = r.orchestrator.run("p", "ABAP")
    assert result["artifact"].artifact_type == "ABAP"
    assert len(r.abap.invocations) == 1
    issue = next(i for i in result["state"].issues if i.code == "TDD_UNAPPROVED")
    assert issue.severity == "error" and not issue.blocking
    assert "pending_approval" in result["artifact"].content


def test_abap_replaced_without_orchestrator_change(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    replacement = ABAPStub()
    r.registry.register("ABAP_GENERATOR", replacement)
    result = r.orchestrator.run("p", "ABAP")
    assert result["artifact"]
    assert len(replacement.invocations) == 1
    assert len(r.abap.invocations) == 0
