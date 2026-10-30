from backend.app.runtime import Runtime


def test_hooks_are_called_on_generation(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    result = r.orchestrator.run("p", "BRD", task_id="hooks")
    assert result["artifact"]
    assert r.orchestrator.guardrail.calls == ["hooks"]
    assert r.orchestrator.validator.calls == ["hooks"]
