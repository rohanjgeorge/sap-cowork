"""V1 extension hooks. These are correlation checks, not production SAP validation."""


class GuardrailHook:
    def __init__(self):
        self.calls = []

    def before_execute(self, state, context):
        self.calls.append(state.active_task_id)
        if context.project_id != state.project_id or context.task_id != state.active_task_id:
            raise ValueError("Execution context correlation mismatch")


class ValidationHook:
    def __init__(self):
        self.calls = []

    def after_execute(self, result, state, context):
        self.calls.append(state.active_task_id)
        if result.task_id != state.active_task_id:
            return {"status": "fail", "message": "Task mismatch"}
        if (
            result.output
            and "artifact" in result.output
            and not result.output["artifact"].get("content", "").strip()
        ):
            return {"status": "fail", "message": "Empty artifact"}
        return {"status": "pass", "message": "V1 contract checks only; production validation deferred"}
