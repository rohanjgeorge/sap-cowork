from backend.app.settings import SettingsService, MemorySecretStore, ProviderSettingsInput


def test_credentials_outside_serialized_settings(tmp_path):
    secrets = MemorySecretStore()
    service = SettingsService(tmp_path, secrets)
    value = ProviderSettingsInput(
        provider="openai", default_model="configured-model", credential="private-key"
    )
    result = service.configure(value)
    assert "private-key" not in result.model_dump_json()
    assert "private-key" not in (tmp_path / "settings/local.json").read_text()
    assert secrets.get("local/openai/default") == "private-key"
    assert service.current().credential_reference == "local/openai/default"
    assert "private-key" not in repr(value)
    service.configure(ProviderSettingsInput(provider="openai", default_model="another-model"))
    assert service.current().credential_reference == "local/openai/default"
