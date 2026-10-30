import json
from backend.app.runtime import Runtime
from backend.app.settings import ProviderSettingsInput, MemorySecretStore


def test_allowlisted_audit_has_required_fields_and_no_content_or_secrets(storage, tmp_path):
    r = Runtime(storage, tmp_path, MemorySecretStore())
    r.settings.configure(
        ProviderSettingsInput(provider="openai", default_model="private-model", credential="TOP-SECRET")
    )
    r.settings.configure(ProviderSettingsInput(provider="fake", default_model="deterministic-v1"))
    r.orchestrator.run("p", "BRD", task_id="audited")
    events = storage.list_events("p")
    result = next(e for e in events if e["kind"] == "capability_result")
    assert result["task_id"] == "audited" and result["capability_id"] == "BRD_GENERATOR"
    assert result["provider"] == "fake" and result["usage"]["prompt_tokens"] > 0
    assert "BUSINESS" in result["context_domains"]
    encoded = json.dumps(events)
    assert "TOP-SECRET" not in encoded and "Automate STO deliveries" not in encoded


def test_workers_have_no_provider_sdk_dependencies():
    from pathlib import Path

    root = Path(__file__).parents[1] / "app"
    for name in ["orchestrator.py", "artifact_worker.py", "abap.py", "context_handler.py"]:
        content = (root / name).read_text()
        assert "import litellm" not in content
        assert "from openai" not in content
        assert "import anthropic" not in content
