from unittest.mock import create_autospec
from backend.app.storage import StorageProvider


def test_provider_protocol_contract():
    provider = create_autospec(StorageProvider, instance=True)
    assert isinstance(provider, StorageProvider)
    provider.load_artifact("p", "TDD", "1")
    provider.load_artifact.assert_called_once_with("p", "TDD", "1")
