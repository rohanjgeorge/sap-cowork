from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from docx import Document
from fastapi.testclient import TestClient

from backend.app.api import create_app
from backend.app.local_storage import LocalStorageProvider
from backend.app.models import ContextItem, ContextPackage, ContextRequest, Project
from backend.app.context_handler import ContextHandler
from backend.app.settings import MemorySecretStore
from backend.app.state_management import StateError, StateManagementService


def test_v11_shared_api_vertical_slice_and_docx_roundtrip(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        p = client.post(
            "/api/projects",
            json={"project_name": "STO", "requirement": "STO delivery when material available"},
        ).json()["project"]["project_id"]
        root = f"/api/projects/{p}"
        initial = client.get(root + "/state").json()
        nav = client.post(
            root + "/state/operations",
            json={
                "operation": "change_draft_stage",
                "payload": {"stage": "Testing"},
                "expected_revision": initial["state_revision"],
                "request_id": "nav-once",
            },
        )
        assert nav.status_code == 200, nav.text
        assert nav.json()["state"]["current_approved_stage"] == "Planning"
        conflict = client.post(
            root + "/state/operations",
            json={
                "operation": "change_draft_stage",
                "payload": {"stage": "Design"},
                "expected_revision": initial["state_revision"],
                "request_id": "stale",
            },
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == "REVISION_CONFLICT"
        for kind in ("BRD", "FRD", "USER_STORIES", "TDD", "ABAP", "SIT", "UAT"):
            generated = client.post(root + "/chat", json={"action": "generate", "artifact_type": kind}).json()
            if kind == "FRD":
                assert generated["workspace"]["state"]["task_status"] == "awaiting_input"
                generated = client.post(
                    root + "/chat",
                    json={"action": "answer", "message": "Full unrestricted stock in plant 1000"},
                ).json()
            assert generated.get("artifact"), generated
            assert generated["artifact"]["approval_status"] == "draft"
            if kind != "ABAP":
                download = client.get(root + f"/artifacts/{kind}/download")
                assert download.status_code == 200
                assert Document(BytesIO(download.content)).paragraphs
                approved = client.post(
                    root + f"/artifacts/{kind}/review", json={"action": "approve", "version": "1"}
                )
                assert approved.status_code == 200, approved.text
        for action in ("confirm_code", "confirm_testing"):
            result = client.post(root + "/chat", json={"action": action})
            assert result.status_code == 200, result.text
        confirmed = client.get(root + "/state").json()
        assert confirmed["current_approved_stage"] == "Testing"
        assert confirmed["follow_ups"]["audit_report"] == "completed"
        closed = client.post(root + "/chat", json={"action": "close_project"}).json()["workspace"]["state"]
        assert closed["project_status"] == "completed"
        assert closed["follow_ups"]["learning"] == "completed"
        assert (
            client.post(root + "/chat", json={"action": "generate", "artifact_type": "BRD"}).status_code
            == 409
        )
        reopened = client.post(root + "/chat", json={"action": "reopen_project"})
        assert reopened.json()["workspace"]["state"]["project_status"] == "active"


def test_concurrent_revisions_have_one_winner_across_provider_instances(tmp_path):
    states = StateManagementService(LocalStorageProvider(tmp_path))
    states.create_project(Project(project_id="p", project_name="Concurrent"))

    def update(stage):
        try:
            return (
                StateManagementService(LocalStorageProvider(tmp_path))
                .apply("p", "change_draft_stage", {"stage": stage}, expected_revision=1)
                .state_revision
            )
        except StateError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(update, ["Design", "Testing"]))
    assert sorted(map(str, results)) == ["2", "REVISION_CONFLICT"]


def test_chat_navigation_checks_revision_inside_the_commit(tmp_path, monkeypatch):
    from threading import Barrier, local
    from backend.app.runtime import Runtime
    from backend.app.services import ApplicationService

    store = LocalStorageProvider(tmp_path)
    StateManagementService(store).create_project(Project(project_id="p", project_name="Concurrent chat"))
    barrier, thread_state = Barrier(2), local()
    original = store.load_state

    def synchronized_read(project_id):
        state = original(project_id)
        if not getattr(thread_state, "read", False):
            thread_state.read = True
            barrier.wait(timeout=10)
        return state

    monkeypatch.setattr(store, "load_state", synchronized_read)

    def navigate(stage):
        try:
            service = ApplicationService(Runtime(store, tmp_path, MemorySecretStore()))
            return service.chat("p", action="set_stage", stage=stage, expected_revision=1)["workspace"][
                "state"
            ].state_revision
        except StateError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(navigate, ["Design", "Testing"]))
    assert sorted(map(str, results)) == ["2", "REVISION_CONFLICT"]


