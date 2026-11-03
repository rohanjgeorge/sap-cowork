"""Worker, research and audit boundaries from the capability specification."""

from backend.app.artifact_profiles import load_profile
from backend.app.capabilities import CapabilityRegistry
from backend.app.models import (
    CapabilityRequest,
    CapabilityResponse,
    ContextItem,
    ContextRequirement,
    ModelResponse,
)
from backend.app.runtime import Runtime


class ResearchAdapter:
    adapter_id = "permitted-research"
    category = "SRC-05"
    research = True
    parallel_safe = False

    def __init__(self):
        from backend.app.models import SourceCategory

        self.category = SourceCategory.SAP_STANDARD
        self.calls = []
        self.allowed = True

    def authorized(self, project, user):
        return self.allowed and user == "local"

    def discover(self, project, requirements):
        return [{"object_id": name, "independent": False} for name in ("reference-a", "reference-b")]

    def retrieve(self, project, action, *, timeout_seconds):
        self.calls.append(action["object_id"])
        return [
            ContextItem(
                content="STO reference evidence for qualified design",
                source="sap:" + action["object_id"],
                source_type="research",
                source_category="SRC-05",
                domain="SAP_TECHNICAL",
                evidence_status="supported",
                authority="official_standard",
            )
        ]


def test_profiles_drive_one_shared_worker_and_preserve_classification(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    for kind in ("BRD", "FRD", "USER_STORIES", "TDD", "SIT", "UAT", "AUDIT_REPORT"):
        profile = load_profile(kind)
        assert profile.version == "1.0" and profile.context_requirement_profile.endswith("#" + kind)
        assert profile.generation_instructions and profile.validation_profile
    for capability in (
        "BRD_GENERATOR",
        "FRD_GENERATOR",
        "USER_STORIES_GENERATOR",
        "TDD_GENERATOR",
        "SIT_GENERATOR",
        "UAT_GENERATOR",
    ):
        assert runtime.registry._implementations[capability].worker is runtime.worker
    catalog = {r["capability_id"]: r["kind"] for r in runtime.registry.describe()}
    assert catalog["AUDIT_WORKER"] == "subgraph" and catalog["RESEARCH"] == "subgraph_agentic"
    assert catalog["ABAP_GENERATOR"] == "external_module" and catalog["SAP_LOOKUP"] == "tool_adapter"
    result = runtime.orchestrator.run("p", "BRD")
    assert result["artifact"].task_profile_version == "1.0"
    assert result["artifact"].task_profile_ref == "artifact_profiles/v1.json#BRD"
    assert runtime.gateway.fake.calls[-1].context["task_profile"]["artifact_type"] == "BRD"


def test_worker_question_becomes_unmet_context_and_native_planner_interrupt(storage, tmp_path, monkeypatch):
    runtime = Runtime(storage, tmp_path)
    original = runtime.gateway.fake.complete
    answered = []

    def complete(request):
        if request.context.get("template") and not answered:
            answered.append(True)
            return ModelResponse(
                status="success",
                provider="fake",
                model="deterministic-v1",
                structured_output={
                    "content": "",
                    "clarification_questions": ["Who owns the exception report?"],
                    "unmet_context_requirements": [],
                },
            )
        return original(request)

    monkeypatch.setattr(runtime.gateway.fake, "complete", complete)
    paused = runtime.orchestrator.run("p", "BRD", task_id="worker-question")
    assert paused["state"].task_status == "awaiting_input"
    assert runtime.orchestrator.checkpoint_snapshot("p", "worker-question")["next"] == ("plan_context",)
    assert storage.list_artifacts("p") == []
    resumed = runtime.orchestrator.clarifications.answer(
        runtime.orchestrator,
        "p",
        paused["state"].clarifications[-1].clarification_id,
        "The logistics lead owns exception reporting.",
    )
    assert resumed["artifact"].artifact_type == "BRD"


def research_setup(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    adapter = ResearchAdapter()
    runtime.context_sources.register(adapter)
    actions, _ = runtime.context_sources.discover(
        storage.load_project("p"),
        [
            ContextRequirement(
                requirement_id="sap",
                description="Find STO evidence",
                domain="SAP_TECHNICAL",
                query="STO",
                source_categories=["SRC-05"],
            )
        ],
    )
    return runtime, adapter, actions


def test_research_iterates_over_permitted_tools_and_qualifies_findings(storage, tmp_path):
    runtime, adapter, actions = research_setup(storage, tmp_path)
    before = storage.load_state("p")
    result = runtime.research.run(
        storage.load_project("p"),
        "research",
        [
            ContextRequirement(
                requirement_id="sap", description="STO references", domain="SAP_TECHNICAL", query="STO"
            )
        ],
        actions,
    )
    assert adapter.calls == ["reference-a", "reference-b"]
    assert result["attempts"] == result["model_calls"] == 2 and len(result["evidence"]) == 2
    assert result["publication"] == "not_requested" and result["qualifications"]
    assert storage.load_state("p") == before and storage.list_artifacts("p") == []


def test_research_cannot_invent_tools_or_bypass_budget(storage, tmp_path, monkeypatch):
    runtime, adapter, actions = research_setup(storage, tmp_path)
    monkeypatch.setattr(
        runtime.gateway.fake,
        "complete",
        lambda request: ModelResponse(
            status="success",
            provider="fake",
            model="demo",
            structured_output={"action_id": "unrestricted-web", "stop": False},
        ),
    )
    result = runtime.research.run(storage.load_project("p"), "invalid-selection", [], actions)
    assert adapter.calls == [] and result["evidence"] == []
    assert any("unauthorized" in q for q in result["qualifications"])
    runtime, adapter, actions = research_setup(storage, tmp_path)
    result = runtime.research.run(storage.load_project("p"), "zero-budget", [], actions, max_attempts=0)
    assert result["model_calls"] == 0 and adapter.calls == []


def test_research_rechecks_authorization_after_model_selection(storage, tmp_path, monkeypatch):
    runtime, adapter, actions = research_setup(storage, tmp_path)
    original = runtime.gateway.fake.complete

    def revoke(request):
        decision = original(request)
        adapter.allowed = False
        return decision

    monkeypatch.setattr(runtime.gateway.fake, "complete", revoke)
    result = runtime.research.run(storage.load_project("p"), "revoked", [], actions)
    assert result["evidence"] == [] and adapter.calls == []
    assert any(f["reason"] == "inaccessible" for f in result["failures"])


def test_context_planning_invokes_research_subgraph_within_limits(storage, tmp_path):
    runtime, adapter, _ = research_setup(storage, tmp_path)
    result = runtime.orchestrator.run("p", "TDD")
    record = storage.load_context_run("p", result["artifact"].context_plan_ref)
    assert record["research_result"]["attempts"] <= runtime.context_planning.budget.max_attempts
    assert adapter.calls and any(
        i["source"].startswith("sap:reference") for i in result["artifact"].evidence_provenance
    )
    assert runtime.orchestrator.checkpoint_snapshot("p", result["artifact"].source_task_id)["next"] == ()


def test_audit_aggregates_findings_without_accepting_code_or_running_sap(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    runtime.orchestrator.run("p", "TDD")
    runtime.orchestrator.run("p", "ABAP")
    before = storage.load_state("p")
    result = runtime.orchestrator.run("p", "AUDIT_REPORT")
    assert result["artifact"].approval_status == "draft"
    assert "INCOMPLETE_IMPLEMENTATION" in result["artifact"].content
    assert "STATIC_ANALYZER_NOT_CONFIGURED" in result["artifact"].content
    assert "RUNTIME_CHECKS_NOT_RUN" in result["artifact"].content
    assert any(f["code"] == "RUNTIME_CHECKS_NOT_RUN" for f in result["artifact"].validation_findings)
    assert result["telemetry"]["sap_execution"] is False and result["warnings"]
    assert storage.load_state("p").confirmations == before.confirmations
    assert storage.load_state("p").current_approved_stage == before.current_approved_stage
    model_call = next(call for call in reversed(runtime.gateway.fake.calls) if call.context.get("template"))
    assert "INCOMPLETE_IMPLEMENTATION" in model_call.context["revision_instructions"]


def test_capability_snapshot_cannot_mutate_parent_state_and_correlates_request(storage):
    import pytest

    registry = CapabilityRegistry()
    state = storage.load_state("p")

    class MutatingWorker:
        def invoke(self, request):
            with pytest.raises(ValueError):
                request.state.requirement = "Worker changed local snapshot"
            return CapabilityResponse(
                task_id=request.task_id, capability_id=request.capability_id, status="success"
            )

    registry.register("BRD_GENERATOR", MutatingWorker())
    result = registry.invoke(
        "BRD_GENERATOR",
        CapabilityRequest(
            request_id="request", project_id="p", task_id="task", capability_id="BRD_GENERATOR", state=state
        ),
    )
    assert result.request_id == "request"
    assert state.requirement == storage.load_state("p").requirement == "Automate STO deliveries"
