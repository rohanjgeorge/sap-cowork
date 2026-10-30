from .models import ApprovalStatus, TaskStatus, now
from .router import ARTIFACT_STAGE, STAGE_ARTIFACT, next_stage, dependency_issues


class ApprovalService:
    def __init__(self, storage, memory_service=None):
        self.storage = storage
        self.memory_service = memory_service

    def review(self, project_id, artifact_id, version, approved, feedback="", user="local"):
        if not approved and not feedback.strip():
            raise ValueError("Revision feedback is required")
        with self.storage.transaction(project_id):
            artifact = self.storage.load_artifact(project_id, artifact_id, version)
            artifact.approval_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            artifact.approved_by = user if approved else None
            artifact.feedback = feedback or None
            artifact.last_edited_date = now()
            self.storage.save_artifact(project_id, artifact)
            state = self.storage.load_state(project_id)
            state.artifact_registry = self.storage.list_artifacts(project_id)
            latest = self.storage.load_artifact(project_id, artifact_id)
            if latest.artifact_version == version and (
                state.current_task is None or state.expected_next_artifact == artifact.artifact_type.value
            ):
                recommended = next_stage(ARTIFACT_STAGE[artifact.artifact_type]) if approved else None
                state.recommended_stage = recommended
                state.expected_next_artifact = (
                    STAGE_ARTIFACT[recommended].value if recommended else artifact.artifact_type.value
                )
                state.recommended_next_action = (
                    f"Generate {STAGE_ARTIFACT[recommended].value}"
                    if recommended
                    else ("Review testing results" if approved else f"Revise {artifact.artifact_type.value}")
                )
                state.task_status = TaskStatus.IDLE
                state.current_task = None
            state.issues = [
                issue
                for stage in state.started_stages
                for issue in dependency_issues(state, STAGE_ARTIFACT[stage])
            ]
            self.storage.save_state(project_id, state)
            if self.memory_service:
                self.memory_service.refresh(state)
            return artifact
