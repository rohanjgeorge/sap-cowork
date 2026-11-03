"""Chat asks persisted clarifications individually without losing the task queue."""

from backend.app.models import CapabilityResponse, Clarification
from backend.app.runtime import Runtime
from backend.app.services import ApplicationService


def test_chat_asks_one_question_then_resumes_only_after_the_current_tasks_answers(storage, tmp_path):
    runtime = Runtime(storage, tmp_path)
    service = ApplicationService(runtime)
    original = runtime.registry._implementations["BRD_GENERATOR"]

    class Worker:
        calls = 0

        def invoke(self, request):
            self.calls += 1
            if self.calls == 1:
                return CapabilityResponse(
                    task_id=request.task_id,
                    capability_id=request.capability_id,
                    status="clarification_required",
                    clarification_questions=["Who owns the process?", "What is the schedule?"],
                )
            return original.invoke(request)

    worker = Worker()
    runtime.registry.register("BRD_GENERATOR", worker)
    first = service.chat("p", action="generate", artifact_type="BRD", task_id="sequential")
    assert first["questions"] == ["Who owns the process?", "What is the schedule?"]
    assert first["message"] == "Who owns the process?"
    assert len(first["workspace"]["status"]["open_clarifications"]) == 2
    state = storage.load_state("p")
    state.clarifications.insert(0, Clarification(question="Old task question", task_id="old-task"))
    storage.save_state("p", state)

    # Reopening retains every question, while answering without an explicit ID
    # selects the current task's first question rather than the older task.
    service = ApplicationService(Runtime(storage, tmp_path))
    service.runtime.registry.register("BRD_GENERATOR", worker)
    second = service.chat("p", action="answer", message="Logistics", request_id="first-answer")
    assert second["message"] == "What is the schedule?"
    assert second["questions"] == ["What is the schedule?"]
    assert second["workspace"]["state"].task_status == "awaiting_input"
    assert worker.calls == 1
    assert service.runtime.orchestrator.checkpoint_snapshot("p", "sequential")["next"] == ("await_input",)
    service.chat("p", action="answer", message="Logistics", request_id="first-answer")
    assert worker.calls == 1
    finished = service.chat("p", action="answer", message="Daily", request_id="second-answer")
    assert worker.calls == 2
    assert finished["artifact"].artifact_type == "BRD"
    current = [c for c in storage.load_state("p").clarifications if c.task_id == "sequential"]
    assert [(c.status, c.response) for c in current] == [("resolved", "Logistics"), ("resolved", "Daily")]
    assert storage.load_state("p").clarifications[0].status == "open"
