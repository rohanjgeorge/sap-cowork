"""Single writer for V1.1 workflow state. Storage remains provider-neutral."""

from hashlib import sha256
import json

from .models import (
    ArtifactRegistryEntry,
    ArtifactType,
    Clarification,
    CompletionRecord,
    Decision,
    Flag,
    ProjectMemory,
    ProjectState,
    SDLCStage,
    TaskStatus,
    now,
)
from .router import ARTIFACT_STAGE, STAGE_ARTIFACT, dependency_issues


class StateError(ValueError):
    def __init__(self, code, message, revision=None, details=None):
        self.code, self.revision = code, revision
        self.details = details or []
        super().__init__(f"{code}: {message}")


STAGE_REQUIREMENTS = {
    SDLCStage.PLANNING: ["BRD"],
    SDLCStage.ANALYSIS: ["FRD", "USER_STORIES"],
    SDLCStage.DESIGN: ["TDD"],
    SDLCStage.DEVELOPMENT: ["ABAP"],
    SDLCStage.TESTING: ["SIT", "UAT"],
}
DOCUMENTS_REQUIRED = ("BRD", "FRD", "USER_STORIES", "TDD", "SIT", "UAT")


def accepted(state, kind):
    """Evidence must refer to current active versions, not stale code/test baselines."""
    if kind == "testing" and any(
        not state.artifacts.get(k) or state.artifacts[k].status != "approved" for k in ("SIT", "UAT")
    ):
        return False
    for record in reversed(state.confirmations):
        if record.kind != kind or not record.active:
            continue
        if all(
            state.artifacts.get(ref.artifact_type)
            and str(state.artifacts[ref.artifact_type].latest_version) == ref.version
            and (
                not record.artifact_hashes
                or record.artifact_hashes.get(ref.artifact_id)
                == state.artifacts[ref.artifact_type].content_hash
            )
            for ref in record.artifacts
        ):
            return True
    return False


def stage_complete(state, stage):
    if stage == SDLCStage.DEVELOPMENT:
        return accepted(state, "development")
    if stage == SDLCStage.TESTING:
        return accepted(state, "testing")
    # A new draft never revokes the approval of an older version.
    return all(
        state.artifacts.get(k) and state.artifacts[k].latest_approved_version
        for k in STAGE_REQUIREMENTS[stage]
    )


def recalculate(state):
    approved = SDLCStage.PLANNING
    for index, stage in enumerate(SDLCStage):
        if not stage_complete(state, stage):
            break
        approved = list(SDLCStage)[min(index + 1, len(SDLCStage) - 1)]
    state.current_approved_stage = approved
    state.recommended_stage = approved if approved != state.current_draft_stage else None
    missing = [
        k
        for k in STAGE_REQUIREMENTS[approved]
        if not state.artifacts.get(k) or not state.artifacts[k].latest_approved_version
    ]
    if approved == SDLCStage.DEVELOPMENT:
        state.expected_next_artifact = "ABAP"
        state.recommended_next_action = (
            "Confirm generated code is satisfactory" if state.artifacts.get("ABAP") else "Generate ABAP"
        )
    elif approved == SDLCStage.TESTING:
        state.expected_next_artifact = missing[0] if missing else "UAT"
        state.recommended_next_action = f"Generate {missing[0]}" if missing else "Confirm testing results"
    else:
        state.expected_next_artifact = missing[0] if missing else STAGE_ARTIFACT[approved].value
        state.recommended_next_action = f"Generate {state.expected_next_artifact}"


