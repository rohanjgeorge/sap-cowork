"""Advisory status derivation. Never owns workflow transitions."""

from .models import SDLCStage
from .router import STAGE_ARTIFACT, ARTIFACT_STAGE, dependency_issues
from .state_management import STAGE_REQUIREMENTS, stage_complete


class ProjectStatusService:
    def __init__(self, storage):
        self.storage = storage

    def get(self, project_id):
        state = self.storage.load_state(project_id)
        stages = []
        issues = []
        for stage in SDLCStage:
            kind = STAGE_ARTIFACT[stage]
            documents = [r for r in state.artifact_registry if ARTIFACT_STAGE[r.artifact_type] == stage]
            documents.sort(key=lambda r: int(r.version.split(".")[0]), reverse=True)
            started = stage in state.started_stages or bool(documents)
            gaps = []
            if started:
                for required in STAGE_REQUIREMENTS[stage]:
                    gaps.extend(dependency_issues(state, required))
            gaps.extend(i for i in state.issues if i.stage == stage and i.blocking)
            gaps = list({gap.code: gap for gap in gaps}.values())
            issues.extend(gaps)
            questions = [
                c
                for c in state.clarifications
                if c.status == "open" and stage == ARTIFACT_STAGE.get(c.related_artifact, state.current_stage)
            ]
            drafts = stage in (SDLCStage.PLANNING, SDLCStage.ANALYSIS, SDLCStage.DESIGN) and any(
                entry.status != "approved"
                for k, entry in state.artifacts.items()
                if ARTIFACT_STAGE[k] == stage and k != "AUDIT_REPORT"
            )
            prior_complete = all(
                stage_complete(state, s) for s in list(SDLCStage)[: list(SDLCStage).index(stage)]
            )
            color = (
                "green"
                if stage_complete(state, stage)
                and prior_complete
                and not drafts
                and not gaps
                and not questions
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
                    "expected_artifacts": STAGE_REQUIREMENTS[stage],
                    "documents": [d.model_dump(mode="json") for d in documents],
                    "clarifications": [c.model_dump(mode="json") for c in questions],
                    "issues": [i.model_dump(mode="json") for i in gaps],
                }
            )
        return {
            "project_id": project_id,
            "current_stage": state.current_stage.value,
            "current_draft_stage": state.current_draft_stage.value,
            "current_approved_stage": state.current_approved_stage.value,
            "project_status": state.project_status,
            "state_revision": state.state_revision,
            "confirmations": [c.model_dump(mode="json") for c in state.confirmations],
            "flags": [f.model_dump(mode="json") for f in state.flags if f.status == "active"],
            "follow_ups": state.follow_ups,
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
