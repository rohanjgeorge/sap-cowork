from .models import Clarification, ContextItem, ContextPackage, ProjectIssue, TaskStatus, now


class ClarificationService:
    def __init__(self, storage):
        self.storage = storage

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
        state.issues = [i for i in state.issues if i.code != "MATERIAL_INPUT_REQUIRED"]
        state.issues.append(
            ProjectIssue(
                code="MATERIAL_INPUT_REQUIRED",
                message="Answer the open clarification to resume this task.",
                severity="error",
                blocking=True,
                stage=state.current_stage,
            )
        )
        for question in questions:
            if not any(c.question == question and c.status == "open" for c in state.open_clarifications):
                state.open_clarifications.append(
                    Clarification(question=question, task_id=state.active_task_id)
                )
        state.task_status = TaskStatus.AWAITING_INPUT
        self.storage.save_state(state.project_id, state)
        return {"state": state, "questions": questions}

    def answer(self, orchestrator, project_id, clarification_id, response):
        if not response.strip():
            raise ValueError("Clarification answer cannot be empty")
        with self.storage.transaction(project_id):
            state = self.storage.load_state(project_id)
            candidates = [c for c in state.open_clarifications if c.clarification_id == clarification_id]
            if not candidates or candidates[0].status != "open":
                raise ValueError("Open clarification not found")
            question = candidates[0]
            question.response = response
            question.status = "resolved"
            if "provide the requirement" in question.question.lower():
                state.requirement = response
            self.storage.save_context(
                project_id,
                ContextPackage(
                    project_id=project_id,
                    task_id=state.active_task_id,
                    business_context=[
                        ContextItem(
                            content=f"{question.question}\nAnswer: {response}",
                            source=f"clarification:{clarification_id}",
                            source_type="user",
                        )
                    ],
                ),
            )
            self.storage.save_state(project_id, state)
            memory = self.storage.load_memory(project_id)
            memory.content += f"\nResolved clarification: {question.question}\n{response}\n"
            memory.updated_at = now()
            self.storage.save_memory(project_id, memory)
            if any(
                c.status == "open" and c.task_id == state.active_task_id for c in state.open_clarifications
            ):
                return {
                    "state": state,
                    "questions": [c.question for c in state.open_clarifications if c.status == "open"],
                }
            state.issues = [i for i in state.issues if i.code != "MATERIAL_INPUT_REQUIRED"]
            self.storage.save_state(project_id, state)
            return orchestrator._execute(state, state.expected_next_artifact)
