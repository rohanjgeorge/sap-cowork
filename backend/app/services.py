from io import BytesIO
from pathlib import Path
from threading import RLock

from .models import (
    Artifact,
    ArtifactType,
    ContextItem,
    ContextPackage,
    Project,
    SDLCStage,
    TaskStatus,
    uid,
    now,
)


class ApplicationService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.storage = runtime.storage
        self._locks = {}
        from .mutations import MutationCoordinator

        self.mutations = MutationCoordinator(self.storage, self.open_project)

    def lock(self, project_id):
        return self._locks.setdefault(project_id, RLock())

    def create_project(
        self,
        name,
        stage="Planning",
        requirement="",
        description="",
        model_policy="user_default",
        organization_id=None,
        program_id=None,
        sap_applicability=None,
        request_id=None,
        expected_revision=0,
        import_artifacts=None,
        client_name=None,
        import_artifact_statuses=None,
    ):
        from hashlib import sha256
        import json
        from .state_management import StateError

        self.runtime.settings.current(model_policy)
        order = ["BRD", "FRD", "USER_STORIES", "TDD", "ABAP", "SIT", "UAT", "AUDIT_REPORT"]
        selected = {ArtifactType(k).value for k in (import_artifacts or [])}
        import_artifacts = [k for k in order if k in selected]
        import_artifact_statuses = {
            ArtifactType(k).value: v for k, v in (import_artifact_statuses or {}).items()
        }
        if set(import_artifact_statuses) - selected:
            raise ValueError("Document statuses must refer to selected import artifacts")
        client_name = (client_name.strip() or None) if client_name else None
        rid = request_id or uid()
        payload = {
            "name": name.strip(),
            "stage": str(stage),
            "requirement": requirement,
            "description": description,
            "model_policy": model_policy,
            "organization_id": organization_id,
            "program_id": program_id,
            "sap_applicability": sap_applicability or {},
            **({"import_artifacts": import_artifacts} if import_artifacts else {}),
            **({"client_name": client_name} if client_name else {}),
            **({"import_artifact_statuses": import_artifact_statuses} if import_artifact_statuses else {}),
        }
        signature = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        project = Project(
            project_id=sha256(f"local:create:{rid}".encode()).hexdigest()[:32],
            project_name=name.strip(),
            client_name=client_name,
            description=description,
            model_policy=model_policy,
            organization_id=organization_id,
            program_id=program_id,
            sap_applicability=sap_applicability or {},
            import_artifacts=import_artifacts,
            import_artifact_statuses=import_artifact_statuses,
        )
        if expected_revision != 0:
            raise StateError("REVISION_CONFLICT", "New projects require initial revision 0")
        with self.storage.mutation_lock(project.project_id):
            try:
                existing = self.storage.load_project(project.project_id)
            except FileNotFoundError:
                existing = None
            if existing:
                event = next(
                    (e for e in self.storage.list_events(project.project_id) if e.get("request_id") == rid),
                    None,
                )
                if not event or event.get("signature") != signature:
                    raise StateError(
                        "IDENTITY_CONFLICT", "Creation request ID was reused with different parameters"
                    )
            else:
                state = self.runtime.state.create_project(
                    project, SDLCStage(stage), requirement, request_id=rid, signature=signature
                )
                self.runtime.memory.refresh(state)
            if project.import_artifacts:
                self._announce_onboarding(project.project_id)
        return {**self.open_project(project.project_id), "request_id": rid}

    def list_projects(self):
        result = []
        for p in self.storage.list_projects():
            with self.storage.transaction(p.project_id):
                status = self.runtime.status.get(p.project_id)
                result.append({**p.model_dump(mode="json"), "status": status})
        return result

    def open_project(self, project_id):
        with self.lock(project_id):
            with self.storage.transaction(project_id):
                project = self.storage.load_project(project_id)
                state = self.storage.load_state(project_id)
            if not state.project_name or (state.artifact_registry and not state.artifacts):
                state = self.runtime.state.apply(project_id, "reconcile_artifacts")
            if (
                state.project_status == "active"
                and not self.storage.task_running(project_id)
                and state.task_status
                in (
                    TaskStatus.EXECUTING,
                    TaskStatus.VALIDATING,
                    TaskStatus.PLANNING_CONTEXT,
                    TaskStatus.READY_TO_EXECUTE,
                )
            ):
                state = self.runtime.state.apply(
                    project_id,
                    "task_status",
                    {
                        "status": "failed",
                        "message": "Retry interrupted task using its existing task ID",
                    },
                )
            with self.storage.transaction(project_id):
                state = self.storage.load_state(project_id)
                return {
                    "snapshot_at": now().isoformat(),
                    "project": project,
                    "state": state,
                    "memory": self.storage.load_memory(project_id),
                    "status": self.runtime.status.get(project_id),
                    "session": self.storage.load_session(project_id),
                    "context": self.runtime.context_session.status(project_id),
                    "assets": self.storage.list_project_assets(project_id),
                    "onboarding": self.onboarding(project, state),
                }

    @staticmethod
    def onboarding(project, state):
        if not project.import_artifacts:
            return None
        # Older import plans had one offline approval declaration for all documents.
        statuses = {
            str(k): project.import_artifact_statuses.get(k, "approved") for k in project.import_artifacts
        }
        pending = [
            str(k)
            for k in project.import_artifacts
            if not state.artifacts.get(k)
            or (statuses[str(k)] == "approved" and state.artifacts[k].status != "approved")
        ]
        return {
            "selected_artifacts": [str(k) for k in project.import_artifacts],
            "pending_artifacts": pending,
            "artifact_statuses": statuses,
            "complete": not pending,
            "message": (
                f"Please upload your {statuses[pending[0]]} {pending[0]} document. "
                "We will bring in your selected documents one at a time."
                if pending
                else "All selected documents have been imported with their chosen statuses. Your project is ready to continue."
            ),
        }

    def import_approved_document(
        self, project_id, artifact_type, name, data, *, request_id, expected_revision=None
    ):
        kind = ArtifactType(artifact_type).value
        with self.lock(project_id):
            project = self.storage.load_project(project_id)
            state = self.storage.load_state(project_id)
            queue = self.onboarding(project, state)
            upload_id = request_id + ":upload"
            replay = any(
                a.get("mutation_request_id") == upload_id
                for a in self.storage.list_project_assets(project_id)
            )
            if not queue or kind not in queue["selected_artifacts"]:
                raise ValueError("This artifact was not selected for document import")
            if not replay and (not queue["pending_artifacts"] or queue["pending_artifacts"][0] != kind):
                raise ValueError(
                    "Please upload "
                    + (
                        queue["pending_artifacts"][0]
                        if queue["pending_artifacts"]
                        else "no further documents"
                    )
                )
            uploaded = self.upload(
                project_id,
                name,
                data,
                kind,
                "SDLC",
                True,
                request_id=upload_id,
                expected_revision=expected_revision,
            )
            imported_state = uploaded["workspace"]["state"]
            version = str(imported_state.artifacts[kind].latest_version)
            if queue["artifact_statuses"][kind] == "approved":
                self.chat(
                    project_id,
                    action="approve",
                    artifact_type=kind,
                    version=version,
                    feedback="User selected Approved for this document during project setup.",
                    request_id=request_id + ":approval",
                    expected_revision=self.storage.load_state(project_id).state_revision,
                )
            self._announce_onboarding(project_id)
            return self.open_project(project_id)

    def _announce_onboarding(self, project_id):
        with self.storage.transaction(project_id):
            queue = self.onboarding(
                self.storage.load_project(project_id), self.storage.load_state(project_id)
            )
            if not queue:
                return
            session = self.storage.load_session(project_id)
            if not any(
                m.get("origin") == "onboarding" and m["content"] == queue["message"]
                for m in session["messages"]
            ):
                self.runtime.context_session.append(
                    project_id, "assistant", queue["message"], {"origin": "onboarding"}
                )

    def _message(self, project_id, role, text, metadata=None):
        with self.storage.transaction(project_id):
            self.runtime.context_session.append(project_id, role, text, metadata)

    def chat(self, project_id, **values):
        # Keep the UI/CLI API while normalizing and authorizing through the
        # parent graph before messages, state mutations or worker execution.
        from .orchestration_events import normalize_request

        if callable(getattr(self.runtime.orchestrator, "sync_runtime_projection", None)):
            self.runtime.orchestrator.sync_runtime_projection(project_id)
        evaluated_state = self.storage.load_state(project_id)
        normalized = normalize_request(evaluated_state, values)

        def dispatch(request):
            if not hasattr(self.runtime, "event_graph"):
                return self._chat(project_id, **request)
            return self.runtime.event_graph.dispatch(
                project_id, request, lambda r: self._chat(project_id, **r)
            )

        if normalized["action"] in ("status", "conversation"):
            return dispatch(normalized)
        payload = {
            k: v
            for k, v in normalized.items()
            if k not in {"progress", "request_id", "expected_revision", "task_id"}
            and v not in (None, "", False, [], {})
        }
        if normalized["action"] == "generate":
            payload.pop("message", None)
            payload["model_policy"] = (
                normalized.get("model_policy")
                or self.storage.load_project(project_id).model_policy
                or "user_default"
            )
            if "feedback" in payload:
                payload["feedback"] = payload["feedback"].replace("\r\n", "\n").strip()
        return self.mutations.run(
            project_id,
            "chat:" + normalized["action"],
            payload,
            lambda rid, rev: dispatch({**normalized, "request_id": rid, "expected_revision": rev}),
            request_id=values.get("request_id") or values.get("task_id"),
            expected_revision=values.get("expected_revision")
            if values.get("expected_revision") is not None
            else evaluated_state.state_revision,
        )

    def _chat(
        self,
        project_id,
        message="",
        action=None,
        artifact_type=None,
        task_id=None,
        clarification_id=None,
        version=None,
        feedback="",
        stage=None,
        model_policy=None,
        progress=None,
        new_version=False,
        authors="",
        remarks="",
        expected_revision=None,
        request_id=None,
        evidence_refs=None,
    ):
        with self.lock(project_id):
            self.storage.load_project(project_id)
            initial = self.storage.load_state(project_id)
            if initial.project_status != "active" and action != "reopen_project":
                if action == "status" or message.lower().strip() in ("status", "project status", "/status"):
                    return {
                        "message": "Project is closed. Reopen to make changes.",
                        "workspace": self.open_project(project_id),
                    }
                self.runtime.state.require_active(initial)
            if message:
                self._message(project_id, "user", message)
            state = self.storage.load_state(project_id)
            from .orchestration_events import normalize_request

            normalized = normalize_request(
                state,
                {
                    "message": message,
                    "action": action,
                    "artifact_type": artifact_type,
                    "task_id": task_id,
                    "stage": stage,
                },
            )
            action, artifact_type, task_id, stage = (
                normalized[k] for k in ("action", "artifact_type", "task_id", "stage")
            )
            result = {}
            self.runtime.orchestrator.events.callback = progress
            try:
                if action == "conversation":
                    result = self.runtime.orchestrator.converse(project_id, message, model_policy, task_id)
                elif action == "generate":
                    project = self.storage.load_project(project_id)
                    result = self.runtime.orchestrator.run(
                        project_id,
                        artifact_type,
                        inputs={
                            "instructions": feedback,
                            "new_version": new_version,
                            "authors": authors,
                            "remarks": remarks,
                            "expected_revision": expected_revision,
                            "model_policy": model_policy or project.model_policy,
                        },
                        task_id=task_id or request_id or uid(),
                    )
                elif action == "answer":
                    pending = [c for c in state.open_clarifications if c.status == "open"]
                    current = [c for c in pending if c.task_id == state.active_task_id]
                    pending = current or pending
                    if not pending:
                        raise ValueError("No clarification is awaiting an answer")
                    result = self.runtime.orchestrator.clarifications.answer(
                        self.runtime.orchestrator,
                        project_id,
                        clarification_id or pending[0].clarification_id,
                        message,
                        expected_revision=expected_revision,
                        request_id=request_id or task_id,
                    )
                elif action in ("approve", "reject"):
                    if not artifact_type:
                        raise ValueError("Choose an artifact to review")
                    artifact = self.storage.load_artifact(project_id, artifact_type, version)
                    artifact = self.runtime.approvals.review(
                        project_id,
                        artifact_type,
                        artifact.artifact_version,
                        action == "approve",
                        feedback or (message if action == "reject" else ""),
                        expected_revision=expected_revision,
                        request_id=request_id or task_id,
                    )
                    result = {"artifact": artifact}
                elif action == "submit_requirement":
                    if not message.strip():
                        raise ValueError("Requirement cannot be empty")
                    state = self.runtime.state.apply(
                        project_id,
                        "set_requirement",
                        {"requirement": message},
                        expected_revision=expected_revision,
                        request_id=request_id or task_id,
                    )
                    self.runtime.memory.refresh(state)
                    result = {"message": "Requirement captured. Generate the BRD when ready."}
                elif action == "set_stage":
                    state = self.runtime.state.apply(
                        project_id,
                        "change_draft_stage",
                        {"stage": stage},
                        expected_revision=expected_revision,
                        request_id=request_id or task_id,
                    )
                    self.runtime.memory.refresh(state)
                    guide = getattr(self.runtime.orchestrator, "guide_stage", None)
                    if callable(guide):
                        result = guide(project_id, model_policy, task_id)
                    else:
                        result = self.runtime.orchestrator.converse(
                            project_id,
                            f"Help me work on the {stage} stage using this project's context.",
                            model_policy,
                            task_id,
                        )
                elif action in (
                    "confirm_code",
                    "confirm_testing",
                    "close_project",
                    "reopen_project",
                    "withdraw_development",
                    "withdraw_testing",
                ):
                    operation = "withdraw_confirmation" if action.startswith("withdraw_") else action
                    payload = {
                        "kind": action.removeprefix("withdraw_"),
                        "remarks": remarks,
                        "evidence_refs": evidence_refs or [],
                    }
                    state = self.runtime.state.apply(
                        project_id,
                        operation,
                        payload,
                        expected_revision=expected_revision,
                        request_id=request_id or task_id,
                    )
                    self.runtime.memory.refresh(state)
                    follow_up = None
                    if action == "confirm_testing":
                        follow_up = self._follow_up(project_id, "audit_report")
                    if action == "close_project":
                        self._follow_up(project_id, "learning")
                    result = {
                        "message": f"{action.replace('_', ' ').capitalize()} recorded. Project: {state.project_status}."
                    }
                    if follow_up and follow_up.get("artifact"):
                        result["artifact"] = follow_up["artifact"]
                elif action == "compact":
                    with self.storage.transaction(project_id):
                        result = {
                            "context": self.runtime.context_session.compact(project_id),
                            "message": "Working context compacted. Project state, memory and artifacts preserved.",
                        }
                elif action != "status":
                    raise ValueError("Unknown project action")
            finally:
                self.runtime.orchestrator.events.callback = None
            if result.get("error"):
                reply = result["error"]
            elif result.get("questions"):
                reply = result["questions"][0]
            elif result.get("artifact"):
                a = result["artifact"]
                reply = f"{a.artifact_type} v{a.artifact_version}: {a.approval_status.value}. "
                reply += "Open the document to review, approve or request changes."
            else:
                reply = (
                    result.get("message")
                    or self.storage.load_state(project_id).recommended_next_action
                    or "Ready."
                )
            if self.storage.load_state(project_id).project_status == "active":
                self._message(
                    project_id,
                    "assistant",
                    reply,
                    {
                        "origin": result.get("origin", "workflow"),
                        **({key: result[key] for key in ("provider", "model") if key in result}),
                    },
                )
            return {**result, "message": reply, "workspace": self.open_project(project_id)}

    def state_operation(self, project_id, value, actor="local"):
        return self.mutations.run(
            project_id,
            "state:" + value.operation,
            value.payload,
            lambda rid, rev: self._dispatch_state_operation(
                project_id, value.model_copy(update={"request_id": rid, "expected_revision": rev}), actor
            ),
            request_id=value.request_id,
            expected_revision=value.expected_revision,
            actor=actor,
        )

    def _dispatch_state_operation(self, project_id, value, actor="local"):
        if not hasattr(self.runtime, "event_graph"):
            return self._state_operation(project_id, value, actor)
        action = value.operation
        if action == "withdraw_confirmation":
            action = "withdraw_" + value.payload.get("kind", "")
        values = {**value.payload, "action": action, "request_id": value.request_id}
        if "artifact_id" in value.payload:
            values["artifact_type"] = value.payload["artifact_id"]

        def apply(request):
            payload = dict(value.payload)
            if "version" in request and request["version"] is not None:
                payload["version"] = request["version"]
            return self._state_operation(project_id, value.model_copy(update={"payload": payload}), actor)

        return self.runtime.event_graph.dispatch(project_id, values, apply, actor=actor)

    def _state_operation(self, project_id, value, actor):
        allowed = {
            "change_draft_stage",
            "recalculate_approved_stage",
            "submit_artifact",
            "approve_artifact",
            "return_artifact_to_draft",
            "confirm_code",
            "confirm_testing",
            "withdraw_confirmation",
            "close_project",
            "reopen_project",
            "record_decision",
            "reopen_clarification",
            "resolve_clarification",
            "resolve_flag",
            "reactivate_flag",
            "reconcile_artifacts",
        }
        if value.operation not in allowed:
            raise ValueError("This operation is not exposed to clients")
        if value.operation == "resolve_clarification":
            if not value.payload.get("clarification_id") or not value.payload.get("answer"):
                raise ValueError("Provide clarification_id and answer")
            result = self.runtime.orchestrator.clarifications.answer(
                self.runtime.orchestrator,
                project_id,
                value.payload["clarification_id"],
                value.payload["answer"],
                expected_revision=value.expected_revision,
                request_id=value.request_id,
            )
            return {"state": result["state"], "workspace": self.open_project(project_id)}
        state = self.runtime.state.apply(
            project_id,
            value.operation,
            value.payload,
            actor=actor,
            expected_revision=value.expected_revision,
            request_id=value.request_id,
        )
        self.runtime.memory.refresh(state)
        if value.operation == "approve_artifact":
            self.runtime.orchestrator.resume_approval(
                self.runtime.storage.load_artifact(
                    project_id, value.payload["artifact_id"], value.payload["version"]
                )
            )
        if value.operation in ("confirm_testing", "close_project"):
            kind = "audit_report" if value.operation == "confirm_testing" else "learning"
            if self.runtime.storage.load_state(project_id).follow_ups.get(kind) != "completed":
                self._follow_up(project_id, kind)
        return {"state": state, "workspace": self.open_project(project_id)}

    def _follow_up(self, project_id, kind):
        result = None
        try:
            if kind == "audit_report":
                result = self.runtime.orchestrator.run(project_id, "AUDIT_REPORT")
                if result.get("error") or not result.get("artifact"):
                    raise ValueError("Audit generation needs retry")
            else:
                state = self.storage.load_state(project_id)
                memory = self.runtime.memory.refresh(state)
                with self.storage.transaction(project_id):
                    self.storage.save_upload(
                        project_id,
                        (
                            f"# Closure learning summary\n\nStatus: {state.project_status}\n\n"
                            "Qualification: project evidence only; generated code remains untested until user confirmed.\n\n"
                            + memory.content
                        ).encode(),
                        {"name": "closure_learning.md", "kind": "learning", "scope": "project"},
                    )
            self.runtime.state.apply(
                project_id, "follow_up", {"name": kind, "status": "completed"}, actor="system"
            )
            return result
        except Exception as exc:
            self.runtime.state.apply(
                project_id,
                "follow_up",
                {"name": kind, "status": f"retry_required:{type(exc).__name__}"},
                actor="system",
            )

    def edit_artifact(self, project_id, artifact_id, **values):
        values = dict(values)
        rid = values.pop("request_id", None)
        expected = values.pop("expected_revision", None)
        return self.mutations.run(
            project_id,
            "edit_artifact",
            {"artifact_id": artifact_id, **values},
            lambda request_id, rev: self._edit_artifact(
                project_id, artifact_id, expected_revision=rev, request_id=request_id, **values
            ),
            request_id=rid,
            expected_revision=expected,
        )

    def _edit_artifact(self, project_id, artifact_id, **values):
        def edit(request):
            artifact, state = self.runtime.artifacts.edit(project_id, artifact_id, **values)
            self.runtime.memory.refresh(state)
            return {"artifact": artifact, "workspace": self.open_project(project_id)}

        if not hasattr(self.runtime, "event_graph"):
            return edit({})
        return self.runtime.event_graph.dispatch(
            project_id, {"action": "edit", "artifact_type": artifact_id}, edit
        )

    def upload(
        self,
        project_id,
        name,
        data,
        artifact_type=None,
        domain="BUSINESS",
        confirmed=False,
        *,
        request_id=None,
        expected_revision=None,
    ):
        from hashlib import sha256

        return self.mutations.run(
            project_id,
            "upload",
            {
                "name": name,
                "digest": sha256(data).hexdigest(),
                "artifact_type": artifact_type,
                "domain": domain,
                "confirmed": confirmed,
            },
            lambda rid, rev: self._dispatch_upload(
                project_id,
                name,
                data,
                artifact_type,
                domain,
                confirmed,
                request_id=rid,
                expected_revision=rev,
            ),
            request_id=request_id,
            expected_revision=expected_revision,
        )

    def _dispatch_upload(
        self, project_id, name, data, artifact_type=None, domain="BUSINESS", confirmed=False, **mutation
    ):
        def upload(request):
            return self._upload(project_id, name, data, artifact_type, domain, confirmed, **mutation)

        if not hasattr(self.runtime, "event_graph"):
            return upload({})
        return self.runtime.event_graph.dispatch(
            project_id, {"action": "upload", "artifact_type": artifact_type}, upload
        )

    def _upload(
        self,
        project_id,
        name,
        data,
        artifact_type=None,
        domain="BUSINESS",
        confirmed=False,
        request_id=None,
        expected_revision=None,
    ):
        from .models import ContextDomain
        from .context_handler import DOMAIN_FIELDS
        from .document_conversion import from_docx

        domain = ContextDomain(domain).value
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("Maximum upload size is 10 MB")
        suffix = Path(name).suffix.lower()
        if suffix == ".docx":
            content = from_docx(data)
        elif suffix == ".pdf":
            from pypdf import PdfReader

            content = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(data)).pages)
        elif suffix in (".txt", ".md", ".json", ".abap", ".csv"):
            content = data.decode("utf-8-sig")
        else:
            content = ""
        with self.lock(project_id):
            state = self.storage.load_state(project_id)
            self.runtime.state.require_active(state)
            if expected_revision is not None and state.state_revision != expected_revision:
                from .state_management import StateError

                raise StateError("REVISION_CONFLICT", "Reload before uploading", state.state_revision)
            if artifact_type and not content.strip():
                raise ValueError("This file needs extracted text before it can be registered as an artifact")
            # Preserve original uploads even when adoption awaits confirmation.
            with self.storage.transaction(project_id):
                previous = next(
                    (
                        a
                        for a in self.storage.list_project_assets(project_id)
                        if request_id and a.get("mutation_request_id") == request_id
                    ),
                    None,
                )
                file_id = (
                    previous["file_id"]
                    if previous
                    else self.storage.save_upload(
                        project_id,
                        data,
                        {
                            "name": Path(name).name,
                            "text_extracted": bool(content),
                            "mutation_request_id": request_id,
                        },
                    )
                )
            comparison = None
            if artifact_type:
                kind = ArtifactType(artifact_type)
                try:
                    comparison = self.runtime.artifacts.compare(project_id, kind.value, content)
                except FileNotFoundError:
                    pass
                if comparison and comparison["significant"] and not confirmed:
                    return {
                        "file_id": file_id,
                        "text_extracted": True,
                        "requires_confirmation": True,
                        "comparison": comparison,
                        "workspace": self.open_project(project_id),
                    }
                content = self.runtime.artifacts.align_upload(kind.value, content)
                artifact = Artifact(
                    artifact_id=kind.value,
                    project_id=project_id,
                    artifact_type=kind,
                    content=content,
                    artifact_version="1",
                    template_version=f"{kind.value.lower()}.md",
                    template_ref=f"{kind.value.lower()}.md",
                    sources=[f"upload:{file_id}"],
                )
                _, state = self.runtime.artifacts.persist(
                    artifact, state, {"remarks": "Accepted uploaded source", "request_id": request_id}
                )
            elif content:
                with self.storage.transaction(project_id):
                    self.storage.save_context(
                        project_id,
                        ContextPackage(
                            project_id=project_id,
                            task_id="upload",
                            **{
                                DOMAIN_FIELDS[domain]: [
                                    ContextItem(
                                        content=content, source=f"upload:{file_id}", source_type="upload"
                                    )
                                ]
                            },
                        ),
                    )
                if not state.requirement and domain in ("BUSINESS", "FUNCTIONAL_PROCESS"):
                    state = self.runtime.state.apply(
                        project_id,
                        "set_requirement",
                        {"requirement": content},
                        expected_revision=state.state_revision,
                        request_id=request_id,
                    )
            self.runtime.memory.refresh(state)
        return {
            "file_id": file_id,
            "text_extracted": bool(content),
            "comparison": comparison,
            "workspace": self.open_project(project_id),
        }

    def delete_artifact(self, project_id, artifact_id, version, *, request_id=None, expected_revision=None):
        def commit(rid, rev):
            self.runtime.artifacts.delete(
                project_id, artifact_id, version, expected_revision=rev, request_id=rid
            )
            return self.open_project(project_id)

        return self.mutations.run(
            project_id,
            "delete_artifact",
            {"artifact_id": artifact_id, "version": version},
            commit,
            request_id=request_id,
            expected_revision=expected_revision,
        )

    def update_metadata(self, project_id, values, *, request_id=None, expected_revision=None):
        def commit(rid, rev):
            state = self.runtime.state.apply(
                project_id, "update_metadata", values, expected_revision=rev, request_id=rid
            )
            self.runtime.memory.refresh(state)
            return self.open_project(project_id)

        return self.mutations.run(
            project_id,
            "update_metadata",
            values,
            commit,
            request_id=request_id,
            expected_revision=expected_revision,
        )
