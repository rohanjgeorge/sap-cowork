"""Run equivalent domain scenarios against the retained and replacement runtimes."""

import json
import re
import sqlite3

import pytest
from fastapi.encoders import jsonable_encoder

from backend.app.local_storage import LocalStorageProvider
from backend.app.models import Artifact, CapabilityResponse, Project, ProjectMemory, ProjectState
from backend.app.runtime import Runtime
from backend.app.templates import TemplateRepository


def build(root, backend, requirement="Automate STO deliveries"):
    storage = LocalStorageProvider(root)
    if not storage.list_projects():
        storage.create_project(Project(project_id="p", project_name="STO Automation"))
        storage.save_state("p", ProjectState(project_id="p", requirement=requirement))
        storage.save_memory("p", ProjectMemory(project_id="p"))
    return Runtime(storage, root, orchestration_backend=backend)


def normalize(value):
    text = json.dumps(jsonable_encoder(value), sort_keys=True)
    text = re.sub(r"\b[0-9a-f]{32}\b", "<id>", text)
    text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:\+00:00|Z)", "<time>", text)
    return json.loads(text)


def domain_snapshot(runtime):
    """Compare retained runtime invariants; V1.1 policy deltas have separate tests."""
    storage = runtime.storage
    state = storage.load_state("p")
    latest = {r.artifact_type: storage.load_artifact("p", r.artifact_id) for r in storage.list_artifacts("p")}
    return normalize(
        {
            "stage": state.current_stage,
            "task_status": state.task_status,
            "task": state.active_task_id,
            "capability": state.active_capability_id,
            "questions": [(q.question, q.status, q.response) for q in state.clarifications],
            "artifacts": sorted((kind, a.source_task_id) for kind, a in latest.items()),
            "transitions": [
                (e["kind"], e["task_status"], e["capability_id"])
                for e in storage.list_events("p")
                if e["kind"] != "state_changed"
            ],
        }
    )


@pytest.mark.parametrize(
    "scenario", ["sto", "missing_brd", "missing_requirement", "revision", "draft_abap", "failure"]
)
def test_legacy_and_langgraph_behavioral_parity(tmp_path, scenario):
    snapshots = []
    for backend in ("legacy", "langgraph"):
        requirement = (
            "STO delivery when material available" if scenario == "sto" else "Automate STO deliveries"
        )
        runtime = build(tmp_path / backend, backend, "" if scenario == "missing_requirement" else requirement)
        o = runtime.orchestrator
        if scenario == "sto":
            o.run("p", "BRD", task_id="brd-task")
            runtime.approvals.review("p", "BRD", "1", True)
            result = o.run("p", "FRD", task_id="frd-task")
            assert result["state"].task_status == "awaiting_input"
            question = result["state"].open_clarifications[-1]
            o.clarifications.answer(
                o, "p", question.clarification_id, "Unrestricted stock, full quantity only"
            )
            runtime.approvals.review("p", "FRD", "1", True)
            o.run("p", "TDD", task_id="tdd-task")
            runtime.approvals.review("p", "TDD", "1", True)
            o.run("p", "ABAP", task_id="abap-task")
        elif scenario == "missing_brd":
            assert o.run("p", "FRD", task_id="frd-task")["artifact"]
        elif scenario == "missing_requirement":
            assert o.run("p", "BRD", task_id="brd-task")["state"].task_status == "awaiting_input"
        elif scenario == "revision":
            o.run("p", "BRD", task_id="first")
            runtime.approvals.review("p", "BRD", "1", False, "Add failure reporting")
            o.run("p", "BRD", task_id="second")
        elif scenario == "draft_abap":
            o.run("p", "TDD", task_id="tdd-task")
            assert o.run("p", "ABAP", task_id="abap-task")["artifact"]
            issue = next(i for i in runtime.status.get("p")["issues"] if i["code"] == "TDD_UNAPPROVED")
            assert issue["severity"] == "error" and not issue["blocking"]
        else:

            class Failed:
                def invoke(self, request):
                    return CapabilityResponse(
                        task_id=request.task_id,
                        capability_id=request.capability_id,
                        status="failed",
                        error="simulated failure",
                    )

            runtime.registry.register("BRD_GENERATOR", Failed())
            assert o.run("p", "BRD", task_id="failed")["state"].task_status == "failed"
        snapshots.append(domain_snapshot(runtime))
    assert snapshots[0] == snapshots[1]


