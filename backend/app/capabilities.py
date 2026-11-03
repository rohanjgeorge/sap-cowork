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
        # Capabilities receive a snapshot, never a mutable alias of the parent's
        # authoritative invocation state. Persistent writes belong to services.
        snapshot = request.model_copy(deep=True)
        from .models import ProjectState, TaskProjectView
        from .router import ARTIFACT_CAPABILITY

        if isinstance(snapshot.state, ProjectState):
            kind = next((k.value for k, v in ARTIFACT_CAPABILITY.items() if v == capability_id), None)
            snapshot.state = TaskProjectView.from_state(
                snapshot.state, kind, snapshot.context.upstream_artifacts if snapshot.context else None
            )
        result = implementation.invoke(snapshot)
        if result.task_id != request.task_id or result.capability_id != capability_id:
            raise ValueError("Capability response correlation mismatch")
        if result.request_id is not None and result.request_id != (request.request_id or request.task_id):
            raise ValueError("Capability request correlation mismatch")
        result.request_id = request.request_id or request.task_id
        return result

    def configured(self):
        return [key for key, value in self._implementations.items() if value is not None]

    def output_contract(self, capability_id):
        from .router import ARTIFACT_CAPABILITY

        return "artifact" if capability_id in ARTIFACT_CAPABILITY.values() else "result"

    def describe(self):
        return [
            {
                "capability_id": key,
                "kind": "subgraph_agentic"
                if key == "RESEARCH"
                else "subgraph"
                if key == "AUDIT_WORKER"
                else "external_module"
                if key == "ABAP_GENERATOR"
                else "tool_adapter"
                if key == "SAP_LOOKUP"
                else "artifact_worker",
                "configured": self._implementations[key] is not None,
            }
            for key in sorted(self._implementations)
        ]
