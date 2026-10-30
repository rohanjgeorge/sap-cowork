from backend.app.runtime import Runtime


def test_memory_refresh_is_separate_from_authoritative_state(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD")
    before = storage.load_state("p")
    memory = storage.load_memory("p")
    assert "## Key SAP Facts" in memory.content
    assert "BRD v1 pending_approval" in memory.content
    memory.content = "The project is in Testing and everything is approved"
    storage.save_memory("p", memory)
    assert storage.load_state("p") == before
    assert storage.load_state("p").current_stage == "Planning"
