import pytest
from fastapi.testclient import TestClient
from backend.app.api import create_app
from backend.app.settings import MemorySecretStore


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="test-code")
    with TestClient(app) as client:
        assert client.get("/api/projects").status_code == 401
        assert client.post("/api/session", json={"access_code": "wrong"}).status_code == 401
        client.post("/api/session", json={"access_code": "test-code"})
        yield client


def test_api_vertical_slice_and_shared_state(client):
    created = client.post("/api/projects", json={"project_name": "STO API"}).json()
    p = created["project"]["project_id"]
    assert (
        client.post(
            f"/api/projects/{p}/chat",
            json={"message": "Automate STO deliveries", "action": "submit_requirement"},
        ).status_code
        == 200
    )
    for kind, next_stage in [("BRD", "Analysis"), ("FRD", "Design"), ("TDD", "Development")]:
        generated = client.post(
            f"/api/projects/{p}/chat", json={"action": "generate", "artifact_type": kind}
        ).json()
        assert generated["artifact"]["artifact_type"] == kind, generated
        assert (
            client.get(f"/api/projects/{p}/artifacts/{kind}?version=1").json()["approval_status"]
            == "pending_approval"
        )
        approved = client.post(
            f"/api/projects/{p}/artifacts/{kind}/review", json={"action": "approve", "version": "1"}
        ).json()
        assert approved["workspace"]["status"]["recommended_stage"] == next_stage
    assert len(client.get("/api/projects").json()) == 1
    assert len(client.get(f"/api/projects/{p}/artifacts").json()) == 3
    assert client.get(f"/api/projects/{p}/state").json()["current_stage"] == "Design"
    assert client.get(f"/api/projects/{p}").json()["memory"]["content"]
    assert client.get(f"/api/projects/{p}/context").json()["estimated"]
    compact = client.post(f"/api/projects/{p}/context/compact").json()
    assert compact["context"]["compactions"] == 1


def test_upload_versions_settings_stream_and_errors(client, monkeypatch):
    p = client.post("/api/projects", json={"project_name": "Files"}).json()["project"]["project_id"]
    upload = client.post(
        f"/api/projects/{p}/files",
        files={"file": ("frd.md", b"# Functional scope")},
        data={"artifact_type": "FRD", "domain": "BUSINESS"},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]
    assert client.get(f"/api/projects/{p}/files/{file_id}").content == b"# Functional scope"
    assert len(client.get(f"/api/projects/{p}/files").json()) == 2
    assert client.get("/api/settings").json()["default_provider"] == "fake"
    assert client.post("/api/settings/provider/test").json()["status"] == "connected"
    settings = client.put(
        "/api/settings/provider",
        json={"provider": "openai", "default_model": "model", "credential": "private-secret"},
    ).json()
    assert "private-secret" not in str(settings)
    from backend.app.model_gateway import LiteLLMProvider, ModelAccessError

    def unavailable(*args):
        raise ModelAccessError("Simulated provider failure")

    monkeypatch.setattr(LiteLLMProvider, "complete", unavailable)
    assert client.post("/api/settings/provider/test").json()["status"] == "failed"
    client.put("/api/settings/provider", json={"provider": "fake", "default_model": "deterministic-v1"})
    response = client.post(
        f"/api/projects/{p}/chat/stream", json={"action": "generate", "artifact_type": "BRD"}
    )
    assert "text/event-stream" in response.headers["content-type"]
    assert '"task_status": "executing"' in response.text
    assert '"type": "result"' in response.text
    assert client.get("/api/projects/not-found").status_code == 404
    assert client.post("/api/projects", json={"project_name": ""}).status_code == 422
    assert (
        client.post(
            "/api/projects", json={"project_name": "bad"}, headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.delete("/api/session").json()["signed_out"]
    assert client.get("/api/projects").status_code == 401
