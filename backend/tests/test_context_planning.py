from threading import Barrier
from time import monotonic, sleep

from backend.app.context_planning import items, merge_refs, plan_id
from backend.app.model_gateway import estimate_tokens
from backend.app.models import (
    CapabilityResponse,
    ContextBudget,
    ContextItem,
    ContextPackage,
    ContextRequirement,
    SourceCategory as S,
    now,
)
from backend.app.runtime import Runtime


def test_subgraph_returns_profile_plus_reasoned_needs_and_traceable_bounded_package(storage, tmp_path):
    storage.save_context(
        "p",
        ContextPackage(
            project_id="p",
            task_id="source",
            sap_technical_context=[
                ContextItem(
                    content="STO release reference. " * 8000,
                    source="original:sap-reference",
                    source_type="curated",
                    original_uri="https://help.sap.com/example",
                    source_version="2023",
                    authority="official_standard",
                    evidence_status="verified",
                    observed_at=now(),
                    applicability={"release": "2023"},
                )
            ],
        ),
    )
    runtime = Runtime(storage, tmp_path)
    result = runtime.orchestrator.run("p", "TDD", task_id="planned")
    artifact = result["artifact"]
    assert artifact.context_package_ref and artifact.evidence_provenance
    record = storage.load_context_run("p", artifact.context_plan_ref)
    assert record["plan"]["profile_version"] == "1.0"
    assert any(r["requirement_id"].startswith("reasoned.") for r in record["plan"]["requirements"])
    package = ContextPackage.model_validate(record["package"])
    assert estimate_tokens(package.model_dump(mode="json")) <= runtime.context_planning.budget.max_tokens
    assert all(len(item.content) <= 1800 for item in items(package))
    assert all(p["original_uri"] and p["source_id"] for p in artifact.evidence_provenance)
    assert record["plan"]["reasoning_status"] == "model"
    assert runtime.context_sources.adapters == {}


class LiveTestAdapter:
    adapter_id = "test-live"
    category = S.CONNECTED_SYSTEM
    parallel_safe = True

    def __init__(self, barrier=None, targeted=False):
        self.barrier, self.targeted, self.calls = barrier, targeted, []

    def authorized(self, project, user):
        return user == "local"

    def discover(self, project, requirements):
        if self.targeted and not any(r.query == "ZCL_NEW" for r in requirements):
            return []
        return [
            {"object_id": "ZCL_NEW", "part": index, "independent": True}
            for index in range(2 if self.barrier else 1)
        ]

    def retrieve(self, project, action, *, timeout_seconds):
        self.calls.append(action)
        if self.barrier:
            self.barrier.wait(timeout=3)
        return [
            ContextItem(
                content="ZCL_NEW implements the customer STO extension",
                source="test-system:ZCL_NEW",
                source_type="connector",
                source_category=S.CONNECTED_SYSTEM,
                domain="SAP_TECHNICAL",
                source_version="42",
                authority="target_system",
                evidence_status="verified",
                observed_at=now(),
                object_id="ZCL_NEW",
                applicability={"system": "S4P", "release": "2023"},
            )
        ]


