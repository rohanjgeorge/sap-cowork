from unittest.mock import Mock
import pytest
from backend.app.model_gateway import ModelGateway, FakeModelProvider, ModelAccessError
from backend.app.models import ModelRequest, ModelResponse
from backend.app.settings import SettingsService, MemorySecretStore


def test_fake_contract_and_bounded_retries(tmp_path):
    fake = FakeModelProvider()
    gateway = ModelGateway(SettingsService(tmp_path, MemorySecretStore()), fake)
    request = ModelRequest(
        task_id="t", messages=[], context={"template": "# BRD\n## Scope", "requirement": "STO"}
    )
    result = gateway.complete(request)
    assert ModelResponse.model_validate_json(result.model_dump_json()) == result
    assert "## Scope" in result.structured_output["content"]
    fake.complete = Mock(side_effect=TimeoutError())
    with pytest.raises(ModelAccessError):
        gateway.complete(request)
    assert fake.complete.call_count == 3
    assert all(call.args[0].task_id == "t" for call in fake.complete.call_args_list)
