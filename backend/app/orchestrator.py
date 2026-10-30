"""Resumable control plane. Only contracts and capability IDs cross this boundary."""

from .models import (
    Artifact,
    ArtifactType,
    CapabilityRequest,
    CapabilityStatus,
    ContextPackage,
    TaskStatus,
    uid,
)
from .router import ARTIFACT_STAGE, dependency_issues, route
from .storage import StorageProvider
from threading import local


class Orchestrator:
    def __init__(self, storage: StorageProvider, registry, planner=None, context_handler=None):
        self.storage = storage
        self.registry = registry
        self.planner = planner
        self.context_handler = context_handler
        self.clarifications = None
        self.memory_service = None
        self.context_session = None
        self.guardrail = None
        self.validator = None
        self.observer = None
        self.events = local()

    def _transition(self, state, status):
        state.task_status = status
        self.storage.save_state(state.project_id, state)
        if getattr(self.events, "callback", None):
            self.events.callback(
                {"type": "progress", "task_status": status.value, "capability_id": state.active_capability_id}
            )
        if self.observer:
            self.observer(state, {"kind": "transition", "task_status": status.value})

    def run(self, project_id, artifact_type=None, inputs=None, task_id=None):
        with self.storage.transaction(project_id):
            state = self.storage.load_state(project_id)
            if task_id and task_id in state.completed_tasks:
                ref = state.completed_tasks[task_id]
                if artifact_type and ref.artifact_type != artifact_type:
                    raise ValueError("Task ID already belongs to a different artifact request")
                return {
                    "state": state,
                    "artifact": self.storage.load_artifact(project_id, ref.artifact_id, ref.version),
                    "replayed": True,
                }
            if state.task_status == TaskStatus.AWAITING_INPUT and task_id != state.active_task_id:
                raise ValueError("Answer the pending clarification before starting another generation task")
            capability_id, selected = route(state.current_stage, artifact_type)
            state.active_task_id = task_id or uid()
            state.active_capability_id = capability_id
            state.task_inputs = inputs or {}
            state.current_task = f"Generate {selected.value}"
            state.current_stage = ARTIFACT_STAGE[selected]
            state.expected_next_artifact = selected.value
            state.recommended_stage = None
            if state.current_stage not in state.started_stages:
                state.started_stages.append(state.current_stage)
            state.issues = [i for i in state.issues if i.stage != state.current_stage]
            state.issues.extend(dependency_issues(state, selected))
            self._transition(state, TaskStatus.UNDERSTANDING)
            return self._execute(state, selected)

    def _execute(self, state, selected):
        selected = ArtifactType(selected)
        project_id = state.project_id
        self._transition(state, TaskStatus.PLANNING_CONTEXT)
        context = ContextPackage(project_id=project_id, task_id=state.active_task_id)
        if self.planner and self.context_handler:
            context = self.context_handler.load(self.planner.plan(state, selected))
        if self.context_session:
            self.context_session.prepare(state, context)
        if self.clarifications:
            questions = self.clarifications.preflight(state, selected)
            if questions:
                return self.clarifications.pause(state, questions)
        self._transition(state, TaskStatus.READY_TO_EXECUTE)
        if self.guardrail:
            self.guardrail.before_execute(state, context)
        self._transition(state, TaskStatus.EXECUTING)
        request = CapabilityRequest(
            task_id=state.active_task_id,
            project_id=project_id,
            capability_id=state.active_capability_id,
            inputs=state.task_inputs,
            state=state,
            context=context,
        )
        try:
            result = self.registry.invoke(state.active_capability_id, request)
        except Exception as exc:
            self._transition(state, TaskStatus.FAILED)
            return {"state": state, "error": f"Capability execution failed ({type(exc).__name__})"}
        if result.status == CapabilityStatus.CLARIFICATION_REQUIRED:
            if not self.clarifications:
                self._transition(state, TaskStatus.AWAITING_INPUT)
                return {"state": state, "questions": result.clarification_questions}
            return self.clarifications.pause(state, result.clarification_questions)
        if result.status == CapabilityStatus.FAILED:
            self._transition(state, TaskStatus.FAILED)
            return {"state": state, "error": "Capability reported failure; retry or review configuration."}
        self._transition(state, TaskStatus.VALIDATING)
        validation = (
            self.validator.after_execute(result, state, context) if self.validator else {"status": "pass"}
        )
        if validation["status"] == "fail":
            self._transition(state, TaskStatus.FAILED)
            return {"state": state, "error": "Validation failed; review the result and retry."}
        artifact = None
        if result.output and result.output.get("artifact"):
            artifact = Artifact.model_validate(result.output["artifact"])
            if (
                artifact.project_id != project_id
                or artifact.source_task_id != state.active_task_id
                or artifact.artifact_type != selected
            ):
                raise ValueError("Artifact project/task correlation mismatch")
            self.storage.save_artifact(project_id, artifact)
            state.artifact_registry = [
                r
                for r in state.artifact_registry
                if (r.artifact_id, r.version) != (artifact.artifact_id, artifact.artifact_version)
            ]
            state.artifact_registry.append(artifact.reference())
            state.completed_tasks[state.active_task_id] = artifact.reference()
        state.recommended_next_action = f"Review {selected.value}" if artifact else "Review capability result"
        self._transition(state, TaskStatus.AWAITING_APPROVAL if artifact else TaskStatus.COMPLETED)
        if self.memory_service:
            self.memory_service.refresh(state)
        if self.observer:
            self.observer(
                state,
                {
                    "kind": "capability_result",
                    "capability_id": state.active_capability_id,
                    "artifact_id": artifact.artifact_id if artifact else None,
                    "outcome": "success",
                },
            )
        return {"state": state, "artifact": artifact, "validation": validation}
