import json
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import pytest

from backend.app.model_gateway import LiteLLMProvider, ModelAccessError
from backend.app.models import ModelRequest
from backend.app.settings import MemorySecretStore, ProviderConfiguration


@pytest.mark.parametrize(
    "provider,prefix",
    [("openai", "openai"), ("anthropic", "anthropic"), ("qwen", "openai"), ("openai-compatible", "openai")],
)
def test_litellm_adapter_contract_without_network(monkeypatch, provider, prefix):
    secrets = MemorySecretStore()
    secrets.set("ref", "test-key-never-logged")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps({"content": "artifact", "clarification_questions": []}), tool_calls=[]
                )
            )
        ],
        usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 10, "completion_tokens": 5}),
    )
    completion = Mock(return_value=response)
    module = SimpleNamespace(completion=completion, Timeout=TimeoutError)
    monkeypatch.setitem(sys.modules, "litellm", module)
    adapter = LiteLLMProvider(
        ProviderConfiguration(
            provider=provider,
            default_model="configured-model",
            credential_reference="ref",
            base_url="https://gateway.example/v1",
        ),
        secrets,
    )
    result = adapter.complete(
        ModelRequest(
            task_id="t",
            messages=[{"role": "user", "content": "Generate"}],
            context={"fact": "source data"},
            structured_output_schema={"type": "object"},
        )
    )
    args = completion.call_args.kwargs
    assert args["model"] == prefix + "/configured-model"
    assert args["api_base"] == "https://gateway.example/v1"
    assert args["api_key"] == "test-key-never-logged"
    assert args["response_format"]["type"] == "json_schema"
    assert result.structured_output["content"] == "artifact"
    assert "test-key-never-logged" not in result.model_dump_json()


def test_provider_exception_details_are_sanitized(monkeypatch):
    secrets = MemorySecretStore()
    secrets.set("ref", "private-secret")
    module = SimpleNamespace(
        completion=Mock(side_effect=RuntimeError("Headers: private-secret")), Timeout=TimeoutError
    )
    monkeypatch.setitem(sys.modules, "litellm", module)
    adapter = LiteLLMProvider(ProviderConfiguration(provider="openai", credential_reference="ref"), secrets)
    with pytest.raises(ModelAccessError) as error:
        adapter.complete(ModelRequest(task_id="t", messages=[]))
    assert "private-secret" not in str(error.value)