def test_independent_lookups_run_in_parallel_and_merge_stable_evidence(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    adapter = LiveTestAdapter(Barrier(2))
    runtime.context_sources.register(
        adapter,
        target_binding={
            "project_id": "p",
            "applicability": {
                "product": "S4",
                "deployment": "on-premise",
                "release": "2023",
                "system": "S4P",
            },
        },
    )
    artifact = runtime.orchestrator.run("p", "TDD")["artifact"]
    record = storage.load_context_run("p", artifact.context_plan_ref)
    assert len(adapter.calls) == 2
    assert len([raw for raw in record["evidence"] if raw["source"] == "test-system:ZCL_NEW"]) == 1
    assert record["plan"]["coverage"]["sap.release"] == "satisfied"
    assert merge_refs(["b", "a"], ["a", "c"]) == ["a", "b", "c"]


def test_native_subgraph_interrupt_resumes_after_restart_without_repeating_reasoning(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    state = storage.load_state("p")
    state.requirement = "STO when material available"
    storage.save_state("p", state)
    paused = runtime.orchestrator.run("p", "FRD", task_id="resume-context")
    assert paused["state"].task_status == "awaiting_input"
    ref = plan_id("p", "resume-context")
    assert storage.load_context_run("p", ref)["plan"]["outcome"] == "awaiting_input"
    with runtime.orchestrator._graph() as graph:
        snapshot = graph.get_state(runtime.orchestrator._config("p", "resume-context"), subgraphs=True)
        assert snapshot.tasks[0].state is not None
    reopened = Runtime(storage, tmp_path)
    answer = reopened.orchestrator.clarifications.answer(
        reopened.orchestrator,
        "p",
        paused["state"].clarifications[-1].clarification_id,
        "Unrestricted stock; no partial delivery",
    )
    assert answer["artifact"].artifact_type == "FRD"
    assert storage.load_context_run("p", ref)["plan"]["model_calls"] == 1
    assert all((r.context or {}).get("operation") != "context_planning" for r in reopened.gateway.fake.calls)


def test_worker_unmet_requirement_triggers_targeted_replan_with_no_partial_artifact(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    adapter = LiveTestAdapter(targeted=True)
    runtime.context_sources.register(
        adapter,
        target_binding={
            "project_id": "p",
            "applicability": {
                "product": "S4",
                "deployment": "on-premise",
                "release": "2023",
                "system": "S4P",
            },
        },
    )
    original = runtime.registry._implementations["TDD_GENERATOR"]

    class Worker:
        calls = 0

        def invoke(self, request):
            self.calls += 1
            if self.calls == 1:
                assert storage.list_artifacts("p") == []
                return CapabilityResponse(
                    task_id=request.task_id,
                    capability_id=request.capability_id,
                    status="context_required",
                    unmet_context_requirements=[
                        ContextRequirement(
                            requirement_id="custom.object",
                            description="Verify the newly discovered custom class",
                            domain="SAP_TECHNICAL",
                            query="ZCL_NEW",
                            source_categories=[S.CONNECTED_SYSTEM],
                            material=True,
                            requires_verification=True,
                            claim="target_implementation",
                        )
                    ],
                )
            assert any("ZCL_NEW" in item.content for item in items(request.context))
            return original.invoke(request)

    worker = Worker()
    runtime.registry.register("TDD_GENERATOR", worker)
    result = runtime.orchestrator.run("p", "TDD", task_id="targeted")
    assert result["artifact"] and worker.calls == 2
    assert len(adapter.calls) == 1
    assert runtime.orchestrator.context_handler.requests[-1].required_domains == ["SAP_TECHNICAL"]
    assert storage.load_context_run("p", result["artifact"].context_plan_ref)["plan"]["cycle"] == 1
    assert len(storage.list_artifacts("p")) == 1


def test_replan_cycles_have_a_terminal_limit(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)

    class Worker:
        calls = 0

        def invoke(self, request):
            self.calls += 1
            return CapabilityResponse(
                task_id=request.task_id,
                capability_id=request.capability_id,
                status="context_required",
                unmet_context_requirements=[
                    ContextRequirement(
                        requirement_id="still.missing",
                        description="Optional reference",
                        domain="SAP_TECHNICAL",
                    )
                ],
            )

    worker = Worker()
    runtime.registry.register("TDD_GENERATOR", worker)
    result = runtime.orchestrator.run("p", "TDD")
    assert "replanning limit" in result["error"]
    assert worker.calls == 3 and storage.list_artifacts("p") == []


def test_unavailable_authoritative_source_cannot_be_replaced_by_cached_guidance(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)

    class Worker:
        calls = 0

        def invoke(self, request):
            self.calls += 1
            return CapabilityResponse(
                task_id=request.task_id,
                capability_id=request.capability_id,
                status="context_required",
                unmet_context_requirements=[
                    ContextRequirement(
                        requirement_id="verify.custom",
                        description="Confirm custom object in target system",
                        domain="SAP_TECHNICAL",
                        query="ZCL_NEW",
                        source_categories=[S.CONNECTED_SYSTEM],
                        requires_verification=True,
                        material=True,
                        claim="target_implementation",
                    )
                ],
            )

    worker = Worker()
    runtime.registry.register("TDD_GENERATOR", worker)
    storage.save_context(
        "p",
        ContextPackage(
            project_id="p",
            task_id="legacy",
            sap_technical_context=[
                ContextItem(
                    content="ZCL_NEW may exist",
                    source="guide.md",
                    source_type="curated",
                    evidence_status="verified",
                    authority="official_standard",
                )
            ],
        ),
    )
    result = runtime.orchestrator.run("p", "TDD")
    assert "could not be verified" in result["error"]
    assert worker.calls == 1 and storage.list_artifacts("p") == []


def test_adapter_deadline_is_bounded_and_missing_context_remains_qualified(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    runtime.context_planning.budget = ContextBudget(max_seconds=0.05)

    class Slow(LiveTestAdapter):
        def retrieve(self, project, action, *, timeout_seconds):
            sleep(0.25)
            return []

    runtime.context_sources.register(Slow())
    started = monotonic()
    result = runtime.orchestrator.run("p", "TDD")
    assert result["artifact"] and monotonic() - started < 5
    assert any(g.gap_type == "budget" for g in result["artifact"].context_gaps)
