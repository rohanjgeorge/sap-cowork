"""Provider-neutral domain contracts. No storage or worker implementation dependencies."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    TDD = "TDD"
    UAT = "UAT"
    AUDIT_REPORT = "AUDIT_REPORT"
    ABAP = "ABAP"


class ContextDomain(StrEnum):
    BUSINESS = "BUSINESS"
    SAP = "SAP"
    ORGANIZATION = "ORGANIZATION"
    HISTORICAL_DEVELOPMENT = "HISTORICAL_DEVELOPMENT"
    SDLC = "SDLC"


class CapabilityStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    CLARIFICATION_REQUIRED = "clarification_required"


class Project(Contract):
    project_id: str = Field(default_factory=uid)
    project_name: str = Field(min_length=1, max_length=150)
    current_state_id: str | None = None
    model_policy: str | None = "user_default"
    description: str = ""
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
    response: str | None = None
    task_id: str | None = None
    domain: ContextDomain = ContextDomain.BUSINESS


class Decision(Contract):
    decision_id: str = Field(default_factory=uid)
    description: str


class ProjectIssue(Contract):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    blocking: bool = False
    stage: SDLCStage


class ProjectState(Contract):
    project_id: str
    current_stage: SDLCStage = SDLCStage.PLANNING
    current_task: str | None = None
    expected_next_artifact: str | None = "BRD"
    artifact_registry: list[ArtifactReference] = Field(default_factory=list)
    open_clarifications: list[Clarification] = Field(default_factory=list)
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


class ProjectMemory(Contract):
    project_id: str
    content: str = ""
    updated_at: datetime = Field(default_factory=now)


class ContextItem(Contract):
    content: str
    source: str
    source_type: str


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


class Artifact(Contract):
    artifact_id: str
    project_id: str
    artifact_type: ArtifactType
    content: str
    artifact_version: str
    template_version: str
    approval_status: ApprovalStatus = ApprovalStatus.PENDING_APPROVAL
    created_date: datetime = Field(default_factory=now)
    last_edited_date: datetime = Field(default_factory=now)
    edited_by: str | None = None
    approved_by: str | None = None
    feedback: str | None = None
    source_task_id: str | None = None
    sources: list[str] = Field(default_factory=list)

    def reference(self) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            version=self.artifact_version,
            approval_status=self.approval_status,
        )


class CapabilityRequest(Contract):
    task_id: str
    project_id: str
    capability_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    context: ContextPackage | None = None
    state: ProjectState | None = None


class CapabilityResponse(Contract):
    task_id: str
    capability_id: str
    status: CapabilityStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    clarification_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == CapabilityStatus.FAILED and not self.error:
            raise ValueError("failed capability requires error")
        if self.status == CapabilityStatus.CLARIFICATION_REQUIRED and not self.clarification_questions:
            raise ValueError("clarification_required needs questions")
        return self


class ArtifactGenerationRequest(Contract):
    task_id: str
    project_id: str
    artifact_type: ArtifactType
    template: str
    template_version: str
    upstream_artifacts: list[Artifact] = Field(default_factory=list)
    context_package: ContextPackage
    relevant_state: ProjectState
    artifact_version: str = "1"
    instructions: str = ""


class ArtifactGenerationResponse(Contract):
    status: CapabilityStatus
    artifact: Artifact | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    error: str | None = None


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