class StateManagementService:
    def __init__(self, storage):
        self.storage = storage

    def require_active(self, state):
        if state.project_status != "active":
            raise StateError(
                "PROJECT_CLOSED", "Reopen the project before making changes", state.state_revision
            )

    def get_state(self, project_id):
        return self.storage.load_state(project_id)

    def request(self, state, operation, payload=None, actor="orchestrator"):
        """Internal request using the revision of a previously loaded state."""
        saved = self.apply(
            state.project_id, operation, payload, actor=actor, expected_revision=state.state_revision
        )
        state.__dict__.update(saved.__dict__)
        return state

    def create_project(self, project, stage="Planning", requirement="", *, request_id=None, signature=None):
        with self.storage.transaction(project.project_id):
            self.storage.create_project(project)
            state = ProjectState(
                project_id=project.project_id,
                project_name=project.project_name,
                program_id=project.program_id,
                current_draft_stage=stage,
                requirement=requirement,
                started_stages=[SDLCStage(stage)],
                state_revision=1,
            )
            state.expected_next_artifact = STAGE_ARTIFACT[SDLCStage(stage)].value
            state.recommended_next_action = f"Generate {state.expected_next_artifact}"
            self.storage.save_state(project.project_id, state)
            self.storage.save_memory(project.project_id, ProjectMemory(project_id=project.project_id))
            self._event(state, "create_project", "local", request_id=request_id, signature=signature)
        return state

    def _event(self, state, operation, actor, request_id=None, signature=None):
        self.storage.append_event(
            state.project_id,
            {
                "kind": "state_changed",
                "operation": operation,
                "actor": actor,
                "time": now().isoformat(),
                "state_revision": state.state_revision,
                "request_id": request_id,
                "expected_revision": state.state_revision - 1 if request_id else None,
                "signature": signature,
                **({"outcome": state.model_dump(mode="json")} if request_id else {}),
            },
        )

    def apply(
        self, project_id, operation, payload=None, *, actor="local", expected_revision=None, request_id=None
    ):
        try:
            return self._apply(
                project_id,
                operation,
                payload,
                actor=actor,
                expected_revision=expected_revision,
                request_id=request_id,
            )
        except StateError as error:
            if error.code == "UNAUTHORIZED":
                with self.storage.transaction(project_id):
                    self.storage.append_event(
                        project_id,
                        {
                            "kind": "state_rejected",
                            "operation": operation,
                            "actor": actor,
                            "time": now().isoformat(),
                            "code": error.code,
                        },
                    )
            raise

    def _apply(
        self, project_id, operation, payload=None, *, actor="local", expected_revision=None, request_id=None
    ):
        """Trusted callers supply actor; API never accepts actor from a request body."""
        payload = payload or {}
        signature = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        with self.storage.transaction(project_id):
            state = self.storage.load_state(project_id)
            if request_id:
                prior = next(
                    (e for e in self.storage.list_events(project_id) if e.get("request_id") == request_id),
                    None,
                )
                if prior:
                    if (
                        prior["operation"] != operation
                        or prior.get("actor") != actor
                        or prior.get("signature") != signature
                    ):
                        raise StateError(
                            "INVALID_TRANSITION", "Request ID already used for another operation"
                        )
                    return ProjectState.model_validate(prior["outcome"])
            if expected_revision is not None and state.state_revision != expected_revision:
                raise StateError("REVISION_CONFLICT", "Reload the latest state", state.state_revision)
            if operation not in ("reopen_project", "follow_up"):
                self.require_active(state)
            if (
                operation
                in {
                    "approve_artifact",
                    "confirm_code",
                    "confirm_testing",
                    "withdraw_confirmation",
                    "close_project",
                    "reopen_project",
                    "submit_artifact",
                    "return_artifact_to_draft",
                }
                and actor != "local"
            ):
                raise StateError("UNAUTHORIZED", "Only the authenticated user can perform this operation")
            if operation == "follow_up" and actor != "system":
                raise StateError("UNAUTHORIZED", "Follow-up bookkeeping is internal")
            try:
                from .eligibility import ensure_eligible

                ensure_eligible(state, operation)
                self._operate(state, operation, payload, actor)
            except StateError:
                raise
            except FileNotFoundError as exc:
                raise StateError("ARTIFACT_NOT_FOUND", "Artifact/version not found") from exc
            except (KeyError, ValueError, TypeError) as exc:
                raise StateError("VALIDATION_ERROR", "Invalid or missing operation parameters") from exc
            self._refresh_flags(state)
            state.state_revision += 1
            state.updated_at = now()
            state.schema_version = "1.1"
            if not state.project_name:
                state.project_name = self.storage.load_project(project_id).project_name
            state = ProjectState.model_validate(state.model_dump())
            self.storage.save_state(project_id, state)
            self._event(state, operation, actor, request_id, signature)
            return state

    def _refresh_flags(self, state):
        conditions = {}
        for stage in state.started_stages:
            for kind in STAGE_REQUIREMENTS[stage]:
                for issue in dependency_issues(state, kind):
                    conditions[f"{kind}:{issue.code}"] = (kind, issue)
        for flag in state.flags:
            if (
                flag.code
                and flag.type != "blocker"
                and not flag.code.startswith("CONTEXT:")
                and flag.code not in conditions
                and flag.status == "active"
            ):
                flag.status, flag.resolved_at = "resolved", now()
        for code, (kind, issue) in conditions.items():
            existing = next((f for f in state.flags if f.code == code), None)
            if existing:
                existing.status, existing.resolved_at = "active", None
            else:
                state.flags.append(Flag(description=issue.message, related_artifact=kind, code=code))

    def _registry(self, state):
        refs = self.storage.list_artifacts(state.project_id)
        state.artifact_registry = refs
        entries = {}
        for kind in ArtifactType:
            versions = [
                self.storage.load_artifact(state.project_id, r.artifact_id, r.version)
                for r in refs
                if r.artifact_type == kind
            ]
            if not versions:
                continue
            latest = max(versions, key=lambda a: int(a.artifact_version))
            approved = max(
                (a for a in versions if a.approval_status == "approved"),
                key=lambda a: int(a.artifact_version),
                default=None,
            )

            def ref(a):
                return f"artifact:{a.artifact_id}:v{a.artifact_version}"

            entries[kind.value] = ArtifactRegistryEntry(
                artifact_id=latest.artifact_id,
                artifact_type=kind,
                status=latest.approval_status.value,
                latest_version=latest.artifact_version,
                latest_approved_version=approved.artifact_version if approved else None,
                storage_ref=ref(latest),
                latest_approved_storage_ref=ref(approved) if approved else None,
                template_version=latest.template_ref or latest.template_version,
                created_at=min(a.created_date for a in versions),
                updated_at=latest.last_edited_date,
                approved_by=approved.approved_by if approved else None,
                approved_at=approved.approved_at if approved else None,
                content_hash=sha256(latest.content.encode()).hexdigest(),
            )
        state.artifacts = entries
        valid = {(r.artifact_id, r.version) for r in refs}
        state.completed_tasks = {
            task: ref
            for task, ref in state.completed_tasks.items()
            if (ref.artifact_id, ref.version) in valid
        }
        for ref in refs:
            artifact = self.storage.load_artifact(state.project_id, ref.artifact_id, ref.version)
            if artifact.source_task_id:
                state.completed_tasks[artifact.source_task_id] = ref

    def _operate(self, state, operation, p, actor):
        if operation == "update_metadata":
            project = self.storage.load_project(state.project_id)
            for key in ("organization_id", "program_id", "sap_applicability"):
                if key in p:
                    setattr(project, key, p[key])
            project.updated_at = now()
            state.program_id = project.program_id
            self.storage.save_project(project)
        elif operation == "change_draft_stage":
            state.current_draft_stage = SDLCStage(p["stage"])
            if state.current_stage not in state.started_stages:
                state.started_stages.append(state.current_stage)
            state.expected_next_artifact = STAGE_ARTIFACT[state.current_stage].value
            state.recommended_next_action = f"Generate {state.expected_next_artifact}"
        elif operation == "set_requirement":
            if not p["requirement"].strip():
                raise StateError("VALIDATION_ERROR", "Requirement cannot be empty")
            state.requirement = p["requirement"]
        elif operation == "sync_task_projection":
            state.active_task_id = p["task_id"]
            state.active_capability_id = p["capability_id"]
            state.current_task = f"Generate {p['artifact_type']}"
            state.task_inputs = p["inputs"]
            state.task_status = TaskStatus(p["status"])
            state.expected_next_artifact = p["artifact_type"]
        elif operation == "begin_task":
            kind = ArtifactType(p["artifact_type"])
            state.active_task_id, state.active_capability_id = p["task_id"], p["capability_id"]
            state.current_task = f"Generate {kind.value}"
            state.task_inputs = p.get("inputs") or {}
            self._operate(state, "change_draft_stage", {"stage": ARTIFACT_STAGE[kind]}, actor)
            state.expected_next_artifact = kind.value
            state.recommended_stage = None
            state.issues = [i for i in state.issues if i.stage != state.current_stage]
            state.issues.extend(dependency_issues(state, kind))
        elif operation == "task_status":
            state.task_status = TaskStatus(p["status"])
            if p.get("message"):
                state.recommended_next_action = p["message"]
        elif operation in ("register_artifact", "reconcile_artifacts"):
            self._registry(state)
            if operation == "register_artifact":
                artifact = self.storage.load_artifact(state.project_id, p["artifact_id"], p["version"])
                if artifact.source_task_id:
                    state.completed_tasks[artifact.source_task_id] = artifact.reference()
                stage = ARTIFACT_STAGE[artifact.artifact_type]
                if stage not in state.started_stages:
                    state.started_stages.append(stage)
            recalculate(state)
        elif operation in ("approve_artifact", "submit_artifact", "return_artifact_to_draft"):
            previous_expected = state.expected_next_artifact
            waiting = state.task_status == TaskStatus.AWAITING_INPUT
            active_kind = state.current_task.removeprefix("Generate ") if state.current_task else None
            artifact = self.storage.load_artifact(state.project_id, p["artifact_id"], p["version"])
            if operation == "approve_artifact":
                artifact.approval_status = "approved"
                artifact.approved_by = p.get("approved_by") or actor
                artifact.approval_declared_by = actor
                artifact.approved_at = p.get("approved_at") or now()
            else:
                if artifact.approval_status == "approved":
                    raise StateError(
                        "INVALID_TRANSITION", "An approved version cannot be changed; create a draft"
                    )
                artifact.approval_status = "pending_approval" if operation == "submit_artifact" else "draft"
                artifact.feedback = p.get("feedback") or None
            self.storage.save_artifact(state.project_id, artifact)
            self._registry(state)
            recalculate(state)
            if waiting:
                state.expected_next_artifact = previous_expected
            elif active_kind is None or (
                active_kind == artifact.artifact_type
                and str(state.artifacts[artifact.artifact_type].latest_version) == artifact.artifact_version
            ):
                state.current_task = None
                state.task_status = TaskStatus.IDLE
        elif operation == "recalculate_approved_stage":
            self._registry(state)
            recalculate(state)
        elif operation == "add_clarification":
            from .models import ProjectIssue

            state.issues = [i for i in state.issues if i.code != "MATERIAL_INPUT_REQUIRED"]
            state.issues.append(
                ProjectIssue(
                    code="MATERIAL_INPUT_REQUIRED",
                    message="Answer the open clarification to resume this task.",
                    severity="error",
                    blocking=True,
                    stage=state.current_stage,
                )
            )
            for question in p["questions"]:
                if not any(c.question == question and c.status == "open" for c in state.clarifications):
                    state.clarifications.append(
                        Clarification(
                            question=question,
                            task_id=state.active_task_id,
                            source=p.get("source", "orchestrator"),
                            related_artifact=state.expected_next_artifact,
                        )
                    )
            state.task_status = TaskStatus.AWAITING_INPUT
        elif operation in ("resolve_clarification", "reopen_clarification"):
            question = next(
                (c for c in state.clarifications if c.clarification_id == p["clarification_id"]), None
            )
            if not question:
                raise StateError("VALIDATION_ERROR", "Clarification not found")
            if operation == "resolve_clarification":
                if question.status != "open" or not p.get("answer", "").strip():
                    raise StateError("INVALID_TRANSITION", "An open question and answer are required")
                question.response, question.status, question.resolved_at = p["answer"], "resolved", now()
                if "provide the requirement" in question.question.lower():
                    state.requirement = p["answer"]
                if not any(
                    c.status == "open" and c.task_id == state.active_task_id for c in state.clarifications
                ):
                    state.issues = [i for i in state.issues if i.code != "MATERIAL_INPUT_REQUIRED"]
            else:
                question.status, question.resolved_at = "open", None
        elif operation == "record_decision":
            state.decisions.append(
                Decision(
                    description=p["description"],
                    decided_by=actor,
                    related_artifact=p.get("related_artifact"),
                    related_stage=p.get("related_stage"),
                )
            )
        elif operation == "add_flag":
            incoming = Flag.model_validate(p)
            existing = next((f for f in state.flags if f.flag_id == incoming.flag_id), None)
            if existing:
                existing.status, existing.resolved_at = "active", None
                existing.description = incoming.description
            else:
                state.flags.append(incoming)
        elif operation in ("resolve_flag", "reactivate_flag"):
            flag = next((f for f in state.flags if f.flag_id == p["flag_id"]), None)
            if not flag:
                raise StateError("VALIDATION_ERROR", "Flag not found")
            flag.status = "resolved" if operation == "resolve_flag" else "active"
            flag.resolved_at = now() if flag.status == "resolved" else None
        elif operation in ("confirm_code", "confirm_testing"):
            kind = "development" if operation == "confirm_code" else "testing"
            required = ["ABAP"] if kind == "development" else ["SIT", "UAT", "ABAP"]
            self._registry(state)
            if kind == "testing" and any(
                not state.artifacts.get(k) or state.artifacts[k].status != "approved" for k in ("SIT", "UAT")
            ):
                raise StateError(
                    "INVALID_TRANSITION", "Approve the current SIT and UAT versions before confirming testing"
                )
            refs = []
            for artifact_type in required:
                entry = state.artifacts.get(artifact_type)
                if not entry:
                    raise StateError("ARTIFACT_NOT_FOUND", f"No {artifact_type} baseline to confirm")
                refs.append(
                    self.storage.load_artifact(
                        state.project_id, entry.artifact_id, entry.latest_version
                    ).reference()
                )
            for record in state.confirmations:
                if record.kind == kind and record.active:
                    record.active, record.withdrawn_at = False, now()
            state.confirmations.append(
                CompletionRecord(
                    kind=kind,
                    artifacts=refs,
                    actor=actor,
                    remarks=p.get("remarks", ""),
                    evidence_refs=p.get("evidence_refs", []),
                    artifact_hashes={
                        ref.artifact_id: state.artifacts[ref.artifact_type].content_hash for ref in refs
                    },
                )
            )
            if kind == "testing":
                state.follow_ups["audit_report"] = "pending"
            recalculate(state)
        elif operation == "withdraw_confirmation":
            if p["kind"] not in ("development", "testing"):
                raise StateError("VALIDATION_ERROR", "Unknown confirmation kind")
            for record in state.confirmations:
                if record.kind == p["kind"] and record.active:
                    record.active, record.withdrawn_at = False, now()
            recalculate(state)
        elif operation == "close_project":
            self._registry(state)
            complete = all(
                state.artifacts.get(k) and state.artifacts[k].status == "approved" for k in DOCUMENTS_REQUIRED
            )
            state.project_status = (
                "completed"
                if complete and accepted(state, "development") and accepted(state, "testing")
                else "incomplete"
            )
            state.follow_ups["learning"] = "pending"
        elif operation == "reopen_project":
            state.project_status = "active"
        elif operation == "follow_up":
            state.follow_ups[p["name"]] = p["status"]
        else:
            raise StateError("INVALID_TRANSITION", "Unknown state operation")
