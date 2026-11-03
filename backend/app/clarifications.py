from .models import ContextItem, ContextPackage, now
from .state_management import StateManagementService


class ClarificationService:
    def __init__(self, storage, state_service=None):
        self.storage = storage
        self.state_service = state_service or StateManagementService(storage)

    def preflight(self, state, artifact_type):
        if artifact_type == "BRD" and not state.requirement.strip():
            return ["Please provide the requirement or change request for the BRD."]
        # Initial deterministic ambiguity rule. More material gaps can also be returned by workers.
        text = state.requirement.lower()
        ambiguous_availability = any(term in text for term in ("material available", "material availability"))
        resolved = any(
            c.status == "resolved" and "availability" in c.question.lower() for c in state.open_clarifications
        )
        curated = self.storage.load_context(state.project_id, "SAP")
        defined = any("availability definition:" in item.content.lower() for item in curated)
        if artifact_type == "FRD" and ambiguous_availability and not resolved and not defined:
            return [
                "What is the material availability rule: unrestricted stock, ATP confirmation, "
                "or another check? Specify plant, quantity and partial-delivery behavior."
            ]
        return []

    def pause(self, state, questions):
        self.state_service.request(state, "add_clarification", {"questions": questions})
        return {"state": state, "questions": questions}

    def answer(
        self, orchestrator, project_id, clarification_id, response, *, expected_revision=None, request_id=None
    ):
        if not response.strip():
            raise ValueError("Clarification answer cannot be empty")
        before = self.storage.load_state(project_id)
        original = next((c for c in before.clarifications if c.clarification_id == clarification_id), None)
        if original and callable(getattr(orchestrator, "sync_runtime_projection", None)):
            orchestrator.sync_runtime_projection(project_id, original.task_id)
            before = self.storage.load_state(project_id)
        paused = (
            original is not None
            and original.task_id == before.active_task_id
            and before.task_status == "awaiting_input"
        )
        if original and callable(getattr(orchestrator, "checkpoint_snapshot", None)):
            snapshot = orchestrator.checkpoint_snapshot(project_id, original.task_id)
            if snapshot["values"]:
                paused = bool(snapshot["next"] and snapshot["values"].get("wait_reason") == "clarification")
        state = self.state_service.apply(
            project_id,
            "resolve_clarification",
            {
                "clarification_id": clarification_id,
                "answer": response,
            },
            expected_revision=expected_revision,
            request_id=request_id,
        )
        question = next(c for c in state.clarifications if c.clarification_id == clarification_id)
        if original is not None and original.status == "resolved":
            return {"state": before, "message": "Clarification already resolved."}
        with self.storage.transaction(project_id):
            self.storage.save_context(
                project_id,
                ContextPackage(
                    project_id=project_id,
                    task_id=state.active_task_id or "clarification",
                    business_context=[
                        ContextItem(
                            content=f"{question.question}\nAnswer: {response}",
                            source=f"clarification:{clarification_id}",
                            source_type="user",
                        )
                    ],
                ),
            )
            memory = self.storage.load_memory(project_id)
            memory.content += f"\nResolved clarification: {question.question}\n{response}\n"
            memory.updated_at = now()
            self.storage.save_memory(project_id, memory)
        if any(c.status == "open" and c.task_id == state.active_task_id for c in state.clarifications):
            return {
                "state": state,
                "questions": [
                    c.question
                    for c in state.clarifications
                    if c.status == "open" and c.task_id == state.active_task_id
                ],
            }
        if not paused:
            return {"state": state, "message": "Clarification resolved. Existing artifacts are unchanged."}
        return orchestrator._execute(state, question.related_artifact or state.expected_next_artifact)
