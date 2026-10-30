"""User settings and OS-backed credentials are deliberately outside project storage."""

from pathlib import Path
from typing import Protocol

from pydantic import Field, SecretStr

from .local_storage import LocalStorageProvider, safe_id
from .models import Contract, ModelProfile


class SecretStore(Protocol):
    def set(self, reference: str, value: str) -> None: ...
    def get(self, reference: str) -> str | None: ...


class KeyringSecretStore:
    def set(self, reference, value):
        import keyring

        keyring.set_password("SAP-CoWork", reference, value)

    def get(self, reference):
        import keyring

        return keyring.get_password("SAP-CoWork", reference)


class MemorySecretStore:
    """Test-only credential store; never selected by production configuration."""

    def __init__(self):
        self.values = {}

    def set(self, reference, value):
        self.values[reference] = value

    def get(self, reference):
        return self.values.get(reference)


class ProviderConfiguration(Contract):
    provider: str = "fake"
    credential_reference: str | None = None
    default_model: str = "deterministic-v1"
    base_url: str | None = None
    connection_status: str = "untested"
    capabilities: ModelProfile = Field(default_factory=ModelProfile)


class UserSettings(Contract):
    user_id: str = "local"
    default_provider: str = "fake"
    providers: dict[str, ProviderConfiguration] = Field(
        default_factory=lambda: {"fake": ProviderConfiguration()}
    )


class ProviderSettingsInput(Contract):
    provider: str
    default_model: str = Field(min_length=1)
    credential: SecretStr | None = None
    base_url: str | None = None
    capabilities: ModelProfile = Field(default_factory=ModelProfile)


class SettingsService:
    def __init__(self, root: Path, secrets: SecretStore | None = None):
        self.root = Path(root) / "settings"
        self.secrets = secrets or KeyringSecretStore()

    def load(self, user_id="local"):
        path = self.root / f"{safe_id(user_id)}.json"
        return (
            UserSettings.model_validate_json(path.read_text())
            if path.exists()
            else UserSettings(user_id=user_id)
        )

    def save(self, settings):
        LocalStorageProvider._atomic(
            self.root / f"{safe_id(settings.user_id)}.json", settings.model_dump_json(indent=2).encode()
        )

    def configure(self, value: ProviderSettingsInput, user_id="local"):
        if value.provider not in {"fake", "openai", "anthropic", "qwen", "openai-compatible"}:
            raise ValueError("Unsupported provider")
        if value.provider in {"qwen", "openai-compatible"} and not value.base_url:
            raise ValueError("This provider requires a base URL")
        if value.base_url and not value.base_url.startswith(
            ("https://", "http://127.0.0.1", "http://localhost")
        ):
            raise ValueError("Base URL must use HTTPS or loopback HTTP")
        settings = self.load(user_id)
        previous = settings.providers.get(value.provider)
        reference = previous.credential_reference if previous else None
        if value.credential:
            reference = f"{user_id}/{value.provider}/default"
            self.secrets.set(reference, value.credential.get_secret_value())
        settings.providers[value.provider] = ProviderConfiguration(
            provider=value.provider,
            credential_reference=reference,
            default_model=value.default_model,
            base_url=value.base_url,
            capabilities=value.capabilities,
        )
        settings.default_provider = value.provider
        self.save(settings)
        return settings

    def current(self, policy=None):
        settings = self.load()
        selected = settings.default_provider if policy in (None, "user_default") else policy
        if selected not in settings.providers:
            raise ValueError("Requested provider has not been configured")
        return settings.providers[selected]
