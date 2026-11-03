"""Records an offline approval declaration from an authenticated user."""

from .state_management import StateManagementService


class ApprovalService:
    def __init__(self, storage, memory_service=None, state_service=None):
        self.storage = storage
        self.memory_service = memory_service
        self.state_service = state_service or StateManagementService(storage)

    def review(
        self,
        project_id,
        artifact_id,
        version,
        approved,
        feedback="",
        user="local",
        *,
        expected_revision=None,
        request_id=None,
    ):
        if not approved and not feedback.strip():
            raise ValueError("Revision feedback is required")
        if not approved:
            prior = self.storage.load_artifact(project_id, artifact_id, version)
            if prior.approval_status == "approved":
                if user != "local":
                    from .state_management import StateError

                    raise StateError("UNAUTHORIZED", "Only the authenticated user can request changes")
                from .artifact_lifecycle import ArtifactLifecycle

                artifact, state = ArtifactLifecycle(self.storage, self.state_service).edit(
                    project_id,
                    artifact_id,
                    prior.content,
                    remarks=feedback,
                    expected_revision=expected_revision,
                )
                artifact.feedback = feedback
                with self.storage.transaction(project_id):
                    self.storage.save_artifact(project_id, artifact)
                return artifact
        state = self.state_service.apply(
            project_id,
            "approve_artifact" if approved else "return_artifact_to_draft",
            {"artifact_id": artifact_id, "version": version, "feedback": feedback},
            actor=user,
            expected_revision=expected_revision,
            request_id=request_id,
        )
        if self.memory_service:
            self.memory_service.refresh(state)
        return self.storage.load_artifact(project_id, artifact_id, version)
