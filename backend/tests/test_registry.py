import pytest
from backend.app.capabilities import CapabilityRegistry
from backend.app.models import CapabilityRequest, CapabilityResponse


class Stub:
    def invoke(self, request):
        return CapabilityResponse(
            task_id=request.task_id,
            capability_id=request.capability_id,
            status="success",
            output={"marker": "replacement"},
        )


def test_registration_replacement_and_contract():
    registry = CapabilityRegistry()
    request = CapabilityRequest(task_id="t", project_id="p", capability_id="ABAP_GENERATOR")
    with pytest.raises(ValueError):
        registry.invoke("ABAP_GENERATOR", request)
    registry.register("ABAP_GENERATOR", Stub())
    assert registry.invoke("ABAP_GENERATOR", request).output["marker"] == "replacement"
