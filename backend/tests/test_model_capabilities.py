import pytest
from backend.app.model_gateway import ModelGateway, ModelCompatibilityError
from backend.app.models import ModelRequest
from backend.app.settings import SettingsService


@pytest.mark.parametrize("requirement", ["tool_calling", "vision", "streaming"])
def test_incompatible_models_rejected_before_invocation(tmp_path, requirement):
    gateway = ModelGateway(SettingsService(tmp_path))
    with pytest.raises(ModelCompatibilityError):
        gateway.complete(ModelRequest(task_id="t", messages=[], model_profile={requirement: True}))
    assert not gateway.fake.calls


def test_context_overflow_rejected(tmp_path):
    gateway = ModelGateway(SettingsService(tmp_path))
    with pytest.raises(ModelCompatibilityError):
        gateway.complete(ModelRequest(task_id="t", messages=[{"content": "x" * 100000}]))
    assert not gateway.fake.calls
