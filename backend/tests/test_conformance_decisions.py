"""Decided consolidated-requirement acceptance cases, added before fixes."""

from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from backend.app.api import create_app
from backend.app.runtime import Runtime
from backend.app.services import ApplicationService
from backend.app.settings import MemorySecretStore
from backend.app.models import Artifact, CapabilityResponse, ContextBudget, ContextItem, now
from backend.app.state_management import StateError, stage_complete
from backend.app.model_gateway import estimate_tokens


def baseline(runtime, kind, approved=False):
    s = runtime.storage
    a = Artifact(
        artifact_id=kind,
        artifact_type=kind,
        project_id="p",
        content="Baseline " + kind,
        artifact_version="1",
        template_version="test",
    )
    s.save_artifact("p", a)
    runtime.state.apply("p", "register_artifact", {"artifact_id": kind, "version": "1"})
    if approved:
        runtime.state.apply("p", "approve_artifact", {"artifact_id": kind, "version": "1"})


def test_g01_chat_mutations_capture_contract_replay_and_reject_stale(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    service = ApplicationService(r)
    rev = storage.load_state("p").state_revision
    first = service.chat(
        "p", action="set_stage", stage="Design", request_id="navigation", expected_revision=rev
    )
    after = storage.load_state("p").state_revision
    service.chat("p", action="set_stage", stage="Design", request_id="navigation", expected_revision=rev)
    assert storage.load_state("p").state_revision == after
    with pytest.raises(StateError):
        service.chat("p", action="set_stage", stage="Testing", expected_revision=rev)
    assert first["workspace"]["state"].current_draft_stage == "Design"


def test_g02_changed_generation_payload_conflicts(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD", task_id="identity")
    with pytest.raises(StateError, match="IDENTITY_CONFLICT"):
        r.orchestrator.run("p", "BRD", inputs={"instructions": "Different scope"}, task_id="identity")
    assert r.orchestrator.run("p", "BRD", task_id="identity")["replayed"]


@pytest.mark.parametrize("operation", ["generation", "confirm_code", "close_project"])
def test_g03_blocker_flags_prevent_execution_but_allow_navigation(storage, tmp_path, operation):
    r = Runtime(storage, tmp_path)
    baseline(r, "ABAP")
    r.state.apply("p", "add_flag", {"type": "blocker", "description": "Execution hold"})
    with pytest.raises(StateError, match="BLOCKED"):
        if operation == "generation":
            r.orchestrator.run("p", "BRD")
        else:
            r.state.apply("p", operation)
    r.state.apply("p", "change_draft_stage", {"stage": "Testing"})
    assert r.status.get("p")["current_draft_stage"] == "Testing"


@pytest.mark.parametrize("approved", [[], ["SIT"], ["SIT", "UAT"]])
def test_g04_testing_requires_approved_baselines(storage, tmp_path, approved):
    r = Runtime(storage, tmp_path)
    for kind in ["ABAP", "SIT", "UAT"]:
        baseline(r, kind, kind in approved)
    if len(approved) < 2:
        with pytest.raises(StateError):
            r.state.apply("p", "confirm_testing")
    else:
        state = r.state.apply(
            "p", "confirm_testing", {"remarks": "Applicable tests passed", "evidence_refs": ["test-run:42"]}
        )
        assert stage_complete(state, "Testing")
        assert state.confirmations[-1].artifact_hashes and state.confirmations[-1].evidence_refs == [
            "test-run:42"
        ]
        state = r.state.apply("p", "withdraw_confirmation", {"kind": "testing"})
        assert not stage_complete(state, "Testing")


def test_g05_artifact_success_requires_output(storage, tmp_path):
    r = Runtime(storage, tmp_path)

    class Empty:
        def invoke(self, request):
            return CapabilityResponse(
                task_id=request.task_id, capability_id=request.capability_id, status="success"
            )

    r.registry.register("BRD_GENERATOR", Empty())
    out = r.orchestrator.run("p", "BRD")
    assert out.get("error_code") == "OUTPUT_CONTRACT_FAILED"
    assert storage.load_state("p").task_status == "failed" and not storage.list_artifacts("p")


def test_g06_entire_low_budget_package_is_bounded_or_explicitly_rejected(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.context_planning.budget = ContextBudget(max_tokens=1000)
    result = r.orchestrator.run("p", "TDD")
    for rec in storage.list_context_runs("p"):
        if rec.get("package"):
            assert estimate_tokens(rec["package"]) <= 1000
    assert result.get("artifact") or result.get("error_code") == "context_budget_exceeded"


def test_g09_missing_target_and_future_effective_evidence_is_not_verified(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    p = storage.load_project("p")
    future = ContextItem(
        content="STO", source="future", source_type="curated", effective_from=now() + timedelta(days=10)
    )
    assert r.context_planning._mismatches(future, p)


def test_g10_inferred_evidence_populates_explicit_assumptions(storage, tmp_path):
    from backend.app.models import ContextPackage

    r = Runtime(storage, tmp_path)
    storage.save_context(
        "p",
        ContextPackage(
            project_id="p",
            task_id="evidence",
            sap_technical_context=[
                ContextItem(
                    content="Assume synchronous interface pending confirmation",
                    source="inference",
                    source_type="curated",
                    evidence_status="inferred",
                )
            ],
        ),
    )
    out = r.orchestrator.run("p", "TDD")
    rec = storage.load_context_run("p", out["artifact"].context_plan_ref)
    assert rec["package"]["assumptions"]
    assert "retrieval_trace" in rec and not any(g["attempted_sources"] for g in rec["plan"]["gaps"])


def test_g08_worker_receives_immutable_compact_view(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    original = r.registry._implementations["BRD_GENERATOR"]

    class Inspect:
        def invoke(self, request):
            from backend.app.models import TaskProjectView

            assert isinstance(request.state, TaskProjectView)
            assert not hasattr(request.state, "completed_tasks")
            with pytest.raises((ValueError, TypeError)):
                request.state.project_name = "Changed"
            return original.invoke(request)

    r.registry.register("BRD_GENERATOR", Inspect())
    assert r.orchestrator.run("p", "BRD")["artifact"]


def test_g11_shared_metadata_update_has_revision_and_replay(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as c:
        c.post("/api/session", json={"access_code": ""})
        p = c.post("/api/projects", json={"project_name": "Metadata"}).json()["project"]["project_id"]
        rev = c.get(f"/api/projects/{p}/state").json()["state_revision"]
        payload = {
            "organization_id": "ABC",
            "program_id": "P1",
            "sap_applicability": {
                "product": "S4",
                "deployment": "on-premise",
                "release": "2023",
                "system": "S4P",
                "client": "100",
            },
            "expected_revision": rev,
            "request_id": "metadata",
        }
        first = c.put(f"/api/projects/{p}/metadata", json=payload)
        assert first.status_code == 200, first.text
        assert c.put(f"/api/projects/{p}/metadata", json=payload).status_code == 200
        assert c.get(f"/api/projects/{p}").json()["project"]["program_id"] == "P1"
        payload.update(request_id="stale", program_id="P2")
        assert c.put(f"/api/projects/{p}/metadata", json=payload).status_code == 409


def test_g01_upload_edit_delete_replay_and_automatic_envelopes(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    service = ApplicationService(r)
    uploaded = service.upload("p", "CR.txt", b"A synthetic CR", request_id="upload")
    assert (
        service.upload("p", "CR.txt", b"A synthetic CR", request_id="upload")["file_id"]
        == uploaded["file_id"]
    )
    assert len([a for a in storage.list_project_assets("p") if a["kind"] == "upload"]) == 1
    r.orchestrator.run("p", "BRD")
    rev = storage.load_state("p").state_revision
    edited = service.edit_artifact(
        "p",
        "BRD",
        content="Revised Draft",
        new_version=True,
        authors="Reviewer",
        remarks="Explicit revision",
        request_id="edit",
        expected_revision=rev,
    )
    replay = service.edit_artifact(
        "p",
        "BRD",
        content="Revised Draft",
        new_version=True,
        authors="Reviewer",
        remarks="Explicit revision",
        request_id="edit",
        expected_revision=rev,
    )
    assert replay["artifact"].artifact_version == edited["artifact"].artifact_version == "2"
    service.delete_artifact("p", "BRD", "2", request_id="delete")
    service.delete_artifact("p", "BRD", "2", request_id="delete")
    with pytest.raises(StateError, match="REVISION_CONFLICT"):
        service.upload("p", "new.txt", b"Stale", request_id="stale-upload", expected_revision=rev)
    service.chat("p", action="set_stage", stage="Testing")
    records = [x for x in storage.list_context_runs("p") if x.get("kind") == "mutation"]
    assert records and all(
        x["request_id"] and x["actor"] == "local" and isinstance(x["expected_revision"], int) for x in records
    )


def test_g01_edit_recovers_after_memory_failure_without_another_version(storage, tmp_path, monkeypatch):
    r = Runtime(storage, tmp_path)
    service = ApplicationService(r)
    r.orchestrator.run("p", "BRD")
    original = r.memory.refresh
    monkeypatch.setattr(
        r.memory, "refresh", lambda state: (_ for _ in ()).throw(OSError("memory unavailable"))
    )
    with pytest.raises(OSError):
        service.edit_artifact(
            "p",
            "BRD",
            content="Revision",
            new_version=True,
            authors="R",
            remarks="scope",
            request_id="recover-edit",
        )
    monkeypatch.setattr(r.memory, "refresh", original)
    result = service.edit_artifact(
        "p",
        "BRD",
        content="Revision",
        new_version=True,
        authors="R",
        remarks="scope",
        request_id="recover-edit",
    )
    assert result["artifact"].artifact_version == "2" and len(storage.list_artifacts("p")) == 2


def test_g03_scoped_blocker_does_not_block_other_artifacts(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.state.apply(
        "p",
        "add_flag",
        {"type": "blocker", "description": "Hold technical design", "related_artifact": "TDD"},
    )
    assert r.orchestrator.run("p", "BRD")["artifact"]
    with pytest.raises(StateError, match="BLOCKED"):
        r.orchestrator.run("p", "TDD")


def test_g04_new_test_version_invalidates_approved_confirmation(storage, tmp_path):

    r = Runtime(storage, tmp_path)
    for kind in ["ABAP", "SIT", "UAT"]:
        baseline(r, kind, True)
    state = r.state.apply("p", "confirm_testing")
    assert stage_complete(state, "Testing")
    _, state = r.artifacts.edit("p", "UAT", "Changed approved test baseline")
    assert not stage_complete(state, "Testing")
    state = r.state.apply("p", "approve_artifact", {"artifact_id": "UAT", "version": "2"})
    assert not stage_complete(state, "Testing")


def test_g07_checkpoint_wait_wins_over_stale_status_projection(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.state.apply("p", "set_requirement", {"requirement": "STO delivery when material available"})
    paused = r.orchestrator.run("p", "FRD", task_id="runtime-authority")
    question = paused["state"].clarifications[-1]
    # Simulate a pre-existing stale compatibility projection, not a workflow change.
    state = storage.load_state("p")
    state.active_task_id = "stale"
    state.task_status = "idle"
    state.current_task = "Generate ABAP"
    storage.save_state("p", state)
    result = r.orchestrator.clarifications.answer(
        r.orchestrator, "p", question.clarification_id, "Use unrestricted stock, full quantity only"
    )
    assert result["artifact"].artifact_type == "FRD" and not r.abap.invocations


def test_g10_unexecuted_sources_are_not_reported_as_attempts(storage, tmp_path):
    from backend.app.models import SourceCategory

    r = Runtime(storage, tmp_path)
    r.context_planning.budget = ContextBudget(max_actions=1)

    class Adapter:
        category = SourceCategory.SAP_STANDARD
        parallel_safe = False

        def __init__(self, name):
            self.adapter_id = name
            self.calls = 0

        def authorized(self, project, user):
            return True

        def discover(self, project, requirements):
            return [{"object_id": "STO"}]

        def retrieve(self, project, action, *, timeout_seconds):
            self.calls += 1
            return []

    a, b = Adapter("a"), Adapter("b")
    r.context_sources.register(a)
    r.context_sources.register(b)
    out = r.orchestrator.run("p", "TDD")
    rec = storage.load_context_run("p", out["artifact"].context_plan_ref)
    assert a.calls == 1 and b.calls == 0
    assert all("b" not in g["attempted_sources"] for g in rec["plan"]["gaps"])
    assert any("b" in g["unattempted_sources"] for g in rec["plan"]["gaps"])


def test_g09_target_requires_explicit_or_trusted_binding(storage, tmp_path):
    from backend.tests.test_context_planning import LiveTestAdapter

    r = Runtime(storage, tmp_path)
    r.context_sources.register(LiveTestAdapter())
    first = r.orchestrator.run("p", "TDD")
    rec = storage.load_context_run("p", first["artifact"].context_plan_ref)
    assert rec["plan"]["coverage"]["sap.release"] != "satisfied"
    r.context_sources.target_bindings["test-live"] = {
        "project_id": "p",
        "applicability": {"product": "S4", "deployment": "on-premise", "release": "2023", "system": "S4P"},
    }
    second = r.orchestrator.run("p", "TDD")
    rec = storage.load_context_run("p", second["artifact"].context_plan_ref)
    assert rec["plan"]["coverage"]["sap.release"] == "satisfied"
    p = storage.load_project("p")
    p.sap_applicability = {"product": "S4", "deployment": "on-premise", "release": "2022", "system": "S4P"}
    storage.save_project(p)
    assert r.context_planning._mismatches(
        ContextItem(content="STO", source="s", source_type="curated", applicability={"release": "2023"}), p
    )


def test_g01_project_creation_deduplicates_client_request(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as c:
        c.post("/api/session", json={"access_code": ""})
        payload = {"project_name": "Idempotent creation", "request_id": "create-once"}
        first = c.post("/api/projects", json=payload)
        assert first.status_code == 200
        second = c.post("/api/projects", json=payload)
        assert (
            second.status_code == 200
            and first.json()["project"]["project_id"] == second.json()["project"]["project_id"]
        )
        assert len(c.get("/api/projects").json()) == 1


def test_g02_explicit_upstream_versions_are_part_of_identity(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.orchestrator.run("p", "BRD", inputs={"upstream_refs": ["upload:source:v1"]}, task_id="upstream-id")
    with pytest.raises(StateError, match="IDENTITY_CONFLICT"):
        r.orchestrator.run("p", "BRD", inputs={"upstream_refs": ["upload:source:v2"]}, task_id="upstream-id")


def test_g11_cli_creates_and_edits_same_metadata_contract(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from cli import main

    monkeypatch.setenv("COWORK_CLI_HOME", str(tmp_path))
    calls = []

    def call(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"project": {"project_id": "p", "sap_applicability": {}}, "state": {"state_revision": 4}}

    monkeypatch.setattr(main, "call", call)
    result = CliRunner().invoke(
        main.app,
        [
            "projects",
            "create",
            "--name",
            "CLI metadata",
            "--organization-id",
            "ABC",
            "--program-id",
            "P1",
            "--sap-product",
            "S4",
            "--release",
            "2023",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls[0][2]["json"]["sap_applicability"]["release"] == "2023"
    result = CliRunner().invoke(main.app, ["projects", "metadata", "--system", "S4P", "--client", "100"])
    assert result.exit_code == 0, result.output
    method, path, options = calls[-1]
    assert method == "PUT" and path == "/projects/p/metadata" and options["json"]["expected_revision"] == 4


def test_g06_minimum_overhead_failure_is_explicit_and_never_saves_oversized_package(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    r.context_planning.budget = ContextBudget(max_tokens=1000)
    out = r.orchestrator.run("p", "TDD", task_id="large-" + "x" * 6000)
    assert out.get("error_code") == "context_budget_exceeded"
    assert storage.list_artifacts("p") == []
    assert all(
        not rec.get("package") or estimate_tokens(rec["package"]) <= 1000
        for rec in storage.list_context_runs("p")
    )


def test_g09_effective_interval_uses_project_date(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    p = storage.load_project("p")
    p.context_date = now() - timedelta(days=5)
    item = ContextItem(
        content="Policy",
        source="policy",
        source_type="curated",
        effective_from=now() - timedelta(days=10),
        effective_to=now() - timedelta(days=1),
    )
    assert not r.context_planning._mismatches(item, p)
    p.context_date = now()
    assert r.context_planning._mismatches(item, p)


def test_g10_discovery_denial_is_not_a_retrieval_attempt(storage, tmp_path):
    from backend.app.models import SourceCategory

    r = Runtime(storage, tmp_path)

    class Denied:
        adapter_id = "denied-source"
        category = SourceCategory.SAP_STANDARD

        def authorized(self, project, user):
            return False

        def discover(self, project, requirements):
            raise AssertionError("Unauthorized discovery")

        def retrieve(self, *args, **kwargs):
            raise AssertionError("Unauthorized retrieval")

    r.context_sources.register(Denied())
    out = r.orchestrator.run("p", "TDD")
    rec = storage.load_context_run("p", out["artifact"].context_plan_ref)
    assert not any("denied-source" in g["attempted_sources"] for g in rec["plan"]["gaps"])


def test_g01_generation_failure_is_retryable_under_same_request(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    service = ApplicationService(r)
    original = r.registry._implementations["BRD_GENERATOR"]

    class Failed:
        def invoke(self, request):
            return CapabilityResponse(
                task_id=request.task_id,
                capability_id=request.capability_id,
                status="failed",
                error="Transient provider error",
            )

    r.registry.register("BRD_GENERATOR", Failed())
    first = service.chat(
        "p", action="generate", artifact_type="BRD", task_id="retryable-task", request_id="retryable-request"
    )
    assert first.get("error")
    r.registry.register("BRD_GENERATOR", original)
    result = service.chat(
        "p", action="generate", artifact_type="BRD", task_id="retryable-task", request_id="retryable-request"
    )
    assert result.get("artifact") and not result.get("error")


def test_g02_service_retry_normalizes_omitted_and_explicit_defaults(storage, tmp_path):
    r = Runtime(storage, tmp_path)
    service = ApplicationService(r)
    first = service.chat(
        "p",
        action="generate",
        artifact_type="BRD",
        task_id="normalized-task",
        request_id="normalized-request",
    )
    second = service.chat(
        "p",
        action="generate",
        artifact_type="BRD",
        task_id="normalized-task",
        request_id="normalized-request",
        feedback="",
        new_version=False,
        authors="",
        remarks="",
        model_policy="user_default",
        evidence_refs=[],
    )
    assert second["artifact"].artifact_version == first["artifact"].artifact_version
    assert len(storage.list_artifacts("p")) == 1


def test_g08_conversation_model_context_omits_execution_projection_fields(storage, tmp_path):
    import json

    r = Runtime(storage, tmp_path)
    assert r.orchestrator.converse("p", "What is the project status?")["origin"] == "model"
    sent = json.dumps(r.gateway.fake.calls[-1].context)
    assert "completed_tasks" not in sent and "task_inputs" not in sent
