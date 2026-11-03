"""Provider failures must be actionable without exposing SDK messages or credentials."""

import sys
from types import SimpleNamespace
import pytest
from backend.app.model_gateway import LiteLLMProvider, ModelAccessError
from backend.app.models import ModelRequest
from backend.app.settings import ProviderConfiguration, MemorySecretStore
from backend.app.runtime import Runtime


def adapter(monkeypatch, completion):
    class Timeout(Exception):
        pass

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=completion, Timeout=Timeout))
    secrets = MemorySecretStore()
    secrets.set("test", "test-only-private-key")
    return LiteLLMProvider(
        ProviderConfiguration(
            provider="openai", default_model="configured-model", credential_reference="test"
        ),
        secrets,
    )


@pytest.mark.parametrize(
    "status,provider_code,expected",
    [
        (401, None, "PROVIDER_AUTHENTICATION_FAILED"),
        (403, None, "PROVIDER_PERMISSION_DENIED"),
        (404, None, "PROVIDER_MODEL_NOT_FOUND"),
        (429, "insufficient_quota", "PROVIDER_QUOTA_EXCEEDED"),
        (429, None, "PROVIDER_RATE_LIMITED"),
        (400, "invalid_json_schema", "PROVIDER_INVALID_REQUEST"),
        (503, None, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_provider_errors_are_classified_without_raw_sdk_details(monkeypatch, status, provider_code, expected):
    def failure(**kwargs):
        error = RuntimeError("Authorization: Bearer test-only-private-key; private project prompt")
        error.status_code = status
        error.code = provider_code
        raise error

    provider = adapter(monkeypatch, failure)
    with pytest.raises(ModelAccessError) as caught:
        provider.complete(ModelRequest(task_id="t", messages=[]))
    assert caught.value.code == expected
    assert "test-only-private-key" not in str(caught.value)
    assert "private project prompt" not in str(caught.value)


@pytest.mark.parametrize(
    "finish,refusal,content,expected",
    [
        ("length", None, '{"content":', "PROVIDER_OUTPUT_TRUNCATED"),
        ("stop", "sensitive refusal text", "", "PROVIDER_REFUSAL"),
        ("stop", None, "not JSON", "PROVIDER_INVALID_OUTPUT"),
    ],
)
def test_structured_response_failures_explain_the_safe_reason(
    monkeypatch, finish, refusal, content, expected
):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish, message=SimpleNamespace(content=content, refusal=refusal, tool_calls=[])
            )
        ],
        usage=None,
    )
    provider = adapter(monkeypatch, lambda **kwargs: response)
    with pytest.raises(ModelAccessError) as caught:
        provider.complete(ModelRequest(task_id="t", messages=[], structured_output_schema={"type": "object"}))
    assert caught.value.code == expected


def test_brd_failure_returns_safe_model_reason_and_no_artifact(storage, tmp_path, monkeypatch):
    runtime = Runtime(storage, tmp_path)

    def failure(request):
        raise ModelAccessError("test-only-private-key", code="PROVIDER_QUOTA_EXCEEDED")

    monkeypatch.setattr(runtime.worker.gateway, "complete", failure)
    result = runtime.orchestrator.run("p", "BRD", task_id="failed-brd")
    assert result["error_code"] == "PROVIDER_QUOTA_EXCEEDED"
    assert "quota" in result["error"].lower()
    assert "test-only-private-key" not in str(result)
    assert storage.load_state("p").task_status == "failed"
    assert storage.list_artifacts("p") == []
