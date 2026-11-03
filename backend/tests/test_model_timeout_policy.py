"""Document generation needs one longer request, not repeated short requests."""

from types import SimpleNamespace
import pytest
from backend.app.model_gateway import LiteLLMProvider, ModelGateway, ModelAccessError
from backend.app.models import ModelRequest
from backend.app.settings import SettingsService, ProviderSettingsInput, MemorySecretStore
from test_provider_errors import adapter


def test_artifact_adapter_allows_a_document_that_exceeds_old_sixty_second_limit(monkeypatch):
    def complete(**kwargs):
        assert kwargs["timeout"] == 180
        assert kwargs["num_retries"] == 0
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"content":"BRD"}', tool_calls=[]), finish_reason="stop"
                )
            ],
            usage=None,
        )

    provider = adapter(monkeypatch, complete)
    assert (
        provider.complete(
            ModelRequest(
                task_id="t",
                messages=[],
                context={"operation": "artifact_generation"},
                structured_output_schema={"type": "object"},
            )
        ).structured_output["content"]
        == "BRD"
    )


def test_artifact_timeout_is_configurable_without_changing_planning_limits(monkeypatch):
    monkeypatch.setenv("COWORK_ARTIFACT_TIMEOUT_SECONDS", "240")
    values = []

    def complete(**kwargs):
        values.append(kwargs["timeout"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK", tool_calls=[]))], usage=None
        )

    provider = adapter(monkeypatch, complete)
    provider.complete(
        ModelRequest(task_id="document", messages=[], context={"operation": "artifact_generation"})
    )
    provider.complete(
        ModelRequest(
            task_id="planning",
            messages=[],
            context={"operation": "context_planning"},
            generation_settings={"timeout": 2},
        )
    )
    provider.complete(ModelRequest(task_id="chat", messages=[]))
    assert values == [240, 2, 60]


def test_document_timeout_does_not_automatically_start_duplicate_provider_requests(monkeypatch, tmp_path):
    settings = SettingsService(tmp_path, MemorySecretStore())
    settings.configure(
        ProviderSettingsInput(provider="openai", default_model="configured-model", credential="test-only-key")
    )
    calls = []

    def timeout(self, request):
        calls.append(request.task_id)
        raise TimeoutError("Timeout without response")

    monkeypatch.setattr(LiteLLMProvider, "complete", timeout)
    with pytest.raises(ModelAccessError) as caught:
        ModelGateway(settings).complete(
            ModelRequest(task_id="same-task", messages=[], context={"operation": "artifact_generation"})
        )
    assert caught.value.code == "PROVIDER_TIMEOUT"
    assert calls == ["same-task"]


def test_shared_artifact_worker_marks_the_document_operation(storage, tmp_path):
    from backend.app.runtime import Runtime

    runtime = Runtime(storage, tmp_path)
    result = runtime.orchestrator.run("p", "BRD", task_id="document-policy")
    assert result.get("artifact")
    assert runtime.gateway.fake.calls[-1].context["operation"] == "artifact_generation"


@pytest.mark.parametrize("value", ["0", "601", "nan", "not-a-number"])
def test_invalid_document_timeout_is_rejected_before_provider_invocation(monkeypatch, value):
    from backend.app.model_gateway import ModelCompatibilityError

    monkeypatch.setenv("COWORK_ARTIFACT_TIMEOUT_SECONDS", value)
    calls = []
    provider = adapter(monkeypatch, lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ModelCompatibilityError, match="between 1 and 600"):
        provider.complete(
            ModelRequest(task_id="document", messages=[], context={"operation": "artifact_generation"})
        )
    assert calls == []
