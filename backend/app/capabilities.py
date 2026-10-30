from typing import Protocol
from .models import CapabilityRequest, CapabilityResponse

CAPABILITY_IDS = (
    "BRD_GENERATOR",
    "FRD_GENERATOR",
    "TDD_GENERATOR",
    "UAT_GENERATOR",
    "ABAP_GENERATOR",
    "AUDIT_WORKER",
    "SAP_LOOKUP",
)


class Capability(Protocol):
    def invoke(self, request: CapabilityRequest) -> CapabilityResponse: ...


class CapabilityRegistry:
    def __init__(self):
        self._implementations: dict[str, Capability | None] = dict.fromkeys(CAPABILITY_IDS)

    def register(self, capability_id, implementation: Capability):
        self._implementations[capability_id] = implementation

    def invoke(self, capability_id, request):
        if request.capability_id != capability_id:
            raise ValueError("Capability ID mismatch")
        implementation = self._implementations.get(capability_id)
        if implementation is None:
            raise ValueError(f"Capability {capability_id} is not configured")
        result = implementation.invoke(request)
        if result.task_id != request.task_id or result.capability_id != capability_id:
            raise ValueError("Capability response correlation mismatch")
        return result

    def configured(self):
        return [key for key, value in self._implementations.items() if value is not None]
