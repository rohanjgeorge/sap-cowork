"""Advisory status derivation. Never owns workflow transitions."""

from .models import SDLCStage
from .router import STAGE_ARTIFACT, dependency_issues


class ProjectStatusService:
    def __init__(self, storage):
        self.storage = storage

    def get(self, project_id):
        state = self.storage.load_state(project_id)
        stages = []
        issues = []
        for stage in SDLCStage:
            kind = STAGE_ARTIFACT[stage]
            documents = [
                r
                for r in state.artifact_registry
                if r.artifact_type == kind
                or (stage == SDLCStage.TESTING and r.artifact_type == "AUDIT_REPORT")
            ]
            documents.sort(key=lambda r: int(r.version.split(".")[0]), reverse=True)
            primary = [r for r in documents if r.artifact_type == kind]
            latest = primary[0] if primary else None
            started = stage in state.started_stages or bool(documents)
            gaps = dependency_issues(state, kind) if started else []
            gaps.extend(i for i in state.issues if i.stage == stage and i.blocking)
            issues.extend(gaps)
            questions = [
                c for c in state.open_clarifications if c.status == "open" and (stage == state.current_stage)
            ]
            color = (
                "green"
                if latest and latest.approval_status == "approved" and not gaps and not questions
                else "amber"
                if started
                else "grey"
            )
            stages.append(
                {
                    "stage": stage.value,
                    "color": color,
                    "label": {
                        "green": "Approved",
                        "amber": "In progress / attention",
                        "grey": "Yet to start",
                    }[color],
                    "expected_artifact": kind.value,
                    "documents": [d.model_dump(mode="json") for d in documents],
                    "clarifications": [c.model_dump(mode="json") for c in questions],
                    "issues": [i.model_dump(mode="json") for i in gaps],
                }
            )
        return {
            "project_id": project_id,
            "current_stage": state.current_stage.value,
            "current_task": state.current_task,
            "task_status": state.task_status.value,
            "recommended_stage": state.recommended_stage.value if state.recommended_stage else None,
            "recommended_next_action": state.recommended_next_action,
            "stages": stages,
            "issues": [i.model_dump(mode="json") for i in issues],
            "open_clarifications": [
                c.model_dump(mode="json") for c in state.open_clarifications if c.status == "open"
            ],
        }
