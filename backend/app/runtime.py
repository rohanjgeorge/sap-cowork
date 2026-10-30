"""Composition root: replacements are wired here, never in the orchestrator."""

from .artifact_worker import ArtifactCapability, ArtifactWorker
from .capabilities import CapabilityRegistry
from .clarifications import ClarificationService
from .context_handler import ContextHandler
from .context_planner import ContextPlanner
from .model_gateway import ModelGateway
from .orchestrator import Orchestrator
from .settings import SettingsService
from .approvals import ApprovalService
from .memory import MemoryService
from .context_session import ContextSessionService
from .hooks import GuardrailHook, ValidationHook
from .abap import ABAPStub
from .project_status import ProjectStatusService
from .sap_lookup import CuratedSAPLookup
from .audit import AuditObserver


class Runtime:
    def __init__(self, storage, settings_root, secrets=None):
        self.storage = storage
        self.settings = SettingsService(settings_root, secrets)
        self.gateway = ModelGateway(self.settings)
        self.registry = CapabilityRegistry()
        self.worker = ArtifactWorker(self.gateway)
        self.registry.register("BRD_GENERATOR", ArtifactCapability("BRD", self.worker, storage))
        self.registry.register("FRD_GENERATOR", ArtifactCapability("FRD", self.worker, storage))
        self.registry.register("TDD_GENERATOR", ArtifactCapability("TDD", self.worker, storage))
        self.orchestrator = Orchestrator(storage, self.registry, ContextPlanner(), ContextHandler(storage))
        self.orchestrator.model_gateway = self.gateway
        self.orchestrator.clarifications = ClarificationService(storage)
        self.memory = MemoryService(storage)
        self.orchestrator.memory_service = self.memory
        self.approvals = ApprovalService(storage, self.memory)
        self.context_session = ContextSessionService(storage, self.settings, self.memory)
        self.orchestrator.context_session = self.context_session
        self.orchestrator.guardrail = GuardrailHook()
        self.orchestrator.validator = ValidationHook()
        self.abap = ABAPStub()
        self.registry.register("ABAP_GENERATOR", self.abap)
        self.status = ProjectStatusService(storage)
        for kind, capability_id in [("UAT", "UAT_GENERATOR"), ("AUDIT_REPORT", "AUDIT_WORKER")]:
            self.registry.register(capability_id, ArtifactCapability(kind, self.worker, storage))
        self.registry.register("SAP_LOOKUP", CuratedSAPLookup(storage))
        self.orchestrator.observer = AuditObserver(storage, self.gateway, self.orchestrator.context_handler)
