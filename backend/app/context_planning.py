"""Dedicated, checkpoint-inheriting LangGraph for task evidence planning.

Only references and bounded counters are graph channels. Plans, selected excerpts,
gap reports and packages are durable project resources behind StorageProvider.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from time import monotonic
from typing import Annotated, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from .context_domains import DOMAIN_FIELDS
from .context_sources import KnowledgeCopies, evidence_id, identity, permitted, qualify, references_allowed
from .model_gateway import estimate_tokens
from .models import (
    ContextBudget,
    ContextGap,
    ContextItem,
    ContextPackage,
    ContextPlan,
    ContextRequirement,
    ContextRequest,
    ProjectState,
    SourceCategory as S,
    now,
)
from .templates import TemplateRepository


def merge_refs(left, right):
    return sorted(set(left or []) | set(right or []))


class PlanningCursor(TypedDict, total=False):
    project_id: str
    task_id: str
    plan_ref: str
    package_ref: str | None
    cycle: int
    requirement_refs: Annotated[list[str], merge_refs]
    evidence_refs: Annotated[list[str], merge_refs]
    source_refs: Annotated[list[str], merge_refs]
    attempts: int
    actions_used: int
    next_step: str


@dataclass
class PlanningInvocation:
    state: ProjectState
    artifact_type: str
    on_pause: Callable
    on_resume: Callable
    parent: object
    on_prepared: Callable | None = None


def plan_id(project_id, task_id, cycle=0):
    return sha256(f"{project_id}:{task_id}:{cycle}".encode()).hexdigest()


def items(package):
    found = {}
    for field in DOMAIN_FIELDS.values():
        for item in getattr(package, field):
            found.setdefault(evidence_id(item), item)
    return [found[key] for key in sorted(found)]


def excerpt(content, requirements, limit=1800):
    if len(content) <= limit:
        return content
    queries = {word.lower() for req in requirements for word in re.findall(r"[A-Za-z0-9_]{3,}", req.query)}
    paragraphs = content.split("\n\n")
    ranked = sorted(
        enumerate(paragraphs), key=lambda pair: (-sum(w in pair[1].lower() for w in queries), pair[0])
    )
    selected, remaining = [], limit
    for index, paragraph in ranked:
        if remaining <= 20:
            break
        selected.append((index, paragraph[:remaining]))
        remaining -= len(paragraph[:remaining]) + 2
    return "\n\n".join(text for _, text in sorted(selected))


class ContextPlanningService:
    def __init__(self, storage, planner, handler, sources, gateway=None, budget=None):
        self.storage, self.planner, self.handler = storage, planner, handler
        self.sources, self.gateway = sources, gateway
        self.budget = budget or ContextBudget()
        self.copies = KnowledgeCopies(storage)
        self.research = None
        graph = StateGraph(PlanningCursor, context_schema=PlanningInvocation)
        for name, function in {
            "define_requirements": self.define_requirements,
            "discover_sources": self.discover_sources,
            "plan_retrieval": self.plan_retrieval,
            "retrieve_context": self.retrieve_context,
            "evaluate_context": self.evaluate_context,
            "route_gaps": self.route_gaps,
            "prepare_clarification": self.prepare_clarification,
            "request_clarification": self.request_clarification,
            "resume_planning": self.resume_planning,
            "research_context": self.research_context,
            "assemble_context": self.assemble_context,
            "return_context": self.return_context,
        }.items():
            graph.add_node(name, function)
        graph.add_edge(START, "define_requirements")
        graph.add_edge("define_requirements", "discover_sources")
        graph.add_edge("discover_sources", "plan_retrieval")
        graph.add_edge("plan_retrieval", "retrieve_context")
        graph.add_edge("retrieve_context", "evaluate_context")
        graph.add_edge("evaluate_context", "route_gaps")
        graph.add_conditional_edges(
            "route_gaps",
            lambda state: state["next_step"],
            {
                "retrieve": "retrieve_context",
                "research": "research_context",
                "clarify": "prepare_clarification",
                "continue": "assemble_context",
                "escalate": "assemble_context",
            },
        )
        graph.add_edge("research_context", "evaluate_context")
        graph.add_conditional_edges(
            "prepare_clarification",
            lambda state: state.get("next_step"),
            {"context_budget_exceeded": END, "clarify": "request_clarification"},
        )
        graph.add_edge("request_clarification", "resume_planning")
        graph.add_edge("resume_planning", "plan_retrieval")
        graph.add_edge("assemble_context", "return_context")
        graph.add_edge("return_context", END)
        self.graph = graph.compile()  # Inherits the parent checkpointer/namespace.

    def read(self, cursor):
        record = self.storage.load_context_run(cursor["project_id"], cursor["plan_ref"])
        return ContextPlan.model_validate(record["plan"]), record

    def save(self, plan, record):
        if record.get("evidence"):
            candidates = [ContextItem.model_validate(raw) for raw in record["evidence"]]
            candidates.sort(
                key=lambda item: (item.source_type not in ("user", "artifact"), evidence_id(item))
            )
            if len(candidates) > 32:
                record["candidate_limit_reached"] = True
            record["evidence"] = [
                item.model_copy(
                    update={"content": excerpt(item.content, plan.requirements, 6000)}
                ).model_dump(mode="json")
                for item in candidates[:32]
            ]
        record["plan"] = plan.model_dump(mode="json")
        with self.storage.transaction(plan.project_id):
            self.storage.save_context_run(plan.project_id, plan.plan_id, record)

    def seed_replan(self, state, artifact_type, cycle, requirements, previous):
        ref = plan_id(state.project_id, state.active_task_id, cycle)
        normalized = []
        for requirement in requirements[:8]:
            value = requirement.model_dump(mode="json")
            value["requirement_id"] = (
                "worker." + sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:20]
            )
            normalized.append(value)
        with self.storage.transaction(state.project_id):
            self.storage.save_context_run(
                state.project_id,
                ref,
                {
                    "kind": "context_seed",
                    "additional": normalized,
                    "previous_package": previous.model_dump(mode="json"),
                    "artifact_type": str(artifact_type),
                },
            )
        return ref

    def define_requirements(self, cursor, runtime: Runtime[PlanningInvocation]):
        ctx = runtime.context
        try:
            record = self.storage.load_context_run(ctx.state.project_id, cursor["plan_ref"])
            if record.get("kind") == "context_plan":
                plan = ContextPlan.model_validate(record["plan"])
                return {"requirement_refs": [r.requirement_id for r in plan.requirements]}
        except FileNotFoundError:
            record = {}
        version, fixed = self.planner.requirements(ctx.state, ctx.artifact_type)
        plan = ContextPlan(
            plan_id=cursor["plan_ref"],
            project_id=ctx.state.project_id,
            task_id=ctx.state.active_task_id,
            stage=ctx.state.current_stage,
            artifact_type=ctx.artifact_type,
            profile_version=version,
            requirements=fixed,
            constraints=self.budget.model_copy(),
            cycle=cursor.get("cycle", 0),
            as_of=ctx.state.task_inputs.get("as_of")
            or self.storage.load_project(ctx.state.project_id).context_date
            or now(),
        )
        if ctx.artifact_type == "FRD" and any(
            word in ctx.state.requirement.lower() for word in ("material available", "material availability")
        ):
            plan.requirements.append(
                ContextRequirement(
                    requirement_id="project.material_availability",
                    description="Material availability definition",
                    domain="SAP_FUNCTIONAL",
                    query="availability",
                    source_categories=[S.CONVERSATION, S.UPLOAD, S.ARTIFACT, S.ORGANIZATION, S.SAP_STANDARD],
                )
            )
        if self.gateway:
            profile = self.gateway.settings.current(ctx.state.task_inputs.get("model_policy")).capabilities
            plan.constraints.max_tokens = max(
                1000, min(plan.constraints.max_tokens, int(profile.context_window * 0.5))
            )
        if record.get("additional"):
            previous_package = ContextPackage.model_validate(record["previous_package"])
            if previous_package.plan_ref:
                previous_plan = ContextPlan.model_validate(
                    self.storage.load_context_run(plan.project_id, previous_package.plan_ref)["plan"]
                )
                plan.profile_version = previous_plan.profile_version
                plan.requirements = previous_plan.requirements
            incoming = [ContextRequirement.model_validate(r) for r in record["additional"]]
            plan.targeted_requirements = [r.requirement_id for r in incoming]
            plan.requirements = list({r.requirement_id: r for r in plan.requirements + incoming}.values())
            plan.reasoning_status = "targeted_worker_replan"
        elif plan.constraints.max_model_calls and self.gateway:
            started = monotonic()
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(
                self.planner.reason,
                ctx.state,
                ctx.artifact_type,
                self.gateway,
                timeout_seconds=plan.constraints.max_seconds,
            )
            try:
                extra, status = future.result(timeout=plan.constraints.max_seconds)
                plan.requirements += extra
                plan.reasoning_status = status
            except Exception:
                plan.reasoning_status = "unavailable; fixed profile retained"
            finally:
                plan.model_calls = 1
                plan.elapsed_seconds += monotonic() - started
                pool.shutdown(wait=False, cancel_futures=True)
        if ctx.artifact_type != "ABAP":
            template, ref = TemplateRepository().load(ctx.artifact_type)
            plan.template_ref, plan.template_digest = ref, sha256(template.encode()).hexdigest()
        self.save(
            plan, {**record, "kind": "context_plan", "evidence": [], "failures": [], "used_actions": []}
        )
        return {
            "requirement_refs": [r.requirement_id for r in plan.requirements],
            "attempts": 0,
            "actions_used": 0,
        }

    def _request(self, ctx, plan, targeted=False):
        request = self.planner.plan(ctx.state, ctx.artifact_type)
        if targeted:
            request.required_domains = list(
                dict.fromkeys(
                    r.domain for r in plan.requirements if r.requirement_id in plan.targeted_requirements
                )
            )
            request.upstream_artifacts = []
        else:
            request.upstream_artifacts = list(
                dict.fromkeys(
                    request.upstream_artifacts
                    + [
                        r.query
                        for r in plan.requirements
                        if r.requirement_id.startswith("artifact.")
                        and r.query in {ref.artifact_id for ref in ctx.state.artifact_registry}
                    ]
                )
            )[:8]
            request.required_domains = list(
                dict.fromkeys(request.required_domains + [r.domain for r in plan.requirements])
            )
            if not ctx.state.requirement:
                request.upstream_artifacts = list(
                    dict.fromkeys(
                        request.upstream_artifacts
                        + [
                            r.artifact_id
                            for r in ctx.state.artifact_registry
                            if r.artifact_type != ctx.artifact_type
                        ]
                    )
                )[:8]
        return request

    def discover_sources(self, cursor, runtime: Runtime[PlanningInvocation]):
        ctx = runtime.context
        plan, record = self.read(cursor)
        project = self.storage.load_project(plan.project_id)
        request = self._request(ctx, plan, bool(plan.cycle))
        package = self.handler.load(request)
        previous = (
            ContextPackage.model_validate(record["previous_package"])
            if record.get("previous_package")
            else None
        )
        local_items = items(package) + (items(previous) if previous else [])
        record["evidence"] = [item.model_dump(mode="json") for item in local_items]
        record["upstream"] = [
            r.model_dump(mode="json")
            for r in (previous.upstream_artifacts if previous else package.upstream_artifacts)
        ]
        active = (
            [r for r in plan.requirements if r.requirement_id in plan.targeted_requirements]
            if plan.cycle
            else plan.requirements
        )
        started = monotonic()
        actions, failures = self.sources.discover(
            project, active, timeout_seconds=max(0.01, plan.constraints.max_seconds - plan.elapsed_seconds)
        )
        plan.elapsed_seconds += monotonic() - started
        plan.candidate_sources = self.sources.catalog(project)
        record["available_actions"] = actions
        record["retrieval_trace"] = []
        for action in actions:
            ids = action.get("requirement_ids")
            mapped = [
                r.requirement_id
                for r in active
                if (
                    r.requirement_id in ids
                    if ids is not None
                    else action["category"] in r.source_categories
                    and (not action.get("domain") or action["domain"] == str(r.domain))
                )
            ]
            record["retrieval_trace"].append(
                {
                    "action_ref": sha256(json.dumps(action, sort_keys=True).encode()).hexdigest(),
                    "source": action["adapter_id"],
                    "requirement_ids": mapped,
                    "executed": False,
                    "status": "planned",
                    "evidence_refs": [],
                    "failures": [],
                }
            )
        record["failures"] = failures
        self.save(plan, record)
        return {"source_refs": [sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() for a in actions]}

    def plan_retrieval(self, cursor, runtime: Runtime[PlanningInvocation]):
        plan, record = self.read(cursor)
        remaining = max(0, plan.constraints.max_actions - plan.actions_used)
        plan.retrieval_actions = record.get("available_actions", [])[:remaining]
        self.save(plan, record)
        return {}

    def _retrieve(self, cursor, ctx, research=False):
        plan, record = self.read(cursor)
        remaining_time = plan.constraints.max_seconds - plan.elapsed_seconds
        actions = [
            a
            for a in plan.retrieval_actions
            if bool(a.get("research")) == research
            and sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() not in record["used_actions"]
        ]
        actions = actions[: max(0, plan.constraints.max_actions - plan.actions_used)]
        if remaining_time > 0 and actions:
            started = monotonic()
            attempts_used = 1
            if research and self.research:
                gaps = {g.requirement_id for g in plan.gaps}
                researched = self.research.run(
                    self.storage.load_project(plan.project_id),
                    plan.task_id,
                    [r for r in plan.requirements if r.requirement_id in gaps],
                    actions,
                    max_attempts=max(0, plan.constraints.max_attempts - plan.attempts),
                    max_actions=max(0, plan.constraints.max_actions - plan.actions_used),
                    max_seconds=remaining_time,
                    max_tokens=plan.constraints.max_tokens,
                    policy=ctx.state.task_inputs.get("model_policy", "user_default"),
                )
                record["research_result"] = researched
                retrieved = [ContextItem.model_validate(raw) for raw in researched["evidence"]]
                failures = researched["failures"]
                actions = researched["attempted_actions"]
                attempts_used = max(1, researched["attempts"])
                if not actions:
                    # No authorized selection or explicit stop: do not loop over
                    # the same actions indefinitely after a model refusal/failure.
                    record["used_actions"] += [
                        sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()
                        for a in plan.retrieval_actions
                        if a.get("research")
                    ]
            else:
                retrieved, failures = self.sources.retrieve(
                    self.storage.load_project(plan.project_id), actions, timeout_seconds=remaining_time
                )
            plan.elapsed_seconds += monotonic() - started
            plan.actions_used += len(actions)
            plan.attempts += attempts_used
            attempted_refs = {sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() for a in actions}
            for trace in record.get("retrieval_trace", []):
                if trace["action_ref"] not in attempted_refs:
                    continue
                errors = [f for f in failures if f.get("action_ref") == trace["action_ref"]]
                found = [
                    evidence_id(item)
                    for item in retrieved
                    if item.retrieval_action_ref == trace["action_ref"]
                    or trace["action_ref"] in item.retrieval_action_refs
                ]
                trace.update(
                    executed=any(f.get("executed", True) for f in errors) if errors else True,
                    status="failed" if errors else "succeeded" if found else "no_evidence",
                    evidence_refs=sorted(set(trace["evidence_refs"] + found)),
                    failures=errors,
                )
            record["failures"] = [
                f for f in record["failures"] if f.get("action_ref") not in attempted_refs
            ] + failures
            by_id = {evidence_id(ContextItem.model_validate(raw)): raw for raw in record["evidence"]}
            for item in retrieved[:50]:
                if item.domain is None:
                    record["failures"].append({"source": item.adapter_id, "reason": "unavailable"})
                    continue
                qualified = qualify(item, item.domain, plan.project_id)
                if len(qualified.content) > 64000:
                    record["failures"].append({"source": item.adapter_id, "reason": "budget"})
                    continue
                qualified, disposition = self.copies.reconcile(plan.project_id, item.domain.value, qualified)
                if qualified and permitted(qualified, self.storage.load_project(plan.project_id)):
                    by_id[evidence_id(qualified)] = qualified.model_dump(mode="json")
                if disposition in ("review_required", "inaccessible"):
                    record["failures"].append(
                        {
                            "source": item.adapter_id,
                            "reason": "inaccessible" if disposition == "inaccessible" else "conflict",
                        }
                    )
            record["evidence"] = [by_id[key] for key in sorted(by_id)]
            record["used_actions"] += [
                sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() for a in actions
            ]
        self.save(plan, record)
        return {
            "evidence_refs": [evidence_id(ContextItem.model_validate(raw)) for raw in record["evidence"]],
            "attempts": plan.attempts,
            "actions_used": plan.actions_used,
        }

    def retrieve_context(self, cursor, runtime: Runtime[PlanningInvocation]):
        return self._retrieve(cursor, runtime.context)

    def research_context(self, cursor, runtime: Runtime[PlanningInvocation]):
        return self._retrieve(cursor, runtime.context, research=True)

    def evaluate_context(self, cursor, runtime: Runtime[PlanningInvocation]):
        ctx = runtime.context
        plan, record = self.read(cursor)
        project = self.storage.load_project(plan.project_id)
        evidence = [ContextItem.model_validate(raw) for raw in record["evidence"]]
        conflicts = {}
        for item in evidence:
            if not permitted(item, project) or not self._still_authorized(item, project):
                continue
            key = ("source", identity(item), item.source_version)
            conflicts.setdefault(key, []).append(item)
            for fact, value in item.structured_facts.items():
                fact_key = (
                    "fact",
                    item.scope,
                    item.organization_id,
                    str(item.domain),
                    json.dumps(item.applicability, sort_keys=True),
                    fact,
                )
                conflicts.setdefault(fact_key, []).append((item, value))
        for key, group in conflicts.items():
            if key[0] == "fact":
                divergent = len({value for _, value in group}) > 1
                affected = [item for item, _ in group]
            else:
                divergent = (
                    len({item.content_digest or sha256(item.content.encode()).hexdigest() for item in group})
                    > 1
                )
                affected = group
            if divergent:
                for item in affected:
                    item.conflict = (
                        "Contradictory source snapshots or structured facts require reconciliation"
                    )
                    item.evidence_status = "disputed"
        record["evidence"] = [item.model_dump(mode="json") for item in evidence]
        gaps, coverage = [], {}
        failures = record.get("failures", [])
        for requirement in plan.requirements:
            candidates = [
                item
                for item in evidence
                if permitted(item, project)
                and self._still_authorized(item, project)
                and self._matches(requirement, item)
            ]
            status, reason = "satisfied", ""
            if requirement.requirement_id == "application.template":
                candidates = []
                if not plan.template_ref:
                    status, reason = "missing", "Template is unavailable"
            elif not candidates:
                status, reason = "missing", "No applicable permitted evidence found"
            elif any(item.conflict or item.evidence_status == "disputed" for item in candidates):
                status, reason = "conflict", "Retained evidence contains an unresolved discrepancy"
            elif any(self._mismatches(item, project, plan.as_of) for item in candidates):
                candidates = [item for item in candidates if not self._mismatches(item, project, plan.as_of)]
                if not candidates:
                    status, reason = "uncertain", "Evidence is not applicable to the target SAP environment"
            if (
                status == "satisfied"
                and requirement.requirement_id == "sap.release"
                and not any(item.applicability.get("release") for item in candidates)
            ):
                status, reason = "uncertain", "Target SAP release/system applicability is not confirmed"
            if status == "satisfied" and requirement.requires_verification:
                target = self.sources.sap_target(project)
                if not all(target.get(key) for key in ("product", "deployment", "release")):
                    status, reason = (
                        "uncertain",
                        "Target SAP product/deployment/release is not established by project metadata or a trusted scoped connector binding",
                    )
                verified = [
                    item for item in candidates if item.evidence_status == "verified" and item.observed_at
                ]
                if requirement.claim == "target_implementation":
                    verified = [
                        item
                        for item in verified
                        if item.authority == "target_system"
                        and item.source_category == S.CONNECTED_SYSTEM
                        and item.adapter_id in self.sources.adapters
                        and item.applicability.get("system")
                    ]
                elif requirement.claim == "standard_behavior":
                    verified = [item for item in verified if item.authority == "official_standard"]
                if not verified:
                    status, reason = "uncertain", "Cached or secondary knowledge does not verify this claim"
            if status == "satisfied" and any(
                item.observed_at and (now() - item.observed_at).total_seconds() > 30 * 86400
                for item in candidates
            ):
                status, reason = "uncertain", "Evidence freshness exceeds the initial 30-day review threshold"
            if (
                status == "satisfied"
                and requirement.requirement_id.startswith("artifact.")
                and any(item.approval_status != "approved" for item in candidates)
            ):
                status, reason = (
                    "uncertain",
                    "Latest upstream version is not approved; draft generation remains permitted",
                )
            coverage[requirement.requirement_id] = status
            if requirement.user_owned and requirement.material:
                resolved = any(
                    c.status == "resolved" and c.question == requirement.description
                    for c in ctx.state.clarifications
                )
                if not resolved and not any(
                    item.source_type == "artifact" and item.approval_status == "approved"
                    for item in candidates
                ):
                    status, reason = "user_owned", "A material user-owned decision is not yet recorded"
                    coverage[requirement.requirement_id] = status
            if status != "satisfied":
                if requirement.user_owned and requirement.material:
                    resolved = any(
                        c.status == "resolved"
                        and (
                            c.question == requirement.description
                            or c.response
                            and requirement.query
                            and requirement.query.lower() in c.response.lower()
                        )
                        for c in ctx.state.clarifications
                    )
                    if resolved:
                        coverage[requirement.requirement_id] = "satisfied_by_clarification"
                        continue
                    status = "user_owned"
                gaps.append(
                    ContextGap(
                        requirement_id=requirement.requirement_id,
                        gap_type=status,
                        impact="material" if requirement.material else "warning",
                        attempted_sources=sorted(
                            {
                                t["source"]
                                for t in record.get("retrieval_trace", [])
                                if requirement.requirement_id in t["requirement_ids"] and t["executed"]
                            }
                        ),
                        planned_sources=sorted(
                            {
                                t["source"]
                                for t in record.get("retrieval_trace", [])
                                if requirement.requirement_id in t["requirement_ids"]
                            }
                        ),
                        unattempted_sources=sorted(
                            {
                                t["source"]
                                for t in record.get("retrieval_trace", [])
                                if requirement.requirement_id in t["requirement_ids"] and not t["executed"]
                            }
                        ),
                        evidence_refs=sorted(
                            {
                                ref
                                for t in record.get("retrieval_trace", [])
                                if requirement.requirement_id in t["requirement_ids"]
                                for ref in t["evidence_refs"]
                            }
                        ),
                        reason=f"{requirement.description}: {reason}",
                    )
                )
        for failure in failures:
            gap_type = (
                failure["reason"]
                if failure["reason"] in ("inaccessible", "unavailable", "budget", "conflict")
                else "unavailable"
            )
            gaps.append(
                ContextGap(
                    requirement_id="source." + sha256(str(failure["source"]).encode()).hexdigest()[:16],
                    gap_type=gap_type,
                    reason=f"A configured source is {gap_type}",
                    attempted_sources=[str(failure["source"])] if failure.get("executed") else [],
                    planned_sources=[str(failure["source"])],
                    unattempted_sources=[] if failure.get("executed") else [str(failure["source"])],
                )
            )
        if "unavailable" in plan.reasoning_status:
            gaps.append(
                ContextGap(
                    requirement_id="planning.reasoning",
                    gap_type="reasoning_unavailable",
                    reason="Task reasoning unavailable; fixed profile requirements retained",
                )
            )
        plan.gaps, plan.coverage = gaps, coverage
        self.save(plan, record)
        return {}

    def _matches(self, requirement, item):
        if requirement.requirement_id.startswith("artifact."):
            return item.source_type == "artifact" and item.source.lower().startswith(
                f"artifact:{requirement.query.lower()}:"
            )
        if requirement.requirement_id == "project.scope":
            return item.source_type in ("user", "conversation", "upload", "artifact")
        if requirement.requirement_id == "project.decisions":
            return item.source_type == "state"
        if requirement.source_categories and item.source_category not in requirement.source_categories:
            return False
        if requirement.requirement_id == "sap.release":
            return bool(item.applicability.get("release"))
        return item.domain == requirement.domain and (
            not requirement.query
            or requirement.query.lower() in item.content.lower()
            or requirement.requirement_id in ("sap.technical", "historical.related", "organization.standards")
        )

    def _mismatches(self, item, project, as_of=None):
        from datetime import timezone

        def aware(value):
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

        date = aware(as_of or project.context_date or now())
        if (
            item.effective_from
            and date < aware(item.effective_from)
            or item.effective_to
            and date > aware(item.effective_to)
        ):
            return True
        target = self.sources.sap_target(project)
        return any(key in target and target[key] != value for key, value in item.applicability.items())

    def route_gaps(self, cursor, runtime: Runtime[PlanningInvocation]):
        ctx = runtime.context
        plan, record = self.read(cursor)
        questions = (
            ctx.parent.clarification_preflight(ctx.state, ctx.artifact_type)
            if callable(getattr(ctx.parent, "clarification_preflight", None))
            else []
        )
        evidence = [ContextItem.model_validate(raw) for raw in record["evidence"]]
        authorized = [
            i
            for i in evidence
            if permitted(i, self.storage.load_project(plan.project_id))
            and self._still_authorized(i, self.storage.load_project(plan.project_id))
        ]
        if any("availability definition:" in item.content.lower() for item in authorized):
            questions = [q for q in questions if "material availability rule" not in q.lower()]
        if any(item.source_type in ("artifact", "upload") and item.content.strip() for item in authorized):
            questions = [q for q in questions if "provide the requirement" not in q.lower()]
        questions += [
            r.description
            for r in plan.requirements
            if any(g.requirement_id == r.requirement_id and g.gap_type == "user_owned" for g in plan.gaps)
        ]
        if questions:
            record["questions"] = list(dict.fromkeys(questions))
            for question in record["questions"]:
                requirement_id = "clarification." + sha256(question.encode()).hexdigest()[:20]
                if not any(r.description == question for r in plan.requirements):
                    plan.requirements.append(
                        ContextRequirement(
                            requirement_id=requirement_id,
                            description=question,
                            domain="BUSINESS",
                            user_owned=True,
                            material=True,
                        )
                    )
                    plan.gaps.append(
                        ContextGap(
                            requirement_id=requirement_id,
                            gap_type="user_owned",
                            impact="material",
                            reason=question,
                            follow_up="Answer the focused clarification",
                        )
                    )
                    plan.coverage[requirement_id] = "user_owned"
            route = "clarify"
        else:
            unused = [
                a
                for a in plan.retrieval_actions
                if sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() not in record["used_actions"]
            ]
            bounded = (
                plan.attempts < plan.constraints.max_attempts
                and plan.actions_used < plan.constraints.max_actions
                and plan.elapsed_seconds < plan.constraints.max_seconds
            )
            if plan.gaps and unused and bounded:
                route = "research" if all(a.get("research") for a in unused) else "retrieve"
            elif (
                plan.gaps
                and bounded
                and any(f.get("action_ref") and f["reason"] == "unavailable" for f in record["failures"])
            ):
                retry = {
                    f["action_ref"]
                    for f in record["failures"]
                    if f.get("action_ref") and f["reason"] == "unavailable"
                }
                record["used_actions"] = [ref for ref in record["used_actions"] if ref not in retry]
                retry_actions = [
                    a
                    for a in plan.retrieval_actions
                    if sha256(json.dumps(a, sort_keys=True).encode()).hexdigest() in retry
                ]
                route = (
                    "research"
                    if retry_actions and all(a.get("research") for a in retry_actions)
                    else "retrieve"
                )
            elif any(g.impact == "material" and g.gap_type != "user_owned" for g in plan.gaps):
                route = "escalate"
                plan.outcome = "escalated"
            else:
                route = "continue"
        self.save(plan, record)
        return {"next_step": route, "requirement_refs": [r.requirement_id for r in plan.requirements]}

    def prepare_clarification(self, cursor, runtime: Runtime[PlanningInvocation]):
        plan, record = self.read(cursor)
        result = runtime.context.on_pause(record["questions"])
        runtime.context.parent.output = result
        plan.outcome = "awaiting_input"
        self.save(plan, record)
        prepared = self.assemble_context(cursor, runtime)
        self.return_context(cursor, runtime)
        if runtime.context.on_prepared and runtime.context.parent.context:
            runtime.context.on_prepared(runtime.context.parent.context)
        return {
            "package_ref": prepared["package_ref"],
            "next_step": "context_budget_exceeded"
            if runtime.context.parent.output
            and runtime.context.parent.output.get("error_code") == "context_budget_exceeded"
            else "clarify",
        }

    def request_clarification(self, cursor, runtime: Runtime[PlanningInvocation]):
        # No project writes in an interrupt node: it restarts on resume.
        interrupt(
            {
                "reason": "context_clarification",
                "project_id": cursor["project_id"],
                "task_id": cursor["task_id"],
                "plan_ref": cursor["plan_ref"],
            }
        )
        return {}

    def resume_planning(self, cursor, runtime: Runtime[PlanningInvocation]):
        ctx = runtime.context
        if any(
            c.status == "open" and c.task_id == ctx.state.active_task_id for c in ctx.state.clarifications
        ):
            raise ValueError("Answer all material context questions before resuming")
        ctx.on_resume()
        plan, record = self.read(cursor)
        # Reload only the answered business context and authoritative state.
        request = ContextRequest(
            project_id=plan.project_id,
            task_id=plan.task_id,
            current_stage=ctx.state.current_stage,
            current_task=ctx.state.current_task,
            required_domains=["BUSINESS", "FUNCTIONAL_PROCESS", "SDLC"],
        )
        refreshed = items(self.handler.load(request))
        existing = {identity(ContextItem.model_validate(raw)): raw for raw in record["evidence"]}
        for item in refreshed:
            existing[identity(item)] = item.model_dump(mode="json")
        record["evidence"] = list(existing.values())
        plan.outcome = "planning"
        self.save(plan, record)
        return {}

    def assemble_context(self, cursor, runtime: Runtime[PlanningInvocation]):
        plan, record = self.read(cursor)
        project = self.storage.load_project(plan.project_id)
        package = ContextPackage(
            project_id=plan.project_id,
            task_id=plan.task_id,
            package_id=plan.plan_id,
            package_ref=f"context-package:{plan.project_id}:{plan.plan_id}",
            plan_ref=plan.plan_id,
            profile_version=plan.profile_version,
            gaps=[g.model_copy(update={"reason": g.reason[:160]}) for g in plan.gaps[:8]],
            constraints={
                "max_tokens": plan.constraints.max_tokens,
                "outcome": plan.outcome,
                "verification": "Unverified target-system claims must remain qualified",
                "gap_report_ref": plan.plan_id,
            },
            upstream_artifacts=record.get("upstream", []),
        )
        evidence = [ContextItem.model_validate(raw) for raw in record["evidence"]]
        evidence.sort(
            key=lambda item: (
                item.source_type not in ("user", "artifact"),
                item.evidence_status not in ("verified", "supported"),
                evidence_id(item),
            )
        )
        seen, omitted = set(), False
        for item in evidence:
            if not permitted(item, project) or not self._still_authorized(item, project):
                omitted = True
                continue
            if self._mismatches(item, project, plan.as_of):
                omitted = True
                continue
            key = evidence_id(item)
            if key in seen:
                continue
            seen.add(key)
            selected = item.model_copy(update={"content": excerpt(item.content, plan.requirements)})
            field = DOMAIN_FIELDS.get(str(item.domain), "sdlc_context")
            getattr(package, field).append(selected)
            package.evidence_refs.append(key)
            if estimate_tokens(package.model_dump(mode="json")) > plan.constraints.max_tokens - 250:
                getattr(package, field).pop()
                package.evidence_refs.pop()
                omitted = True
            elif selected.evidence_status == "inferred":
                package.assumptions.append(
                    f"Qualified inference from {selected.source}: {selected.content[:200]}"
                )
        if omitted:
            package.gaps.append(
                ContextGap(
                    requirement_id="package.selection",
                    gap_type="budget",
                    reason="Some source passages were omitted by applicability, access or package budget; original sources remain external",
                )
            )
        if plan.outcome not in ("escalated", "awaiting_input"):
            plan.outcome = "qualified" if package.gaps else "ready"
        package.constraints["outcome"] = plan.outcome
        package.constraints["estimated_tokens"] = estimate_tokens(package.model_dump(mode="json"))
        if estimate_tokens(package.model_dump(mode="json")) > plan.constraints.max_tokens:
            # Full detail remains in the external plan. Compact optional prose,
            # never silently discard the gap-report reference or provenance.
            package.gaps = [
                ContextGap(
                    requirement_id="gap_report",
                    gap_type="budget",
                    reason="See referenced Gap Report for unresolved requirements and qualifications.",
                    follow_up="Review Gap Report",
                    qualification="Qualified draft",
                )
            ]
            for field in DOMAIN_FIELDS.values():
                setattr(package, field, [])
            package.evidence_refs = []
            package.assumptions = package.assumptions[:2]
            package.constraints["estimated_tokens"] = 0
            for _ in range(3):
                package.constraints["estimated_tokens"] = estimate_tokens(package.model_dump(mode="json"))
        if estimate_tokens(package.model_dump(mode="json")) > plan.constraints.max_tokens:
            plan.outcome = "context_budget_exceeded"
            record["package"] = None
            record["budget_error"] = {
                "error": "Minimum Context Package exceeds configured budget",
                "error_code": "context_budget_exceeded",
            }
            self.save(plan, record)
            return {"package_ref": None, "next_step": plan.outcome}
        plan.package_ref = package.package_ref
        record["package"] = package.model_dump(mode="json")
        self.save(plan, record)
        return {"package_ref": package.package_ref, "next_step": plan.outcome}

    def _still_authorized(self, item, project):
        if item.domain:
            aliases = {
                "FUNCTIONAL_PROCESS": "BUSINESS",
                "SAP_FUNCTIONAL": "SAP",
                "SAP_TECHNICAL": "SAP",
                "STANDARDS_GOVERNANCE": "ORGANIZATION",
            }
            domains = {str(item.domain), aliases.get(str(item.domain), str(item.domain))}
            current = [
                stored
                for domain in domains
                for stored in self.storage.load_context(project.project_id, domain)
                if identity(stored) == identity(item)
            ]
            if any(not permitted(stored, project) for stored in current):
                return False
        if item.source_type in ("memory", "artifact") and not references_allowed(
            item.derivation_refs,
            self.storage,
            project,
            self.sources,
            strict_versions=item.source_type == "memory",
        ):
            return False
        if item.adapter_id and (
            item.adapter_id not in self.sources.adapters
            or not self.sources.authorized(item.adapter_id, project, "local")
        ):
            return False
        if item.scope == "organization" and item.domain:
            current = next(
                (
                    i
                    for i in self.storage.load_context(project.project_id, item.domain.value)
                    if identity(i) == identity(item)
                ),
                None,
            )
            return current is not None and permitted(current, project)
        return True

    def return_context(self, cursor, runtime: Runtime[PlanningInvocation]):
        plan, record = self.read(cursor)
        if record.get("budget_error"):
            runtime.context.parent.output = {"state": runtime.context.state, **record["budget_error"]}
        else:
            runtime.context.parent.context = ContextPackage.model_validate(record["package"])
        return {"package_ref": plan.package_ref}
