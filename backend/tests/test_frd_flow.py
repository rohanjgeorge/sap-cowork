from backend.app.runtime import Runtime


def test_frd_clarification_then_resume(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    state = storage.load_state("p")
    state.requirement = "Automate 150 STO deliveries per day when material available, plants 1000 to 1100"
    storage.save_state("p", state)
    r.orchestrator.run("p", "BRD")
    r.approvals.review("p", "BRD", "1", True)
    paused = r.orchestrator.run("p", "FRD")
    assert paused["state"].task_status == "awaiting_input"
    assert r.orchestrator.context_handler.requests[-1].required_domains == [
        "BUSINESS",
        "SAP",
        "ORGANIZATION",
        "HISTORICAL_DEVELOPMENT",
        "SDLC",
    ]
    clarification = paused["state"].open_clarifications[-1]
    resumed = r.orchestrator.clarifications.answer(
        r.orchestrator,
        "p",
        clarification.clarification_id,
        "Use unrestricted stock in supplying plant 1000; full quantity; no partial delivery",
    )
    assert resumed["artifact"].artifact_type == "FRD"
    assert resumed["state"].active_task_id == paused["state"].active_task_id
    assert any(s.startswith("clarification:") for s in resumed["artifact"].sources)
    r.approvals.review("p", "FRD", "1", True)
    assert storage.load_state("p").recommended_stage == "Design"


def test_missing_brd_allows_frd(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    result = r.orchestrator.run("p", "FRD")
    assert result["artifact"].artifact_type == "FRD"
    assert result["state"].issues[0].code == "BRD_MISSING"
