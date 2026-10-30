from .models import ContextDomain as D, ContextRequest

PROFILES = {
    "BRD": [D.BUSINESS, D.SDLC],
    "FRD": [D.BUSINESS, D.SAP, D.ORGANIZATION, D.HISTORICAL_DEVELOPMENT, D.SDLC],
    "TDD": [D.BUSINESS, D.SAP, D.ORGANIZATION, D.HISTORICAL_DEVELOPMENT, D.SDLC],
    "ABAP": [D.SAP, D.ORGANIZATION, D.HISTORICAL_DEVELOPMENT, D.SDLC],
    "UAT": [D.BUSINESS, D.SAP, D.ORGANIZATION, D.SDLC],
    "AUDIT_REPORT": [D.SAP, D.ORGANIZATION, D.SDLC],
}


class ContextPlanner:
    def plan(self, state, artifact_type):
        domains = list(PROFILES[artifact_type])
        if artifact_type == "BRD" and any(w in state.requirement.lower() for w in ("sap", "sto", "plant")):
            domains.extend([D.SAP, D.ORGANIZATION])
        inputs = {
            "BRD": [],
            "FRD": ["BRD"],
            "TDD": ["BRD", "FRD"],
            "ABAP": ["FRD", "TDD"],
            "UAT": ["BRD", "FRD", "TDD", "ABAP"],
            "AUDIT_REPORT": ["FRD", "TDD", "ABAP"],
        }[artifact_type]
        return ContextRequest(
            project_id=state.project_id,
            task_id=state.active_task_id,
            current_stage=state.current_stage,
            current_task=state.current_task,
            required_domains=domains,
            upstream_artifacts=list(
                dict.fromkeys(r.artifact_id for r in state.artifact_registry if r.artifact_type in inputs)
            ),
            query=f"Retrieve context relevant to {state.current_task}",
        )
