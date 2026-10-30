import pytest
from fastapi.testclient import TestClient
from backend.app.runtime import Runtime
from backend.app.api import create_app
from backend.app.settings import MemorySecretStore


def test_reviewing_upstream_does_not_discard_waiting_task(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    state = storage.load_state("p")
    state.requirement = "STO delivery when material available"
    storage.save_state("p", state)
    runtime.orchestrator.run("p", "BRD")
    runtime.approvals.review("p", "BRD", "1", True)
    runtime.orchestrator.run("p", "FRD")
    waiting = storage.load_state("p")
    runtime.approvals.review("p", "BRD", "1", True)
    assert storage.load_state("p").task_status == "awaiting_input"
    assert storage.load_state("p").active_task_id == waiting.active_task_id
    assert storage.load_state("p").expected_next_artifact == "FRD"
    with pytest.raises(ValueError, match="pending clarification"):
        runtime.orchestrator.run("p", "TDD")


def test_task_identity_cannot_be_reused_for_different_artifact(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    runtime.orchestrator.run("p", "BRD", task_id="fixed")
    with pytest.raises(ValueError, match="different artifact"):
        runtime.orchestrator.run("p", "TDD", task_id="fixed")


def test_long_change_request_is_captured_before_generation(tmp_path):
    with TestClient(create_app(tmp_path, MemorySecretStore(), access_code="")) as client:
        client.post("/api/session", json={"access_code": ""})
        p = client.post("/api/projects", json={"project_name": "Raw request"}).json()["project"]["project_id"]
        requirement = (
            "Create delivery notes in SAP for STOs.\n"
            + "Include failure reporting and duplicate prevention. " * 4
        )
        result = client.post(f"/api/projects/{p}/chat", json={"message": requirement}).json()
        assert result["workspace"]["state"]["requirement"] == requirement
        assert result["workspace"]["state"]["artifact_registry"] == []


def test_revision_feedback_reaches_worker_through_api(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        p = client.post("/api/projects", json={"project_name": "Revision", "requirement": "STO"}).json()[
            "project"
        ]["project_id"]
        client.post(f"/api/projects/{p}/chat", json={"action": "generate", "artifact_type": "BRD"})
        client.post(
            f"/api/projects/{p}/artifacts/BRD/review",
            json={"action": "reject", "version": "1", "feedback": "Add exception report"},
        )
        client.post(f"/api/projects/{p}/chat", json={"action": "generate", "artifact_type": "BRD"})
        assert (
            app.state.runtime.gateway.fake.calls[-1].context["revision_instructions"]
            == "Add exception report"
        )