def test_context_scope_provenance_and_conflicts_are_preserved(tmp_path):
    store = LocalStorageProvider(tmp_path)
    states = StateManagementService(store)
    states.create_project(Project(project_id="p", project_name="Scoped", organization_id="ABC"))
    store.save_context(
        "p",
        ContextPackage(
            project_id="p",
            task_id="source",
            sap_technical_context=[
                ContextItem(
                    content="Qualified release fact",
                    source="organization:ABC:1",
                    source_type="curated",
                    scope="organization",
                    organization_id="ABC",
                    source_version="1",
                    origin="org-library",
                    conflict="Newer source needs reconciliation",
                ),
                ContextItem(
                    content="Must not cross tenant",
                    source="organization:XYZ:1",
                    source_type="curated",
                    organization_id="XYZ",
                ),
            ],
        ),
    )
    package = ContextHandler(store).load(
        ContextRequest(
            project_id="p",
            task_id="t",
            current_stage="Design",
            current_task="TDD",
            required_domains=["SAP_TECHNICAL"],
        )
    )
    assert len(package.sap_technical_context) == 1
    item = package.sap_technical_context[0]
    assert item.source_version == "1" and item.conflict and item.origin == "org-library"


def test_historical_clarification_resolution_does_not_regenerate_artifacts(tmp_path):
    from backend.app.runtime import Runtime

    runtime = Runtime(LocalStorageProvider(tmp_path), tmp_path, MemorySecretStore())
    runtime.state.create_project(
        Project(project_id="p", project_name="Clarification history"),
        requirement="STO when material available",
    )
    result = runtime.orchestrator.run("p", "FRD")
    question = result["state"].clarifications[-1]
    runtime.orchestrator.clarifications.answer(
        runtime.orchestrator, "p", question.clarification_id, "Unrestricted stock"
    )
    runtime.state.apply("p", "reopen_clarification", {"clarification_id": question.clarification_id})
    calls = len(runtime.gateway.fake.calls)
    runtime.orchestrator.clarifications.answer(
        runtime.orchestrator,
        "p",
        question.clarification_id,
        "Confirmed for this CR",
        request_id="historical-answer",
    )
    runtime.orchestrator.clarifications.answer(
        runtime.orchestrator,
        "p",
        question.clarification_id,
        "Confirmed for this CR",
        request_id="historical-answer",
    )
    assert len(runtime.gateway.fake.calls) == calls
    assert len(runtime.storage.list_artifacts("p")) == 1


def test_audit_failure_does_not_undo_testing_and_learning_failure_does_not_reopen(tmp_path, monkeypatch):
    from backend.app.runtime import Runtime
    from backend.app.services import ApplicationService
    from backend.tests.test_state_v11 import register

    runtime = Runtime(LocalStorageProvider(tmp_path), tmp_path, MemorySecretStore())
    service = ApplicationService(runtime)
    runtime.state.create_project(Project(project_id="p", project_name="Recovery"))
    for kind in ("BRD", "FRD", "USER_STORIES", "TDD", "ABAP", "SIT", "UAT"):
        register(runtime.storage, runtime.state, kind)
    runtime.state.apply("p", "confirm_code")
    monkeypatch.setattr(runtime.orchestrator, "run", lambda *a, **k: {"error": "unavailable"})
    service.chat("p", action="confirm_testing")
    assert runtime.storage.load_state("p").confirmations[-1].active
    assert runtime.storage.load_state("p").follow_ups["audit_report"].startswith("retry_required")
    monkeypatch.setattr(
        runtime.storage, "save_upload", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )
    service.chat("p", action="close_project")
    assert runtime.storage.load_state("p").project_status == "completed"
    assert runtime.storage.load_state("p").follow_ups["learning"].startswith("retry_required")
