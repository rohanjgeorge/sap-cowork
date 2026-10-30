from backend.app.runtime import Runtime
from backend.app.models import Decision, Clarification


def test_compaction_preserves_durable_data_and_transcript(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD")
    state = storage.load_state("p")
    state.decisions.append(Decision(description="Full quantity only"))
    state.open_clarifications.append(Clarification(question="Confirm schedule"))
    storage.save_state("p", state)
    r.context_session.append("p", "user", "Repeated background " * 7000)
    r.context_session.append("p", "user", "Generate FRD next")
    before = r.context_session.status("p")
    memory = storage.load_memory("p")
    artifact = storage.load_artifact("p", "BRD")
    with storage.transaction("p"):
        after = r.context_session.compact("p")
    assert after["used_tokens"] < before["used_tokens"]
    assert after["compactions"] == 1
    assert storage.load_state("p") == state
    assert storage.load_memory("p") == memory
    assert storage.load_artifact("p", "BRD") == artifact
    assert len(storage.load_session("p")["messages"]) == 2
    assert storage.load_session("p")["working_messages"][-1]["content"] == "Generate FRD next"