def test_sqlite_resume_after_runtime_recreation_keeps_domain_source_of_truth(tmp_path):
    runtime = build(tmp_path, "langgraph", "STO delivery when material available")
    paused = runtime.orchestrator.run("p", "FRD", task_id="resume-task")
    assert runtime.orchestrator.checkpoint_snapshot("p", "resume-task")["next"] == ("plan_context",)
    question = paused["state"].open_clarifications[-1]
    reopened = build(tmp_path, "langgraph")
    result = reopened.orchestrator.clarifications.answer(
        reopened.orchestrator,
        "p",
        question.clarification_id,
        "Unrestricted stock in plant 1000; no partial delivery",
    )
    assert result["state"].active_task_id == "resume-task"
    assert result["artifact"].artifact_type == "FRD"
    assert reopened.orchestrator.checkpoint_snapshot("p", "resume-task")["next"] == ()
    reopened.approvals.review("p", "FRD", "1", True)
    assert reopened.orchestrator.checkpoint_snapshot("p", "resume-task")["next"] == ()
    assert reopened.storage.load_state("p").current_approved_stage == "Planning"


def test_checkpoints_contain_runtime_cursors_not_project_payloads(tmp_path):
    marker = "DO_NOT_CHECKPOINT_THIS_BUSINESS_REQUIREMENT"
    runtime = build(tmp_path, "langgraph", marker)
    runtime.orchestrator.run("p", "BRD", task_id="private-task")
    snapshot = runtime.orchestrator.checkpoint_snapshot("p", "private-task")
    assert set(snapshot["values"]) == {
        "project_id",
        "task_id",
        "entry",
        "artifact_type",
        "next_step",
        "wait_reason",
        "context_plan_ref",
        "context_package_ref",
        "replan_count",
    }
    database = tmp_path / "runtime/langgraph/checkpoints.sqlite"
    with sqlite3.connect(database) as connection:
        for table in ("checkpoints", "writes"):
            for row in connection.execute("SELECT * FROM " + table):
                assert not any(
                    marker.encode() in (v if isinstance(v, bytes) else str(v).encode()) for v in row
                )
    assert marker in runtime.storage.load_memory("p").content


def test_worker_clarification_resumes_without_replaying_a_completed_generation(tmp_path):
    runtime = build(tmp_path, "langgraph")

    class Worker:
        def __init__(self):
            self.calls = 0

        def invoke(self, request):
            self.calls += 1
            if self.calls == 1:
                return CapabilityResponse(
                    task_id=request.task_id,
                    capability_id=request.capability_id,
                    status="clarification_required",
                    clarification_questions=["Confirm the business owner."],
                )
            artifact = Artifact(
                project_id="p",
                artifact_id="BRD",
                artifact_type="BRD",
                content=TemplateRepository().load("BRD")[0],
                artifact_version="1",
                template_version="brd.md",
                template_ref="brd.md",
                source_task_id=request.task_id,
            )
            return CapabilityResponse(
                task_id=request.task_id,
                capability_id=request.capability_id,
                status="success",
                output={"artifact": artifact.model_dump(mode="json")},
            )

    worker = Worker()
    runtime.registry.register("BRD_GENERATOR", worker)
    result = runtime.orchestrator.run("p", "BRD", task_id="worker-task")
    runtime.orchestrator.clarifications.answer(
        runtime.orchestrator,
        "p",
        result["state"].open_clarifications[-1].clarification_id,
        "Business owner is the logistics lead",
    )
    assert worker.calls == 2
    runtime.approvals.review("p", "BRD", "1", True)
    assert worker.calls == 2
    assert runtime.orchestrator.run("p", "BRD", task_id="worker-task")["replayed"]
    assert worker.calls == 2


def test_ordinary_conversation_and_progress_keep_legacy_behavior(tmp_path):
    from backend.app.services import ApplicationService

    snapshots = []
    for backend in ("legacy", "langgraph"):
        runtime = build(tmp_path / backend, backend)
        service = ApplicationService(runtime)
        progress = []
        result = service.chat(
            "p", message="What can you help me with?", task_id="chat-task", progress=progress.append
        )
        snapshots.append(
            normalize(
                {
                    "response": {k: result[k] for k in ("message", "origin", "provider", "model")},
                    "progress": progress,
                    "requests": [(r.task_id, r.messages) for r in runtime.gateway.fake.calls],
                    "domain": domain_snapshot(runtime),
                }
            )
        )
    assert snapshots[0] == snapshots[1]


def test_uncommitted_checkpoint_cannot_advance_domain_or_duplicate_retry(tmp_path, monkeypatch):
    runtime = build(tmp_path, "langgraph")
    original = runtime.memory.refresh

    def fail(state):
        raise OSError("simulated storage failure after generation")

    monkeypatch.setattr(runtime.memory, "refresh", fail)
    with pytest.raises(OSError):
        runtime.orchestrator.run("p", "BRD", task_id="retry-task")
    assert runtime.storage.load_state("p").task_status == "failed"
    assert runtime.storage.load_artifact("p", "BRD").approval_status == "draft"
    monkeypatch.setattr(runtime.memory, "refresh", original)
    result = runtime.orchestrator.run("p", "BRD", task_id="retry-task")
    assert result["artifact"].artifact_version == "1"
    assert len(runtime.storage.list_artifacts("p")) == 1
    assert runtime.orchestrator.run("p", "BRD", task_id="retry-task")["replayed"]


