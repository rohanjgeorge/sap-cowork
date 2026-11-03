"""Finite request intents and the parent event graph.

Request bodies, domain state and callbacks are invocation-only. This graph has no
checkpointer; pause/resume is delegated to the checkpointed task execution graph.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.runtime import Runtime
from .models import SDLCStage, TaskStatus, uid
from .state_management import StateError


class Intent(StrEnum):
    PROJECT_GUIDANCE = "PROJECT_GUIDANCE"
    STAGE_NAVIGATION = "STAGE_NAVIGATION"
    GENERATE_ARTIFACT = "GENERATE_ARTIFACT"
    GENERATE_CODE = "GENERATE_CODE"
    GENERATE_TESTS = "GENERATE_TESTS"
    AUDIT = "AUDIT"
    EDIT_ARTIFACT = "EDIT_ARTIFACT"
    REVISE_ARTIFACT = "REVISE_ARTIFACT"
    UPLOAD_ARTIFACT = "UPLOAD_ARTIFACT"
    APPROVE_ARTIFACT = "APPROVE_ARTIFACT"
    REJECT_ARTIFACT = "REJECT_ARTIFACT"
    RETURN_TO_DRAFT = "RETURN_TO_DRAFT"
    ANSWER_CLARIFICATION = "ANSWER_CLARIFICATION"
    CONFIRM_DEVELOPMENT = "CONFIRM_DEVELOPMENT"
    WITHDRAW_DEVELOPMENT_CONFIRMATION = "WITHDRAW_DEVELOPMENT_CONFIRMATION"
    CONFIRM_TESTING = "CONFIRM_TESTING"
    WITHDRAW_TESTING_CONFIRMATION = "WITHDRAW_TESTING_CONFIRMATION"
    CLOSE_PROJECT = "CLOSE_PROJECT"
    REOPEN_PROJECT = "REOPEN_PROJECT"
    RECORD_REQUIREMENT = "RECORD_REQUIREMENT"
    PROJECT_OPERATION = "PROJECT_OPERATION"


ACTIONS = {
    "status": Intent.PROJECT_GUIDANCE,
    "conversation": Intent.PROJECT_GUIDANCE,
    "set_stage": Intent.STAGE_NAVIGATION,
    "change_draft_stage": Intent.STAGE_NAVIGATION,
    "approve": Intent.APPROVE_ARTIFACT,
    "approve_artifact": Intent.APPROVE_ARTIFACT,
    "reject": Intent.REJECT_ARTIFACT,
    "return_artifact_to_draft": Intent.RETURN_TO_DRAFT,
    "edit": Intent.EDIT_ARTIFACT,
    "upload": Intent.UPLOAD_ARTIFACT,
    "answer": Intent.ANSWER_CLARIFICATION,
    "resolve_clarification": Intent.ANSWER_CLARIFICATION,
    "confirm_code": Intent.CONFIRM_DEVELOPMENT,
    "confirm_testing": Intent.CONFIRM_TESTING,
    "withdraw_development": Intent.WITHDRAW_DEVELOPMENT_CONFIRMATION,
    "withdraw_testing": Intent.WITHDRAW_TESTING_CONFIRMATION,
    "close_project": Intent.CLOSE_PROJECT,
    "reopen_project": Intent.REOPEN_PROJECT,
    "submit_requirement": Intent.RECORD_REQUIREMENT,
}
OPERATIONS = {
    "recalculate_approved_stage",
    "submit_artifact",
    "withdraw_confirmation",
    "record_decision",
    "reopen_clarification",
    "resolve_flag",
    "reactivate_flag",
    "reconcile_artifacts",
    "compact",
    "delete_artifact",
    "retry_follow_up",
}


def normalize_request(state, values):
    message = values.get("message", "")
    action = values.get("action")
    artifact_type = values.get("artifact_type")
    task_id = values.get("task_id")
    stage = values.get("stage")
    text = message.strip().lower()
    aliases = [
        ("BRD", ("brd", "business requirement")),
        ("USER_STORIES", ("user stories", "user story")),
        ("FRD", ("frd", "functional requirement")),
        ("TDD", ("tdd", "technical design")),
        ("ABAP", ("abap", "code generation")),
        ("SIT", ("sit", "integration test")),
        ("UAT", ("uat", "acceptance test")),
        ("AUDIT_REPORT", ("audit", "code review")),
    ]
    if not action:
        if not text or text in ("status", "project status", "/status"):
            action = "status"
        elif text.startswith(("go to ", "switch to ", "move to ")):
            stage = next((s.value for s in SDLCStage if s.value.lower() in text), None)
            action = "set_stage"
        elif (
            state.task_status == TaskStatus.AWAITING_INPUT
            and text
            and not text.startswith(("generate ", "create ", "revise ", "approve ", "reject "))
        ):
            action = "answer"
        elif text.startswith(("requirement:", "cr:")):
            action = "submit_requirement"
        elif (
            text.rstrip("!.? ")
            in (
                "hi",
                "hello",
                "hey",
                "good morning",
                "good afternoon",
                "good evening",
                "thanks",
                "thank you",
            )
            or text.endswith("?")
            or text.startswith(
                (
                    "what ",
                    "how ",
                    "why ",
                    "who ",
                    "which ",
                    "where ",
                    "when ",
                    "explain ",
                    "describe ",
                    "tell me ",
                    "please explain ",
                    "help me understand ",
                    "can you ",
                    "could you ",
                    "would you ",
                )
            )
        ):
            action = "conversation"
        elif not state.requirement and (
            len(message) > 120 or "\n" in message or not any(w in text for _, words in aliases for w in words)
        ):
            action = "submit_requirement"
        elif text.startswith("retry"):
            action, artifact_type, task_id = (
                "generate",
                state.expected_next_artifact,
                state.active_task_id,
            )
        elif any(word in text for word in ("generate", "create ", "revise", "draft ", "prepare")):
            action = "generate"
            artifact_type = next(
                (kind for kind, words in aliases if any(w in text for w in words)),
                state.expected_next_artifact,
            )
        elif text.startswith(("approve ", "reject ")):
            action = "approve" if text.startswith("approve") else "reject"
            artifact_type = next((kind for kind, words in aliases if any(w in text for w in words)), None)
        elif not state.requirement or text.startswith(("requirement:", "cr:")):
            action = "submit_requirement"
        else:
            action = "conversation"
    return {**values, "action": action, "artifact_type": artifact_type, "task_id": task_id, "stage": stage}


class EventCursor(TypedDict):
    project_id: str
    request_id: str
    intent: str
    route_decision: str


@dataclass
class EventInvocation:
    values: dict
    handler: Callable
    actor: str = "local"
    state: object = None
    normalized: dict | None = None
    output: object = None
    status: dict | None = None
    trace: list | None = None


class ParentEventGraph:
    def __init__(self, runtime):
        self.runtime = runtime
        graph = StateGraph(EventCursor, context_schema=EventInvocation)
        nodes = {
            "load_project": self.load_project,
            "understand_request": self.understand_request,
            "classify_intent": self.classify_intent,
            "authorize_action": self.authorize_action,
            "route_intent": self.route_intent,
            "refresh_project_status": self.refresh_project_status,
            "update_project_memory": self.update_project_memory,
            "build_response": self.build_response,
        }
        for name, fn in nodes.items():
            graph.add_node(name, fn)
        for branch in (
            "navigate_stage",
            "project_guidance",
            "resolve_task",
            "artifact_lifecycle",
            "state_operation",
            "answer_clarification",
        ):
            graph.add_node(branch, self.execute_event)
            graph.add_edge(branch, "refresh_project_status")
        sequence = [
            START,
            "load_project",
            "understand_request",
            "classify_intent",
            "authorize_action",
            "route_intent",
        ]
        for a, b in zip(sequence, sequence[1:]):
            graph.add_edge(a, b)
        graph.add_conditional_edges(
            "route_intent",
            lambda s: s["route_decision"],
            {
                b: b
                for b in (
                    "navigate_stage",
                    "project_guidance",
                    "resolve_task",
                    "artifact_lifecycle",
                    "state_operation",
                    "answer_clarification",
                )
            },
        )
        graph.add_edge("refresh_project_status", "update_project_memory")
        graph.add_edge("update_project_memory", "build_response")
        graph.add_edge("build_response", END)
        self.graph = graph.compile()

    def dispatch(self, project_id, values, handler, *, actor="local", trace=None):
        ctx = EventInvocation(dict(values), handler, actor=actor, trace=trace)
        self.graph.invoke(
            {"project_id": project_id, "request_id": values.get("request_id") or uid()}, context=ctx
        )
        return ctx.output

    def _trace(self, ctx, name):
        if ctx.trace is not None:
            ctx.trace.append(name)

    def load_project(self, cursor, runtime: Runtime[EventInvocation]):
        ctx = runtime.context
        self.runtime.storage.load_project(cursor["project_id"])
        ctx.state = self.runtime.storage.load_state(cursor["project_id"])
        self._trace(ctx, "load_project")
        return {}

    def understand_request(self, cursor, runtime: Runtime[EventInvocation]):
        ctx = runtime.context
        ctx.normalized = normalize_request(ctx.state, ctx.values)
        self._trace(ctx, "understand_request")
        return {}

    def classify_intent(self, cursor, runtime: Runtime[EventInvocation]):
        ctx = runtime.context
        action = ctx.normalized["action"]
        if action == "generate":
            from .router import route

            _, selected = route(ctx.state.current_stage, ctx.normalized.get("artifact_type"))
            kind = selected.value
            ctx.normalized["artifact_type"] = kind
            intent = (
                Intent.REVISE_ARTIFACT
                if ctx.normalized.get("new_version")
                or ctx.normalized.get("feedback")
                or ctx.normalized.get("message", "").strip().lower().startswith("revise")
                else {
                    "ABAP": Intent.GENERATE_CODE,
                    "SIT": Intent.GENERATE_TESTS,
                    "UAT": Intent.GENERATE_TESTS,
                    "AUDIT_REPORT": Intent.AUDIT,
                }.get(kind, Intent.GENERATE_ARTIFACT)
            )
        elif action in ACTIONS:
            intent = ACTIONS[action]
        elif action in OPERATIONS:
            intent = Intent.PROJECT_OPERATION
        else:
            raise ValueError("Unknown project action")
        self._trace(ctx, "classify_intent")
        return {"intent": intent.value}

    def authorize_action(self, cursor, runtime: Runtime[EventInvocation]):
        ctx = runtime.context
        intent = Intent(cursor["intent"])
        if ctx.actor != "local":
            raise StateError("UNAUTHORIZED", "Only the authenticated user may submit project events")
        if ctx.state.project_status != "active" and intent not in (
            Intent.REOPEN_PROJECT,
            Intent.PROJECT_GUIDANCE,
        ):
            self.runtime.state.require_active(ctx.state)
        if ctx.state.project_status != "active" and ctx.normalized["action"] == "conversation":
            self.runtime.state.require_active(ctx.state)
        if intent in (
            Intent.APPROVE_ARTIFACT,
            Intent.REJECT_ARTIFACT,
            Intent.RETURN_TO_DRAFT,
            Intent.EDIT_ARTIFACT,
        ):
            kind = ctx.normalized.get("artifact_type") or ctx.normalized.get("artifact_id")
            if not kind:
                raise ValueError("Choose an artifact to review or edit")
            artifact = self.runtime.storage.load_artifact(
                cursor["project_id"], kind, ctx.normalized.get("version")
            )
            ctx.normalized["version"] = artifact.artifact_version
        self._trace(ctx, "authorize_action")
        return {}

    def route_intent(self, cursor, runtime: Runtime[EventInvocation]):
        intent = Intent(cursor["intent"])
        branch = "state_operation"
        if intent == Intent.STAGE_NAVIGATION:
            branch = "navigate_stage"
        elif intent == Intent.PROJECT_GUIDANCE:
            branch = "project_guidance"
        elif intent in (
            Intent.GENERATE_ARTIFACT,
            Intent.GENERATE_CODE,
            Intent.GENERATE_TESTS,
            Intent.AUDIT,
            Intent.REVISE_ARTIFACT,
        ):
            branch = "resolve_task"
        elif intent == Intent.ANSWER_CLARIFICATION:
            branch = "answer_clarification"
        elif intent in (
            Intent.APPROVE_ARTIFACT,
            Intent.REJECT_ARTIFACT,
            Intent.RETURN_TO_DRAFT,
            Intent.EDIT_ARTIFACT,
            Intent.UPLOAD_ARTIFACT,
        ):
            branch = "artifact_lifecycle"
        self._trace(runtime.context, "route_intent")
        return {"route_decision": branch}

    def execute_event(self, cursor, runtime: Runtime[EventInvocation]):
        ctx = runtime.context
        self._trace(ctx, cursor["route_decision"])
        ctx.output = ctx.handler(ctx.normalized)
        return {}

    def refresh_project_status(self, cursor, runtime: Runtime[EventInvocation]):
        ctx = runtime.context
        ctx.status = self.runtime.status.get(cursor["project_id"])
        self._trace(ctx, "refresh_project_status")
        return {}

    def update_project_memory(self, cursor, runtime: Runtime[EventInvocation]):
        # Existing domain services refresh memory after meaningful mutations. Do
        # not repeat writes or refresh memory for a read-only guidance event.
        self._trace(runtime.context, "update_project_memory")
        return {}

    def build_response(self, cursor, runtime: Runtime[EventInvocation]):
        self._trace(runtime.context, "build_response")
        return {}
