import base64
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.app.runtime import Runtime


def test_crash_journal_is_recovered_on_next_transaction(storage):
    project = storage.root / "project/p"
    original = (project / "state/project_state.json").read_bytes()
    (project / ".journal.json").write_text(
        json.dumps({"state/project_state.json": base64.b64encode(original).decode()})
    )
    (project / "state/project_state.json").write_text('{"project_id":"p","current_stage":"Testing"}')
    with storage.transaction("p"):
        assert storage.load_state("p").current_stage == "Planning"
    assert not (project / ".journal.json").exists()


def test_memory_failure_rolls_back_artifact_state_and_audit(storage, tmp_path, monkeypatch):
    runtime = Runtime(storage, tmp_path)
    state = storage.load_state("p")

    def fail(*args):
        raise OSError("simulated memory persistence failure")

    monkeypatch.setattr(storage, "save_memory", fail)
    with pytest.raises(OSError):
        runtime.orchestrator.run("p", "BRD")
    assert storage.load_state("p") == state
    assert storage.list_artifacts("p") == []
    assert storage.list_events("p") == []


def test_simultaneous_duplicate_tasks_commit_one_artifact(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: runtime.orchestrator.run("p", "BRD", task_id="shared"), range(3)))
    assert len(storage.list_artifacts("p")) == 1
    assert sum(bool(result.get("replayed")) for result in results) == 2
