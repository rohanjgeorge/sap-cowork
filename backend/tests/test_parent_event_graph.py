"""Acceptance contracts for the parent-orchestration behavior document."""

import pytest
from fastapi.testclient import TestClient

from backend.app.api import create_app
from backend.app.context_planning import items
from backend.app.context_sources import qualify
from backend.app.models import Artifact, CapabilityResponse, ContextItem, ContextPackage
from backend.app.orchestration_events import Intent, normalize_request
from backend.app.runtime import Runtime
from backend.app.services import ApplicationService
from backend.app.settings import MemorySecretStore
from backend.app.state_management import StateError
from backend.app.templates import TemplateRepository


def test_parent_authorizes_before_dispatch_and_guidance_does_not_execute(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    before = storage.load_state("p")
    trace = []
    called = []
    with pytest.raises(StateError, match="UNAUTHORIZED"):
        runtime.event_graph.dispatch(
            "p",
            {"action": "set_stage", "stage": "Design"},
            lambda r: called.append(r),
            actor="agent",
            trace=trace,
        )
    assert called == [] and storage.load_state("p") == before
    assert trace == ["load_project", "understand_request", "classify_intent"]
    result = runtime.event_graph.dispatch("p", {"action": "status"}, lambda r: "guidance", trace=trace)
    assert result == "guidance" and "project_guidance" in trace
    assert storage.load_state("p") == before and runtime.gateway.fake.calls == []


def test_navigation_and_status_remain_available_while_clarification_is_paused(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    runtime.state.apply("p", "set_requirement", {"requirement": "STO when material available"})
    service = ApplicationService(runtime)
    paused = service.chat("p", action="generate", artifact_type="FRD")
    task_id = paused["state"].active_task_id
    checkpoint = runtime.orchestrator.checkpoint_snapshot("p", task_id)
    result = service.chat("p", message="go to Testing")
    assert result["origin"] == "model"
    assert result["message"] != "Generate UAT"
    assert runtime.orchestrator.checkpoint_snapshot("p", task_id) == checkpoint
    assert result["workspace"]["state"].current_draft_stage == "Testing"
    assert result["workspace"]["state"].current_approved_stage == "Planning"
    assert result["workspace"]["state"].task_status == "awaiting_input"
    assert service.chat("p", message="status")["workspace"]["state"].active_task_id == task_id
    assert storage.list_artifacts("p") == []


def test_generation_finishes_then_exact_version_approval_is_separate(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    first = runtime.orchestrator.run("p", "BRD", task_id="first")
    assert first["artifact"].approval_status == "draft"
    assert runtime.orchestrator.checkpoint_snapshot("p", "first")["next"] == ()
    second = ApplicationService(runtime).chat(
        "p",
        message="revise BRD",
        feedback="Add exception handling",
        new_version=True,
        authors="Rohan",
        remarks="Explicit revision",
    )
    assert second["artifact"].artifact_version == "2"
    runtime.approvals.review("p", "BRD", "1", True)
    assert storage.load_artifact("p", "BRD", "1").approval_status == "approved"
    assert storage.load_artifact("p", "BRD", "2").approval_status == "draft"
    assert runtime.orchestrator.checkpoint_snapshot("p", "first")["next"] == ()


@pytest.mark.parametrize("defect", ["type", "project", "empty", "template", "missing_template", "source"])
def test_invalid_worker_output_never_persists_or_registers(storage, tmp_path, defect):
    runtime = Runtime(storage, tmp_path)
    template, ref = TemplateRepository().load("BRD")

    class Invalid:
        def invoke(self, request):
            artifact = Artifact(
                artifact_id="BRD",
                artifact_type="BRD",
                project_id="p",
                source_task_id=request.task_id,
                content=template,
                template_ref=ref,
                template_version=ref,
            )
            if defect == "type":
                artifact.artifact_type = "TDD"
            elif defect == "project":
                artifact.project_id = "other"
            elif defect == "empty":
                artifact.content = ""
            elif defect == "template":
                artifact.content = "# Incomplete document"
            elif defect == "missing_template":
                artifact.template_ref = None
            else:
                artifact.sources = ["invented:source"]
            return CapabilityResponse(
                task_id=request.task_id,
                capability_id=request.capability_id,
                status="success",
                output={"artifact": artifact.model_dump(mode="json")},
            )

    runtime.registry.register("BRD_GENERATOR", Invalid())
    result = runtime.orchestrator.run("p", "BRD")
    assert result["state"].task_status == "failed" and result["error"]
    assert storage.list_artifacts("p") == [] and storage.load_state("p").artifact_registry == []
    assert not any(r.get("kind") == "artifact_commit" for r in storage.list_context_runs("p"))


def test_saved_output_recovers_registration_after_restart_without_regeneration(
    storage, tmp_path, monkeypatch
):
    runtime = Runtime(storage, tmp_path)
    original = runtime.state.apply

    def fail_registration(project_id, operation, *args, **kwargs):
        if operation == "register_artifact":
            raise OSError("Registration unavailable")
        return original(project_id, operation, *args, **kwargs)

    monkeypatch.setattr(runtime.state, "apply", fail_registration)
    with pytest.raises(OSError):
        runtime.orchestrator.run("p", "BRD", task_id="recover")
    saved = storage.load_artifact("p", "BRD")
    assert storage.load_state("p").artifact_registry == []
    reopened = Runtime(storage, tmp_path)
    result = reopened.orchestrator.run("p", "BRD", task_id="recover")
    assert result["replayed"] and result["artifact"] == saved
    assert reopened.gateway.fake.calls == []
    assert len(storage.list_artifacts("p")) == 1
    assert storage.load_state("p").completed_tasks["recover"].version == "1"


def test_pre_execution_guard_rechecks_source_revocation(storage, tmp_path, monkeypatch):
    runtime = Runtime(storage, tmp_path)
    evidence = qualify(
        ContextItem(content="Private policy", source="org:private", source_type="curated"),
        "SAP_TECHNICAL",
        "p",
    )
    storage.save_context(
        "p", ContextPackage(project_id="p", task_id="source", sap_technical_context=[evidence])
    )
    original = runtime.orchestrator._before_execute

    def revoke(cursor, runtime):
        assert any(i.source == "org:private" for i in items(runtime.context.context))
        storage.replace_context(
            "p", "SAP_TECHNICAL", [evidence.model_copy(update={"access_status": "revoked"})]
        )
        return original(cursor, runtime)

    monkeypatch.setattr(runtime.orchestrator, "_before_execute", revoke)
    with pytest.raises(ValueError, match="access changed"):
        runtime.orchestrator.run("p", "TDD")
    assert storage.list_artifacts("p") == []
    assert all(call.context.get("operation") == "context_planning" for call in runtime.gateway.fake.calls)


def test_closed_project_rejects_mutating_events_before_upload_or_message(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        project = client.post("/api/projects", json={"project_name": "Closed"}).json()["project"][
            "project_id"
        ]
        client.post(f"/api/projects/{project}/chat", json={"action": "close_project"})
        storage = app.state.runtime.storage
        before = storage.load_session(project)
        assert (
            client.post(
                f"/api/projects/{project}/chat",
                json={"action": "submit_requirement", "message": "Unauthorized new CR"},
            ).status_code
            == 409
        )
        assert storage.load_session(project) == before
        assert (
            client.post(
                f"/api/projects/{project}/files", files={"file": ("private.txt", b"Do not save")}
            ).status_code
            == 409
        )
        assert not any(a.get("name") == "private.txt" for a in storage.list_project_assets(project))


def test_intents_are_finite_and_normalization_does_not_change_state(storage):
    state = storage.load_state("p")
    before = state.model_dump()
    assert normalize_request(state, {"message": "generate ABAP"})["artifact_type"] == "ABAP"
    assert state.model_dump() == before
    assert len(Intent) >= 20
