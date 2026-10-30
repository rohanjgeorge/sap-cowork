import json
import os
import queue
import secrets
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, SecretStr

from .local_storage import LocalStorageProvider
from .models import Contract, SDLCStage
from .runtime import Runtime
from .services import ApplicationService
from .settings import ProviderSettingsInput


class Login(Contract):
    access_code: SecretStr = SecretStr("")


class NewProject(Contract):
    project_name: str = Field(min_length=1, max_length=150)
    stage: SDLCStage = SDLCStage.PLANNING
    requirement: str = ""
    description: str = ""
    model_policy: str = "user_default"


class ChatInput(Contract):
    message: str = ""
    action: str | None = None
    artifact_type: str | None = None
    task_id: str | None = None
    clarification_id: str | None = None
    version: str | None = None
    feedback: str = ""
    stage: str | None = None
    model_policy: str | None = None


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
        f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (8000, 5173, 4173)
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

    @app.post("/api/projects", dependencies=protected)
    def create_project(value: NewProject):
        return service.create_project(
            value.project_name, value.stage, value.requirement, value.description, value.model_policy
        )

    @app.get("/api/projects/{project_id}", dependencies=protected)
    def project(project_id: str):
        return service.open_project(project_id)

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
                    messages.put(
                        {
                            "type": "error",
                            "message": f"Operation failed ({type(exc).__name__}); retry the request.",
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

    @app.get("/api/projects/{project_id}/files", dependencies=protected)
    def files(project_id: str):
        return service.open_project(project_id)["assets"]

    @app.post("/api/projects/{project_id}/files", dependencies=protected)
    async def upload(
        project_id: str,
        file: UploadFile = File(...),
        artifact_type: str | None = Form(None),
        domain: str = Form("BUSINESS"),
    ):
        data = await file.read(10 * 1024 * 1024 + 1)
        return service.upload(project_id, file.filename or "upload", data, artifact_type, domain)

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