def test_pre_migration_clarification_can_be_adopted_without_a_checkpoint(tmp_path):
    original = build(tmp_path, "legacy", "STO delivery when material available")
    waiting = original.orchestrator.run("p", "FRD", task_id="pre-migration")
    migrated = build(tmp_path, "langgraph")
    result = migrated.orchestrator.clarifications.answer(
        migrated.orchestrator,
        "p",
        waiting["state"].open_clarifications[-1].clarification_id,
        "Use unrestricted stock; full quantity",
    )
    assert result["artifact"].artifact_type == "FRD"
    assert result["state"].active_task_id == "pre-migration"


def test_multiple_questions_do_not_resume_execution_until_all_are_answered(tmp_path):
    runtime = build(tmp_path, "langgraph")
    artifact_worker = runtime.registry._implementations["BRD_GENERATOR"]

    class Worker:
        def __init__(self):
            self.calls = 0

        def invoke(self, request):
            self.calls += 1
            if self.calls == 1:
                return CapabilityResponse(
                    task_id=request.task_id,
                    capability_id=request.capability_id,
                    status="clarification_required",
                    clarification_questions=["Confirm owner", "Confirm schedule"],
                )
            return artifact_worker.invoke(request)

    worker = Worker()
    runtime.registry.register("BRD_GENERATOR", worker)
    result = runtime.orchestrator.run("p", "BRD", task_id="multi-question")
    questions = result["state"].open_clarifications
    runtime.orchestrator.clarifications.answer(
        runtime.orchestrator, "p", questions[0].clarification_id, "Logistics"
    )
    assert worker.calls == 1
    assert runtime.orchestrator.checkpoint_snapshot("p", "multi-question")["next"] == ("await_input",)
    runtime.orchestrator.clarifications.answer(
        runtime.orchestrator, "p", questions[1].clarification_id, "Daily"
    )
    assert worker.calls == 2
    assert runtime.storage.load_state("p").task_status == "awaiting_approval"
    assert runtime.storage.load_artifact("p", "BRD").content


def test_checkpoint_acknowledgement_failure_does_not_undo_committed_approval(tmp_path, monkeypatch):
    runtime = build(tmp_path, "langgraph")
    runtime.orchestrator.run("p", "BRD", task_id="review-task")
    # Simulate a pre-update approval wait. New generations finish immediately.
    from backend.app.langgraph_orchestrator import Invocation

    with runtime.orchestrator._graph() as graph:
        config = runtime.orchestrator._config("p", "review-task")
        graph.update_state(
            config, {"wait_reason": "approval", "next_step": "await_approval"}, as_node="persist_and_continue"
        )
        graph.invoke(None, config, context=Invocation(state=runtime.storage.load_state("p")))

    def fail(*args):
        raise OSError("simulated checkpoint failure")

    monkeypatch.setattr(runtime.orchestrator, "resume_approval", fail)
    runtime.approvals.review("p", "BRD", "1", True)
    assert runtime.storage.load_artifact("p", "BRD", "1").approval_status == "approved"
    assert runtime.orchestrator.checkpoint_snapshot("p", "review-task")["next"] == ("await_approval",)
    reopened = build(tmp_path, "langgraph")
    reopened.orchestrator.run("p", "FRD", task_id="next-task")
    assert reopened.orchestrator.checkpoint_snapshot("p", "review-task")["next"] == ()
    assert len([r for r in reopened.storage.list_artifacts("p") if r.artifact_type == "BRD"]) == 1


def test_runtime_cursor_cannot_override_authoritative_artifact_selection(tmp_path):
    runtime = build(tmp_path, "langgraph", "STO delivery when material available")
    result = runtime.orchestrator.run("p", "FRD", task_id="domain-authority")
    with runtime.orchestrator._graph() as graph:
        graph.update_state(runtime.orchestrator._config("p", "domain-authority"), {"artifact_type": "ABAP"})
    resumed = runtime.orchestrator.clarifications.answer(
        runtime.orchestrator,
        "p",
        result["state"].open_clarifications[-1].clarification_id,
        "Unrestricted stock",
    )
    assert resumed["artifact"].artifact_type == "FRD"
    assert runtime.abap.invocations == []


def test_conversation_uses_graph_without_persisting_a_second_memory_store(tmp_path):
    runtime = build(tmp_path, "langgraph", "PRIVATE_CONVERSATION_CONTEXT")
    before = runtime.storage.load_state("p")
    result = runtime.orchestrator.converse("p", "What can you help me with?", task_id="chat-no-checkpoint")
    assert result["origin"] == "model"
    assert runtime.storage.load_state("p") == before
    assert not (tmp_path / "runtime/langgraph/checkpoints.sqlite").exists()
    assert runtime.gateway.fake.calls[0].task_id == "chat-no-checkpoint"
