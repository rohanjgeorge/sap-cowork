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
from pathlib import Path
from .langgraph_orchestrator import RuntimeAwareApprovals
from .legacy_orchestrator import Orchestrator as LegacyOrchestrator
from .state_management import StateManagementService
from .artifact_lifecycle import ArtifactLifecycle
from .context_sources import SourceRegistry
from .context_planning import ContextPlanningService


class Runtime:
    def __init__(self, storage, settings_root, secrets=None, *, orchestration_backend="langgraph"):
        self.storage = storage
        self.settings = SettingsService(settings_root, secrets)
        self.gateway = ModelGateway(self.settings)
        self.registry = CapabilityRegistry()
        self.state = StateManagementService(storage)
        self.artifacts = ArtifactLifecycle(storage, self.state)
        self.worker = ArtifactWorker(self.gateway)
        self.registry.register("BRD_GENERATOR", ArtifactCapability("BRD", self.worker, storage))
        self.registry.register("FRD_GENERATOR", ArtifactCapability("FRD", self.worker, storage))
        self.registry.register("TDD_GENERATOR", ArtifactCapability("TDD", self.worker, storage))
        if orchestration_backend == "langgraph":
            self.orchestrator = Orchestrator(
                storage,
                self.registry,
                ContextPlanner(),
                ContextHandler(storage),
                checkpoint_path=Path(settings_root) / "runtime" / "langgraph" / "checkpoints.sqlite",
            )
        elif orchestration_backend == "legacy":
            self.orchestrator = LegacyOrchestrator(
                storage, self.registry, ContextPlanner(), ContextHandler(storage)
            )
        else:
            raise ValueError("Unknown orchestration backend")
        self.orchestrator.model_gateway = self.gateway
        self.context_sources = SourceRegistry()
        self.orchestrator.context_handler.source_registry = self.context_sources
        self.context_planning = ContextPlanningService(
            storage,
            self.orchestrator.planner,
            self.orchestrator.context_handler,
            self.context_sources,
            self.gateway,
        )
        from .research import ResearchSubgraph, ResearchCapability

        self.research = ResearchSubgraph(self.context_sources, self.gateway)
        self.context_planning.research = self.research
        self.registry.register("RESEARCH", ResearchCapability(self.research, storage))
        if orchestration_backend == "langgraph":
            self.orchestrator.context_planning = self.context_planning
        self.orchestrator.state_service = self.state
        self.orchestrator.artifact_service = self.artifacts
        self.orchestrator.clarifications = ClarificationService(storage, self.state)
        self.memory = MemoryService(storage)
        self.orchestrator.memory_service = self.memory
        self.approvals = ApprovalService(storage, self.memory, self.state)
        if orchestration_backend == "langgraph":
            self.approvals = RuntimeAwareApprovals(self.approvals, self.orchestrator)
        self.context_session = ContextSessionService(storage, self.settings, self.memory)
        self.orchestrator.context_session = self.context_session
        self.orchestrator.guardrail = GuardrailHook(storage, self.registry, self.context_planning)
        self.orchestrator.validator = ValidationHook(self.registry)
        self.abap = ABAPStub()
        self.registry.register("ABAP_GENERATOR", self.abap)
        self.status = ProjectStatusService(storage)
        if orchestration_backend == "langgraph":
            from .orchestration_events import ParentEventGraph

            self.event_graph = ParentEventGraph(self)
            self.orchestrator.event_graph = self.event_graph
        for kind, capability_id in [
            ("UAT", "UAT_GENERATOR"),
            ("SIT", "SIT_GENERATOR"),
            ("USER_STORIES", "USER_STORIES_GENERATOR"),
            ("AUDIT_REPORT", "AUDIT_WORKER"),
        ]:
            capability = ArtifactCapability(kind, self.worker, storage)
            if kind == "AUDIT_REPORT" and orchestration_backend == "langgraph":
                from .audit_capability import AuditSubgraph

                capability = AuditSubgraph(capability)
            self.registry.register(capability_id, capability)
        self.registry.register("SAP_LOOKUP", CuratedSAPLookup(storage, self.context_sources))
        self.orchestrator.observer = AuditObserver(storage, self.gateway, self.orchestrator.context_handler)
        if orchestration_backend == "legacy":
            from .legacy_workflow import LegacyApprovalService, LegacyClarificationService

            self.orchestrator.clarifications = LegacyClarificationService(storage)
            self.approvals = LegacyApprovalService(storage, self.memory)
