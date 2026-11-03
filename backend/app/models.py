"""Provider-neutral domain contracts. No storage or worker implementation dependencies."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return uuid4().hex


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SDLCStage(StrEnum):
    PLANNING = "Planning"
    ANALYSIS = "Analysis"
    DESIGN = "Design"
    DEVELOPMENT = "Development"
    TESTING = "Testing"


class TaskStatus(StrEnum):
    IDLE = "idle"
    UNDERSTANDING = "understanding"
    AWAITING_INPUT = "awaiting_input"
    PLANNING_CONTEXT = "planning_context"
    READY_TO_EXECUTE = "ready_to_execute"
    EXECUTING = "executing"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class ArtifactType(StrEnum):
    BRD = "BRD"
    FRD = "FRD"
    USER_STORIES = "USER_STORIES"
    TDD = "TDD"
    UAT = "UAT"
    SIT = "SIT"
    AUDIT_REPORT = "AUDIT_REPORT"
    ABAP = "ABAP"


class ContextDomain(StrEnum):
    FUNCTIONAL_PROCESS = "FUNCTIONAL_PROCESS"
    SAP_FUNCTIONAL = "SAP_FUNCTIONAL"
    SAP_TECHNICAL = "SAP_TECHNICAL"
    STANDARDS_GOVERNANCE = "STANDARDS_GOVERNANCE"
    BUSINESS = "BUSINESS"
    SAP = "SAP"
    ORGANIZATION = "ORGANIZATION"
    HISTORICAL_DEVELOPMENT = "HISTORICAL_DEVELOPMENT"
    SDLC = "SDLC"


class CapabilityStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    CLARIFICATION_REQUIRED = "clarification_required"
    CONTEXT_REQUIRED = "context_required"


class SourceCategory(StrEnum):
    CONVERSATION = "SRC-01"
    UPLOAD = "SRC-02"
    ARTIFACT = "SRC-03"
    STATE_MEMORY = "SRC-04"
    SAP_STANDARD = "SRC-05"
    ORGANIZATION = "SRC-06"
    HISTORICAL = "SRC-07"
    CONNECTED_SYSTEM = "SRC-08"
    SUPPORT_COMMUNITY = "SRC-09"


class Project(Contract):
    project_id: str = Field(default_factory=uid)
    project_name: str = Field(min_length=1, max_length=150)
    client_name: str | None = Field(default=None, max_length=150)
    current_state_id: str | None = None
    model_policy: str | None = "user_default"
    description: str = ""
    organization_id: str | None = None
    tenant_id: str | None = None
    sap_applicability: dict[str, str] = Field(default_factory=dict)
    context_date: datetime | None = None
    program_id: str | None = None
    import_artifacts: list[ArtifactType] = Field(default_factory=list)
    import_artifact_statuses: dict[ArtifactType, Literal["draft", "approved"]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class ArtifactReference(Contract):
    artifact_id: str
    artifact_type: ArtifactType
    version: str
    approval_status: ApprovalStatus


class Clarification(Contract):
    clarification_id: str = Field(default_factory=uid)
    question: str
    status: Literal["open", "resolved"] = "open"
    resolution: str | None = Field(default=None, validation_alias=AliasChoices("resolution", "response"))
    task_id: str | None = None
    domain: ContextDomain = ContextDomain.BUSINESS
    source: Literal["user", "orchestrator", "worker"] = "orchestrator"
    related_artifact: str | None = None
    created_at: datetime = Field(default_factory=now)
    resolved_at: datetime | None = None

    @property
    def response(self):
        return self.resolution

    @response.setter
    def response(self, value):
        self.resolution = value


class Decision(Contract):
    decision_id: str = Field(default_factory=uid)
    description: str
    decided_by: str = "local"
    related_artifact: str | None = None
    related_stage: SDLCStage | None = None
    created_at: datetime = Field(default_factory=now)


class Flag(Contract):
    flag_id: str = Field(default_factory=uid)
    type: Literal["warning", "blocker", "exception"] = "warning"
    description: str
    status: Literal["active", "resolved"] = "active"
    source: Literal["orchestrator", "worker", "system"] = "system"
    related_artifact: str | None = None
    created_at: datetime = Field(default_factory=now)
    resolved_at: datetime | None = None
    code: str | None = None
    related_stage: SDLCStage | None = None
    capability_id: str | None = None


class CompletionRecord(Contract):
    confirmation_id: str = Field(default_factory=uid)
    kind: Literal["development", "testing"]
    active: bool = True
    artifacts: list[ArtifactReference]
    actor: str
    confirmed_at: datetime = Field(default_factory=now)
    withdrawn_at: datetime | None = None
    remarks: str = ""
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class ArtifactRegistryEntry(Contract):
    artifact_id: str
    artifact_type: ArtifactType
    status: str = "not_started"
    latest_version: int | None = None
    latest_approved_version: int | None = None
    storage_ref: str | None = None
    latest_approved_storage_ref: str | None = None
    template_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    content_hash: str | None = None


class ProjectIssue(Contract):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    blocking: bool = False
    stage: SDLCStage


class ProjectState(Contract):
    project_id: str
    project_name: str = ""
    project_status: Literal["active", "completed", "incomplete"] = "active"
    program_id: str | None = None
    current_draft_stage: SDLCStage = Field(
        default=SDLCStage.PLANNING, validation_alias=AliasChoices("current_draft_stage", "current_stage")
    )
    current_approved_stage: SDLCStage = SDLCStage.PLANNING
    schema_version: str = "1.1"
    state_revision: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=now)
    artifacts: dict[str, ArtifactRegistryEntry] = Field(default_factory=dict)
    current_task: str | None = None
    expected_next_artifact: str | None = "BRD"
    artifact_registry: list[ArtifactReference] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(
        default_factory=list, validation_alias=AliasChoices("clarifications", "open_clarifications")
    )
    decisions: list[Decision] = Field(default_factory=list)
    recommended_next_action: str | None = "Generate BRD"
    recommended_stage: SDLCStage | None = None
    active_task_id: str | None = None
    task_status: TaskStatus = TaskStatus.IDLE
    active_capability_id: str | None = None
    task_inputs: dict[str, Any] = Field(default_factory=dict)
    requirement: str = ""
    issues: list[ProjectIssue] = Field(default_factory=list)
    started_stages: list[SDLCStage] = Field(default_factory=lambda: [SDLCStage.PLANNING])
    completed_tasks: dict[str, ArtifactReference] = Field(default_factory=dict)
    flags: list[Flag] = Field(default_factory=list)
    confirmations: list[CompletionRecord] = Field(default_factory=list)
    follow_ups: dict[str, str] = Field(default_factory=dict)

    @property
    def current_stage(self):
        return self.current_draft_stage

    @current_stage.setter
    def current_stage(self, value):
        self.current_draft_stage = value

    @property
    def open_clarifications(self):
        return self.clarifications

    @open_clarifications.setter
    def open_clarifications(self, value):
        self.clarifications = value


class ProjectMemory(Contract):
    project_id: str
    content: str = ""
    updated_at: datetime = Field(default_factory=now)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class ContextItem(Contract):
    content: str
    source: str
    source_type: str
    scope: Literal["global", "organization", "project"] = "project"
    organization_id: str | None = None
    program_id: str | None = None
    source_version: str | None = None
    origin: str | None = None
    copied_at: datetime | None = None
    applicability: dict[str, str] = Field(default_factory=dict)
    qualification: str = "user_supplied"
    conflict: str | None = None
    source_id: str | None = None
    original_uri: str | None = None
    object_id: str | None = None
    source_category: SourceCategory | None = None
    acquisition_method: str | None = None
    project_id: str | None = None
    tenant_id: str | None = None
    domain: ContextDomain | None = None
    topic: str | None = None
    derived_version: int = 1
    observed_at: datetime | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    retrieval_action_ref: str | None = None
    retrieval_action_refs: list[str] = Field(default_factory=list)
    evidence_status: Literal["verified", "supported", "inferred", "disputed", "unknown"] = "unknown"
    authority: Literal["project", "official_standard", "target_system", "guidance", "unverified"] = (
        "unverified"
    )
    approval_status: str | None = None
    lineage: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)
    allowed_projects: list[str] = Field(default_factory=list)
    allowed_publication_scopes: list[str] = Field(default_factory=lambda: ["project"])
    access_status: Literal["allowed", "revoked"] = "allowed"
    confidential: bool = False
    rights: str = "Project use only; publication requires a separate policy"
    project_customized: bool = False
    adapter_id: str | None = None
    content_digest: str | None = None
    structured_facts: dict[str, str] = Field(default_factory=dict)
    derivation_refs: list[dict[str, Any]] = Field(default_factory=list)


class ContextRequirement(Contract):
    requirement_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1200)
    domain: ContextDomain = ContextDomain.SDLC
    priority: Literal["essential", "recommended"] = "recommended"
    source_categories: list[SourceCategory] = Field(default_factory=list)
    query: str = Field(default="", max_length=500)
    user_owned: bool = False
    material: bool = False
    requires_verification: bool = False
    claim: Literal["project_requirement", "standard_behavior", "target_implementation", "guidance"] = (
        "guidance"
    )


class ContextGap(Contract):
    requirement_id: str
    gap_type: Literal[
        "missing",
        "user_owned",
        "conflict",
        "uncertain",
        "inaccessible",
        "unavailable",
        "exhausted",
        "budget",
        "reasoning_unavailable",
    ]
    impact: Literal["warning", "material", "escalation"] = "warning"
    attempted_sources: list[str] = Field(default_factory=list)
    planned_sources: list[str] = Field(default_factory=list)
    unattempted_sources: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str
    follow_up: str = "Review before relying on this evidence"
    qualification: str = "Qualified draft; do not assert missing facts as confirmed"


class ContextBudget(Contract):
    max_attempts: int = Field(default=2, ge=1, le=5)
    max_actions: int = Field(default=12, ge=1, le=50)
    max_seconds: float = Field(default=10, gt=0, le=120)
    max_tokens: int = Field(default=5000, ge=1000, le=16000)
    max_model_calls: int = Field(default=1, ge=0, le=1)
    max_replans: int = Field(default=2, ge=0, le=4)


class ContextPlan(Contract):
    plan_id: str
    project_id: str
    task_id: str
    stage: SDLCStage
    artifact_type: ArtifactType
    profile_version: str = "1.0"
    requirements: list[ContextRequirement] = Field(default_factory=list)
    candidate_sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_actions: list[dict[str, Any]] = Field(default_factory=list)
    constraints: ContextBudget = Field(default_factory=ContextBudget)
    attempts: int = 0
    actions_used: int = 0
    model_calls: int = 0
    elapsed_seconds: float = 0
    cycle: int = 0
    coverage: dict[str, str] = Field(default_factory=dict)
    gaps: list[ContextGap] = Field(default_factory=list)
    reasoning_status: str = "not_requested"
    package_ref: str | None = None
    outcome: Literal[
        "planning", "awaiting_input", "ready", "qualified", "escalated", "context_budget_exceeded"
    ] = "planning"
    template_ref: str | None = None
    template_digest: str | None = None
    targeted_requirements: list[str] = Field(default_factory=list)
    as_of: datetime = Field(default_factory=now)


class ContextRequest(Contract):
    project_id: str
    task_id: str
    current_stage: SDLCStage
    current_task: str
    required_domains: list[ContextDomain]
    upstream_artifacts: list[str] = Field(default_factory=list)
    query: str | None = None


class ContextPackage(Contract):
    project_id: str
    task_id: str
    business_context: list[ContextItem] = Field(default_factory=list)
    sap_context: list[ContextItem] = Field(default_factory=list)
    organization_context: list[ContextItem] = Field(default_factory=list)
    historical_context: list[ContextItem] = Field(default_factory=list)
    sdlc_context: list[ContextItem] = Field(default_factory=list)
    upstream_artifacts: list[ArtifactReference] = Field(default_factory=list)
    functional_process_context: list[ContextItem] = Field(default_factory=list)
    sap_functional_context: list[ContextItem] = Field(default_factory=list)
    sap_technical_context: list[ContextItem] = Field(default_factory=list)
    standards_governance_context: list[ContextItem] = Field(default_factory=list)
    package_id: str | None = None
    package_ref: str | None = None
    plan_ref: str | None = None
    profile_version: str | None = None
    gaps: list[ContextGap] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class Artifact(Contract):
    artifact_id: str
    project_id: str
    artifact_type: ArtifactType
    content: str
    artifact_version: str
    template_version: str
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    created_date: datetime = Field(default_factory=now)
    last_edited_date: datetime = Field(default_factory=now)
    edited_by: str | None = None
    approved_by: str | None = None
    feedback: str | None = None
    source_task_id: str | None = None
    sources: list[str] = Field(default_factory=list)
    template_ref: str | None = None
    task_profile_ref: str | None = None
    task_profile_version: str | None = None
    approved_at: datetime | None = None
    approval_declared_by: str | None = None
    upstream: list[ArtifactReference] = Field(default_factory=list)
    version_history: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    deleted: bool = False
    context_package_ref: str | None = None
    context_plan_ref: str | None = None
    context_gaps: list[ContextGap] = Field(default_factory=list)
    evidence_provenance: list[dict[str, Any]] = Field(default_factory=list)
    validation_findings: list[dict[str, Any]] = Field(default_factory=list)

    def reference(self) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            version=self.artifact_version,
            approval_status=self.approval_status,
        )


class FrozenValues(dict):
    def _deny(self, *args, **kwargs):
        raise TypeError("Task view values are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _deny
    __ior__ = _deny

    def __deepcopy__(self, memo):
        return self


class TaskProjectView(Contract):
    """Immutable task-scoped compatibility view, never authoritative state."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: str
    project_name: str
    current_draft_stage: SDLCStage
    current_approved_stage: SDLCStage
    current_task: str | None
    active_task_id: str | None
    requirement: str
    task_inputs: dict[str, Any]
    artifact_registry: tuple[ArtifactReference, ...]
    decisions: tuple[Decision, ...]
    clarifications: tuple[Clarification, ...]
    flags: tuple[Flag, ...]
    completion_info: tuple[dict[str, Any], ...] = ()

    @property
    def current_stage(self):
        return self.current_draft_stage

    @classmethod
    def from_state(cls, state, artifact_type=None, upstream_refs=None):
        def freeze(value):
            if isinstance(value, dict):
                return FrozenValues({k: freeze(v) for k, v in value.items()})
            if isinstance(value, list):
                return tuple(freeze(v) for v in value)
            return value

        def frozen_model(value):
            subtype = type(
                "Task" + type(value).__name__,
                (type(value),),
                {"model_config": ConfigDict(extra="forbid", frozen=True)},
            )
            return subtype.model_validate(value.model_dump())

        relevant = {artifact_type, *[r.artifact_type for r in (upstream_refs or [])]}
        view = cls(
            project_id=state.project_id,
            project_name=state.project_name,
            current_draft_stage=state.current_draft_stage,
            current_approved_stage=state.current_approved_stage,
            current_task=state.current_task,
            active_task_id=state.active_task_id,
            requirement=state.requirement[:6000],
            task_inputs={
                k: v
                for k, v in state.task_inputs.items()
                if k in {"instructions", "new_version", "authors", "remarks", "model_policy", "upstream_refs"}
            },
            artifact_registry=tuple(
                frozen_model(v) for v in state.artifact_registry if v.artifact_type in relevant
            ),
            decisions=tuple(
                frozen_model(v) for v in state.decisions if v.related_artifact in (None, artifact_type)
            ),
            clarifications=tuple(
                frozen_model(v) for v in state.clarifications if v.related_artifact in (None, artifact_type)
            ),
            flags=tuple(
                frozen_model(v)
                for v in state.flags
                if v.status == "active" and v.related_artifact in (None, artifact_type)
            ),
        )
        object.__setattr__(view, "task_inputs", freeze(view.task_inputs))
        object.__setattr__(
            view,
            "completion_info",
            tuple(
                freeze(c.model_dump(mode="json"))
                for c in state.confirmations
                if any(r.artifact_type in relevant for r in c.artifacts)
            ),
        )
        return view


