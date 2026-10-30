"""Regression coverage for a connected provider receiving no ordinary chat calls."""

from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient

from backend.app.api import create_app
from backend.app.model_gateway import LiteLLMProvider, ModelAccessError
from backend.app.models import ModelResponse
from backend.app.settings import MemorySecretStore


@pytest.fixture
def live_client(tmp_path, monkeypatch):
    complete = Mock(
        return_value=ModelResponse(
            content="A real model reply about your SAP project.",
            provider="openai",
            model="configured-openai-model",
            status="success",
            usage={"prompt_tokens": 20},
        )
    )
    monkeypatch.setattr(LiteLLMProvider, "complete", complete)
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        client.put(
            "/api/settings/provider",
            json={
                "provider": "openai",
                "default_model": "configured-openai-model",
                "credential": "test-only-not-a-real-key",
            },
        )
        project = client.post("/api/projects", json={"project_name": "Connected chat"}).json()["project"][
            "project_id"
        ]
        yield client, app.state.runtime, project, complete


@pytest.mark.parametrize("message", ["hi", "hello", "What is 2 plus 2?", "Explain SAP sales orders"])
def test_ordinary_chat_uses_saved_openai_provider_and_not_demo(live_client, message):
    client, runtime, project, complete = live_client
    # First send a greeting as in the reported reproduction, then a follow-up.
    response = client.post(f"/api/projects/{project}/chat", json={"message": message})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["message"] == "A real model reply about your SAP project."
    complete.assert_called_once()
    assert runtime.gateway.fake.calls == []
    last = result["workspace"]["session"]["messages"][-1]
    assert last["origin"] == "model" and last["provider"] == "openai"
    assert result["workspace"]["state"]["artifact_registry"] == []
    if message in ("hi", "hello") or "?" in message:
        assert result["workspace"]["state"]["requirement"] == ""


def test_chat_failure_does_not_fall_back_to_fake_or_repeat_workflow(live_client):
    client, runtime, project, complete = live_client
    complete.side_effect = ModelAccessError("Provider request failed; check configuration and model access")
    result = client.post(f"/api/projects/{project}/chat", json={"message": "Hello"}).json()
    assert "Provider request failed" in result["message"]
    assert result["error"]
    assert runtime.gateway.fake.calls == []
    assert "demo" not in result["message"].lower()


def test_chat_preserves_active_approval_and_uses_recent_user_history(live_client):
    client, runtime, project, complete = live_client
    with runtime.storage.transaction(project):
        state = runtime.storage.load_state(project)
        state.requirement = "Automate deliveries"
        state.task_status = "awaiting_approval"
        state.active_task_id = "artifact-task"
        state.current_task = "Generate BRD"
        runtime.storage.save_state(project, state)
    before = runtime.storage.load_state(project)
    client.post(f"/api/projects/{project}/chat", json={"message": "What inputs do you need?"})
    client.post(f"/api/projects/{project}/chat", json={"message": "Please explain further"})
    assert complete.call_count == 2
    assert runtime.storage.load_state(project) == before
    messages = complete.call_args.args[0].messages
    assert any(m["content"] == "What inputs do you need?" for m in messages)
    assert any(m["content"] == "A real model reply about your SAP project." for m in messages)


def test_streaming_chat_reaches_model_and_workflow_status_remains_deterministic(live_client):
    client, runtime, project, complete = live_client
    response = client.post(f"/api/projects/{project}/chat/stream", json={"message": "Hi"})
    assert "A real model reply about your SAP project." in response.text
    assert "PROJECT_CHAT" in response.text
    complete.assert_called_once()
    client.post(f"/api/projects/{project}/chat", json={"message": "status"})
    complete.assert_called_once()


def test_artifact_worker_uses_connected_openai_and_never_demo(live_client):
    client, runtime, project, complete = live_client

    def generate(request):
        template = request.context["template"]
        content = "\n\n".join(
            line + "\nVerified provider content." for line in template.splitlines() if line.startswith("#")
        )
        return ModelResponse(
            content=content,
            structured_output={"content": content, "clarification_questions": []},
            provider="openai",
            model="configured-openai-model",
            status="success",
        )

    complete.side_effect = generate
    client.post(
        f"/api/projects/{project}/chat",
        json={"action": "submit_requirement", "message": "Automate deliveries"},
    )
    result = client.post(
        f"/api/projects/{project}/chat", json={"action": "generate", "artifact_type": "BRD"}
    ).json()
    assert result["artifact"]["approval_status"] == "pending_approval"
    assert "Verified provider content." in result["artifact"]["content"]
    assert "demonstration" not in result["artifact"]["content"].lower()
    assert runtime.gateway.fake.calls == []


def test_fake_chat_is_explicitly_labeled(tmp_path):
    with TestClient(create_app(tmp_path, MemorySecretStore(), access_code="")) as client:
        client.post("/api/session", json={"access_code": ""})
        project = client.post("/api/projects", json={"project_name": "Demo chat"}).json()["project"][
            "project_id"
        ]
        result = client.post(f"/api/projects/{project}/chat", json={"message": "Hi"}).json()
        assert "Demo mode is selected" in result["message"]
        assert result["provider"] == "fake"
        assert result["workspace"]["state"]["requirement"] == ""
