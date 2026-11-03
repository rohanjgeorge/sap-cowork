import json
import os
import queue
import secrets
import threading
import time
from typing import Literal
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, SecretStr

from .local_storage import LocalStorageProvider
from .models import ArtifactType, Contract, SDLCStage
from .runtime import Runtime
from .services import ApplicationService
from .settings import ProviderSettingsInput


class Login(Contract):
    access_code: SecretStr = SecretStr("")


class NewProject(Contract):
    import_artifacts: list[ArtifactType] = Field(default_factory=list)
    import_artifact_statuses: dict[ArtifactType, Literal["draft", "approved"]] = Field(default_factory=dict)
    request_id: str | None = None
    expected_revision: int = Field(default=0, ge=0)
    project_name: str = Field(min_length=1, max_length=150)
    client_name: str | None = Field(default=None, max_length=150)
    stage: SDLCStage = SDLCStage.PLANNING
    requirement: str = ""
    description: str = ""
    model_policy: str = "user_default"
    organization_id: str | None = None
    program_id: str | None = None
    sap_applicability: dict[str, str] = Field(default_factory=dict)


class ChatInput(Contract):
    evidence_refs: list[str] = Field(default_factory=list)
    message: str = ""
    action: str | None = None
    artifact_type: str | None = None
    task_id: str | None = None
    clarification_id: str | None = None
    version: str | None = None
    feedback: str = ""
    stage: str | None = None
    model_policy: str | None = None
    new_version: bool = False
    authors: str = ""
    remarks: str = ""
    expected_revision: int | None = None
    request_id: str | None = None


class StateOperation(Contract):
    operation: str
    payload: dict = Field(default_factory=dict)
    expected_revision: int = Field(ge=0)
    request_id: str = Field(min_length=1, max_length=150)


class ArtifactEdit(Contract):
    content: str = Field(min_length=1)
    new_version: bool = False
    authors: str = ""
    remarks: str = ""
    expected_revision: int = Field(ge=0)
    request_id: str | None = None


class ProjectMetadata(Contract):
    organization_id: str | None = None
    program_id: str | None = None
    sap_applicability: dict[str, str] = Field(default_factory=dict)
    expected_revision: int | None = None
    request_id: str | None = None


class KnowledgeReview(Contract):
    request_id: str | None = None
    expected_revision: int | None = None
    approved: bool
    expected_fingerprint: str | None = None