class CapabilityRequest(Contract):
    request_id: str | None = None
    actor: str = "local"
    input_refs: list[str] = Field(default_factory=list)
    context_package_ref: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    task_id: str
    project_id: str
    capability_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: ContextPackage | None = None
    state: TaskProjectView | ProjectState | None = None


class CapabilityResponse(Contract):
    request_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    task_id: str
    capability_id: str
    status: CapabilityStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    unmet_context_requirements: list[ContextRequirement] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == CapabilityStatus.FAILED and not self.error:
            raise ValueError("failed capability requires error")
        if self.status == CapabilityStatus.CLARIFICATION_REQUIRED and not self.clarification_questions:
            raise ValueError("clarification_required needs questions")
        if self.status == CapabilityStatus.CONTEXT_REQUIRED and not self.unmet_context_requirements:
            raise ValueError("context_required needs structured requirements")
        return self


class ArtifactGenerationRequest(Contract):
    task_profile: dict[str, Any] | None = None
    task_id: str
    project_id: str
    artifact_type: ArtifactType
    template: str
    template_version: str
    upstream_artifacts: list[Artifact] = Field(default_factory=list)
    context_package: ContextPackage
    relevant_state: TaskProjectView | ProjectState
    artifact_version: str = "1"
    instructions: str = ""


class ArtifactGenerationResponse(Contract):
    status: CapabilityStatus
    artifact: Artifact | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    error: str | None = None
    unmet_context_requirements: list[ContextRequirement] = Field(default_factory=list)


class ModelProfile(Contract):
    context_window: int = Field(default=32000, gt=0)
    max_output_tokens: int = Field(default=4096, gt=0)
    structured_output: bool = True
    tool_calling: bool = False
    vision: bool = False
    streaming: bool = False
    reasoning: bool = True
    coding: bool = True


class ModelRequest(Contract):
    task_id: str
    model_profile: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]]
    context: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    structured_output_schema: dict[str, Any] | None = None
    generation_settings: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(Contract):
    content: str | None = None
    structured_output: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    provider: str
    model: str
    status: str
