"""V1 extension hooks. These are correlation checks, not production SAP validation."""


class GuardrailHook:
    def __init__(self, storage=None, registry=None, context_policy=None):
        self.calls = []
        self.storage, self.registry, self.context_policy = storage, registry, context_policy

    def before_execute(self, state, context, *, operation="generation"):
        from .eligibility import ensure_eligible

        ensure_eligible(
            state, operation, state.current_task.removeprefix("Generate ") if state.current_task else None
        )
        self.calls.append(state.active_task_id)
        if context.project_id != state.project_id or context.task_id != state.active_task_id:
            raise ValueError("Execution context correlation mismatch")
        if self.storage:
            fresh = self.storage.load_state(state.project_id)
            if fresh.project_status != "active":
                raise ValueError("Project is closed")
            if state.active_capability_id != "PROJECT_CHAT" and (
                fresh.active_task_id != state.active_task_id
                or fresh.active_capability_id != state.active_capability_id
            ):
                raise ValueError("Execution task no longer matches project state")
            if operation == "generation" and any(issue.blocking for issue in fresh.issues):
                raise ValueError("Project has an active blocking condition")
            project = self.storage.load_project(state.project_id)
            from .context_planning import items
            from .context_sources import permitted

            if any(
                not permitted(item, project)
                or self.context_policy
                and not self.context_policy._still_authorized(item, project)
                for item in items(context)
            ):
                raise ValueError("Context source access changed; replan before execution")
        if self.registry and state.active_capability_id != "PROJECT_CHAT":
            if state.active_capability_id not in self.registry.configured():
                raise ValueError("Capability is not configured")


class ValidationHook:
    def __init__(self, registry=None):
        self.calls = []
        self.registry = registry

    def after_execute(self, result, state, context):
        self.calls.append(state.active_task_id)
        if (
            self.registry
            and self.registry.output_contract(result.capability_id) == "artifact"
            and not (result.output or {}).get("artifact")
        ):
            return {
                "status": "fail",
                "code": "OUTPUT_CONTRACT_FAILED",
                "message": "Artifact-producing capability returned success without an artifact",
            }
        if result.task_id != state.active_task_id:
            return {"status": "fail", "message": "Task mismatch"}
        if result.capability_id != state.active_capability_id:
            return {"status": "fail", "message": "Capability mismatch"}
        if result.output and "artifact" in result.output:
            from .models import Artifact
            from .templates import TemplateRepository
            from .context_planning import items
            import re

            try:
                artifact = Artifact.model_validate(result.output["artifact"])
            except ValueError:
                return {"status": "fail", "message": "Invalid artifact contract"}
            if not artifact.content.strip():
                return {"status": "fail", "message": "Empty artifact"}
            expected = state.current_task.removeprefix("Generate ")
            if (
                artifact.project_id != state.project_id
                or artifact.source_task_id != state.active_task_id
                or artifact.artifact_type != expected
                or artifact.artifact_id != artifact.artifact_type
            ):
                return {"status": "fail", "message": "Artifact correlation mismatch"}
            # Application artifacts use the current template contract. The
            # replaceable ABAP module owns its output format.
            if artifact.artifact_type != "ABAP":
                template, ref = TemplateRepository().load(artifact.artifact_type)

                def headings(text):
                    return re.findall(r"^#{1,2} .+$", text, re.M)

                if (
                    artifact.template_ref != ref
                    or artifact.template_version != ref
                    or headings(template) != headings(artifact.content)
                ):
                    return {"status": "fail", "message": "Artifact template mismatch"}
            known = {item.source for item in items(context)}
            known.update(f"artifact:{ref.artifact_id}:v{ref.version}" for ref in context.upstream_artifacts)
            if any(source not in known for source in artifact.sources):
                return {"status": "fail", "message": "Unknown artifact source"}
        return {"status": "pass", "message": "V1 contract checks only; production validation deferred"}