def create_app(data_dir=None, secret_store=None, access_code=None):
    root = Path(data_dir or os.getenv("COWORK_DATA_DIR", ".cowork"))
    runtime = Runtime(LocalStorageProvider(root), root, secret_store)
    service = ApplicationService(runtime)
    app = FastAPI(title="SAP CoWork", version="0.1.0")
    app.state.service = service
    app.state.runtime = runtime
    sessions = {}
    configured_code = access_code if access_code is not None else os.getenv("COWORK_ACCESS_CODE", "")
    allowed_origins = [
        f"http://{host}:{port}"
        for host in ("localhost", "127.0.0.1")
        for port in {8000, 5173, 4173, int(os.getenv("COWORK_PORT", "8000"))}
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def origin_boundary(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in allowed_origins and request.method not in ("GET", "HEAD", "OPTIONS"):
            return Response("Origin is not allowed", status_code=403)
        return await call_next(request)

    def authenticated(request: Request):
        authorization = request.headers.get("authorization", "")
        token = (
            authorization.removeprefix("Bearer ") if authorization else request.cookies.get("cowork_session")
        )
        if not token or sessions.get(token, 0) < time.time():
            raise HTTPException(401, "Sign in to the local workspace")
        return "local"

    @app.exception_handler(FileNotFoundError)
    async def not_found(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": "Project or asset not found"})

    @app.exception_handler(ValueError)
    async def bad_request(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(OSError)
    async def persistence_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"detail": "Storage operation failed. Project changes were not committed."},
        )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local-single-user"}

    @app.post("/api/session")
    def login(value: Login, response: Response):
        if not secrets.compare_digest(value.access_code.get_secret_value(), configured_code):
            raise HTTPException(401, "Invalid access code")
        token = secrets.token_urlsafe(32)
        sessions[token] = time.time() + 28800
        response.set_cookie("cowork_session", token, httponly=True, samesite="strict", max_age=28800)
        return {"user_id": "local", "token": token, "mode": "local-single-user"}

    @app.get("/api/session", dependencies=[Depends(authenticated)])
    def session():
        return {"user_id": "local", "mode": "local-single-user"}

    @app.delete("/api/session")
    def logout(request: Request, response: Response):
        token = request.cookies.get("cowork_session") or request.headers.get(
            "authorization", ""
        ).removeprefix("Bearer ")
        sessions.pop(token, None)
        response.delete_cookie("cowork_session")
        return {"signed_out": True}

    protected = [Depends(authenticated)]

    from .state_management import StateError

    @app.exception_handler(StateError)
    async def state_error(request, exc):
        from fastapi.responses import JSONResponse

        code = (
            409
            if exc.code
            in ("REVISION_CONFLICT", "PROJECT_CLOSED", "INVALID_TRANSITION", "IDENTITY_CONFLICT", "BLOCKED")
            else 403
            if exc.code == "UNAUTHORIZED"
            else 400
        )
        return JSONResponse(
            status_code=code,
            content={
                "detail": str(exc),
                "code": exc.code,
                "state_revision": exc.revision,
                "reasons": exc.details,
            },
        )

    @app.post("/api/stage-suggestion", dependencies=protected)
    def suggest_stage(artifact_types: list[str]):
        from .models import ArtifactType
        from .router import ARTIFACT_STAGE, next_stage

        stages = [ARTIFACT_STAGE[ArtifactType(kind)] for kind in artifact_types]
        last = max(stages, key=lambda s: list(SDLCStage).index(s)) if stages else None
        suggested = (next_stage(last) or last) if last else SDLCStage.PLANNING
        return {"suggested_stage": suggested, "requires_confirmation": True}

    @app.get("/api/projects", dependencies=protected)
    def projects():
        return service.list_projects()

    @app.get("/api/capabilities", dependencies=protected)
    def capability_catalog():
        return runtime.registry.describe()

    @app.post("/api/projects", dependencies=protected)
    def create_project(value: NewProject):
        return service.create_project(
            value.project_name,
            value.stage,
            value.requirement,
            value.description,
            value.model_policy,
            value.organization_id,
            value.program_id,
            value.sap_applicability,
            value.request_id,
            value.expected_revision,
            import_artifacts=value.import_artifacts,
            client_name=value.client_name,
            import_artifact_statuses=value.import_artifact_statuses,
        )

    @app.get("/api/projects/{project_id}", dependencies=protected)
    def project(project_id: str):
        return service.open_project(project_id)

    @app.put("/api/projects/{project_id}/metadata", dependencies=protected)
    def update_project_metadata(project_id: str, value: ProjectMetadata):
        return service.update_metadata(
            project_id,
            value.model_dump(exclude={"request_id", "expected_revision"}, exclude_unset=True),
            request_id=value.request_id,
            expected_revision=value.expected_revision,
        )

    @app.post("/api/projects/{project_id}/chat", dependencies=protected)
    def chat(project_id: str, value: ChatInput):
        return service.chat(project_id, **value.model_dump())

    @app.post("/api/projects/{project_id}/chat/stream", dependencies=protected)
    def stream(project_id: str, value: ChatInput):
        runtime.storage.load_project(project_id)

        def events():
            messages = queue.Queue()

            def execute():
                try:
                    result = service.chat(project_id, **value.model_dump(), progress=messages.put)
                    messages.put({"type": "result", "data": jsonable_encoder(result)})
                except Exception as exc:
                    from .state_management import StateError

                    messages.put(
                        {
                            "type": "error",
                            "code": exc.code if isinstance(exc, StateError) else "EXECUTION_ERROR",
                            "reasons": exc.details if isinstance(exc, StateError) else [],
                            "message": str(exc)
                            if isinstance(exc, StateError)
                            else f"Operation failed ({type(exc).__name__}); retry the request.",
                        }
                    )
                finally:
                    messages.put(None)

            threading.Thread(target=execute, daemon=True).start()
            while True:
                try:
                    item = messages.get(timeout=10)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                yield "data: " + json.dumps(item) + "\n\n"

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/api/projects/{project_id}/state", dependencies=protected)
    def state(project_id: str):
        return service.open_project(project_id)["state"]

    @app.get("/api/projects/{project_id}/status", dependencies=protected)
    def status(project_id: str):
        return service.open_project(project_id)["status"]

    @app.post("/api/projects/{project_id}/state/operations")
    def state_operation(project_id: str, value: StateOperation, actor: str = Depends(authenticated)):
        return service.state_operation(project_id, value, actor)

    @app.get("/api/projects/{project_id}/artifacts", dependencies=protected)
    def artifacts(project_id: str):
        return service.open_project(project_id)["state"].artifact_registry

    @app.get("/api/projects/{project_id}/artifacts/{artifact_id}", dependencies=protected)
    def artifact(project_id: str, artifact_id: str, version: str | None = None):
        with runtime.storage.transaction(project_id):
            runtime.storage.load_project(project_id)
            return runtime.storage.load_artifact(project_id, artifact_id, version)

    @app.post("/api/projects/{project_id}/artifacts/{artifact_id}/review", dependencies=protected)
    def review(project_id: str, artifact_id: str, value: ChatInput):
        if value.action not in ("approve", "reject"):
            raise ValueError("Review action must be approve or reject")
        return service.chat(project_id, **{**value.model_dump(), "artifact_type": artifact_id})

    @app.get("/api/projects/{project_id}/artifacts/{artifact_id}/download", dependencies=protected)
    def download_artifact(project_id: str, artifact_id: str, version: str | None = None):
        artifact = runtime.storage.load_artifact(project_id, artifact_id, version)
        extension = "abap" if artifact.artifact_type == "ABAP" else "docx"
        return Response(
            runtime.storage.load_artifact_document(project_id, artifact_id, version),
            media_type="text/plain"
            if extension == "abap"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.artifact_id}_v{artifact.artifact_version}.{extension}"'
            },
        )

    @app.put("/api/projects/{project_id}/artifacts/{artifact_id}", dependencies=protected)
    def edit_artifact(project_id: str, artifact_id: str, value: ArtifactEdit):
        return service.edit_artifact(project_id, artifact_id, **value.model_dump())

    @app.delete("/api/projects/{project_id}/artifacts/{artifact_id}", dependencies=protected)
    def delete_artifact(
        project_id: str,
        artifact_id: str,
        version: str,
        request_id: str | None = None,
        expected_revision: int | None = None,
    ):
        return service.delete_artifact(
            project_id, artifact_id, version, request_id=request_id, expected_revision=expected_revision
        )

    @app.get("/api/projects/{project_id}/files", dependencies=protected)
    def files(project_id: str):
        return service.open_project(project_id)["assets"]

    @app.post("/api/projects/{project_id}/follow-ups/{kind}/retry", dependencies=protected)
    def retry_follow_up(
        project_id: str, kind: str, request_id: str | None = None, expected_revision: int | None = None
    ):
        def commit(rid, revision):
            if kind not in ("audit_report", "learning"):
                raise ValueError("Unknown follow-up")
            state = runtime.storage.load_state(project_id)
            if kind not in state.follow_ups:
                raise ValueError("No pending follow-up")
            if state.follow_ups[kind] != "completed":
                service._follow_up(project_id, kind)
            return service.open_project(project_id)

        return service.mutations.run(
            project_id,
            "retry_follow_up",
            {"kind": kind},
            commit,
            request_id=request_id,
            expected_revision=expected_revision,
        )

    @app.post("/api/projects/{project_id}/files", dependencies=protected)
    async def upload(
        project_id: str,
        file: UploadFile = File(...),
        artifact_type: str | None = Form(None),
        domain: str = Form("BUSINESS"),
        confirmed: bool = Form(False),
        request_id: str | None = Form(None),
        expected_revision: int | None = Form(None),
    ):
        data = await file.read(10 * 1024 * 1024 + 1)
        return service.upload(
            project_id,
            file.filename or "upload",
            data,
            artifact_type,
            domain,
            confirmed,
            request_id=request_id,
            expected_revision=expected_revision,
        )

    @app.post("/api/projects/{project_id}/onboarding/upload", dependencies=protected)
    async def import_approved_document(
        project_id: str,
        file: UploadFile = File(...),
        artifact_type: ArtifactType = Form(...),
        request_id: str = Form(...),
        expected_revision: int | None = Form(None),
    ):
        return service.import_approved_document(
            project_id,
            artifact_type,
            file.filename or "upload",
            await file.read(10 * 1024 * 1024 + 1),
            request_id=request_id,
            expected_revision=expected_revision,
        )

    @app.get("/api/projects/{project_id}/files/{file_id}", dependencies=protected)
    def download(project_id: str, file_id: str):
        with runtime.storage.transaction(project_id):
            runtime.storage.load_project(project_id)
            return Response(
                runtime.storage.load_upload(project_id, file_id), media_type="application/octet-stream"
            )

    @app.get("/api/projects/{project_id}/context", dependencies=protected)
    def context_status(project_id: str):
        return service.open_project(project_id)["context"]

    @app.post("/api/projects/{project_id}/context/compact", dependencies=protected)
    def compact(project_id: str):
        return service.chat(project_id, action="compact")

    @app.get("/api/projects/{project_id}/context/sources", dependencies=protected)
    def context_sources(project_id: str):
        return runtime.context_sources.catalog(runtime.storage.load_project(project_id))

    @app.get("/api/projects/{project_id}/context/plans", dependencies=protected)
    def context_plans(project_id: str):
        runtime.storage.load_project(project_id)
        return [
            {
                key: r["plan"].get(key)
                for key in (
                    "plan_id",
                    "task_id",
                    "artifact_type",
                    "profile_version",
                    "outcome",
                    "package_ref",
                    "cycle",
                )
            }
            for r in runtime.storage.list_context_runs(project_id)
            if r.get("kind") == "context_plan"
        ]

    @app.get("/api/projects/{project_id}/context/plans/{plan_ref}", dependencies=protected)
    def context_plan(project_id: str, plan_ref: str):
        from .models import ContextPackage
        from .context_domains import DOMAIN_FIELDS
        from .context_sources import permitted

        project = runtime.storage.load_project(project_id)
        record = runtime.storage.load_context_run(project_id, plan_ref)
        if record.get("kind") != "context_plan":
            raise FileNotFoundError("Context plan not found")
        package = ContextPackage.model_validate(record["package"]) if record.get("package") else None
        if package:
            for field in DOMAIN_FIELDS.values():
                setattr(
                    package,
                    field,
                    [
                        i
                        for i in getattr(package, field)
                        if permitted(i, project) and runtime.context_planning._still_authorized(i, project)
                    ],
                )
        return {
            "plan": record["plan"],
            "gap_report": record["plan"]["gaps"],
            "package": package,
            "retrieval_trace": record.get("retrieval_trace", []),
        }

    @app.get("/api/projects/{project_id}/context/updates", dependencies=protected)
    def context_updates(project_id: str):
        from .context_sources import permitted
        from .models import ContextItem

        project = runtime.storage.load_project(project_id)
        return [
            {
                "record_id": r["record_id"],
                "domain": r["domain"],
                "source": r["incoming"]["source"],
                "source_version": r["incoming"].get("source_version"),
                "decision": r["decision"],
            }
            for r in runtime.storage.list_context_runs(project_id)
            if r.get("kind") == "knowledge_update"
            and r.get("decision") == "review_required"
            and not r.get("review_outcome")
            and permitted(ContextItem.model_validate(r["incoming"]), project)
        ]

    @app.post("/api/projects/{project_id}/context/updates/{record_id}/review")
    def review_context_update(
        project_id: str, record_id: str, value: KnowledgeReview, actor: str = Depends(authenticated)
    ):
        def commit(rid, revision):
            runtime.state.require_active(runtime.storage.load_state(project_id))
            if value.approved and not value.expected_fingerprint:
                raise HTTPException(409, "Compare source changes before accepting the update")
            try:
                record = runtime.context_planning.copies.review(
                    project_id,
                    record_id,
                    value.approved,
                    actor=actor,
                    expected_fingerprint=value.expected_fingerprint,
                )
                return {
                    key: record.get(key)
                    for key in ("record_id", "review_outcome", "reviewed_by", "reviewed_at")
                }
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc

        return service.mutations.run(
            project_id,
            "review_context_update",
            {
                "record_id": record_id,
                "approved": value.approved,
                "expected_fingerprint": value.expected_fingerprint,
            },
            commit,
            request_id=value.request_id,
            expected_revision=value.expected_revision,
            actor=actor,
        )

    @app.get("/api/projects/{project_id}/context/updates/{record_id}", dependencies=protected)
    def compare_context_update(project_id: str, record_id: str):
        from hashlib import sha256
        from .context_sources import identity, permitted
        from .models import ContextItem
        from difflib import unified_diff

        project = runtime.storage.load_project(project_id)
        record = runtime.storage.load_context_run(project_id, record_id)
        if record.get("kind") != "knowledge_update":
            raise FileNotFoundError("Knowledge update not found")
        incoming = ContextItem.model_validate(record["incoming"])
        current = next(
            (
                i
                for i in runtime.storage.load_context(project_id, record["domain"])
                if identity(i) == identity(incoming)
            ),
            None,
        )
        if not permitted(incoming, project) or current is not None and not permitted(current, project):
            raise HTTPException(403, "Source access was revoked")
        previous = ContextItem.model_validate(record["previous"]) if record.get("previous") else None
        comparison = current or previous
        before = (
            comparison.content
            if comparison and permitted(comparison, project)
            else "Previous source content not available under current permissions"
        )
        return {
            "record_id": record_id,
            "previous": before,
            "incoming": incoming.content,
            "current_fingerprint": sha256(current.model_dump_json().encode()).hexdigest()
            if current
            else "absent",
            "diff": "\n".join(
                unified_diff(
                    before.splitlines(),
                    incoming.content.splitlines(),
                    fromfile="project copy",
                    tofile="proposed source",
                )
            )
            or "No textual changes; review source metadata.",
            "metadata": incoming.model_dump(mode="json", exclude={"content"}),
        }

    @app.get("/api/settings", dependencies=protected)
    def settings():
        return runtime.settings.load()

    @app.put("/api/settings/provider", dependencies=protected)
    def provider(value: ProviderSettingsInput):
        return runtime.settings.configure(value)

    @app.post("/api/settings/provider/test", dependencies=protected)
    def connection_test():
        from .models import ModelRequest
        from .model_gateway import ModelAccessError

        settings = runtime.settings.load()
        configuration = settings.providers[settings.default_provider]
        try:
            runtime.gateway.complete(
                ModelRequest(
                    task_id="connection-test",
                    messages=[{"role": "user", "content": "Reply OK"}],
                    generation_settings={"max_tokens": 16},
                )
            )
            configuration.connection_status = "connected"
        except (ModelAccessError, ValueError):
            configuration.connection_status = "failed"
        runtime.settings.save(settings)
        return {"status": configuration.connection_status, "provider": configuration.provider}

    static = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="ui")
    return app
