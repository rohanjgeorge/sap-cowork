"""Deterministic routing and ideal-flow recommendations."""

from .models import ArtifactType, SDLCStage, ProjectIssue

STAGE_ARTIFACT = {
    SDLCStage.PLANNING: ArtifactType.BRD,
    SDLCStage.ANALYSIS: ArtifactType.FRD,
    SDLCStage.DESIGN: ArtifactType.TDD,
    SDLCStage.DEVELOPMENT: ArtifactType.ABAP,
    SDLCStage.TESTING: ArtifactType.UAT,
}
ARTIFACT_STAGE = {value: key for key, value in STAGE_ARTIFACT.items()}
ARTIFACT_STAGE[ArtifactType.AUDIT_REPORT] = SDLCStage.TESTING
ARTIFACT_CAPABILITY = {a: f"{a.value}_GENERATOR" for a in STAGE_ARTIFACT.values()}
ARTIFACT_CAPABILITY[ArtifactType.AUDIT_REPORT] = "AUDIT_WORKER"
UPSTREAM = {
    ArtifactType.BRD: None,
    ArtifactType.FRD: ArtifactType.BRD,
    ArtifactType.TDD: ArtifactType.FRD,
    ArtifactType.ABAP: ArtifactType.TDD,
    ArtifactType.UAT: ArtifactType.FRD,
    ArtifactType.AUDIT_REPORT: ArtifactType.ABAP,
}


def route(stage, artifact_type=None):
    selected = ArtifactType(artifact_type) if artifact_type else STAGE_ARTIFACT[SDLCStage(stage)]
    return ARTIFACT_CAPABILITY[selected], selected


def next_stage(stage):
    stages = list(SDLCStage)
    index = stages.index(SDLCStage(stage))
    return stages[index + 1] if index < len(stages) - 1 else None


def dependency_issues(state, artifact_type):
    upstream = UPSTREAM[artifact_type]
    if not upstream:
        return []
    available = [r for r in state.artifact_registry if r.artifact_type == upstream]
    latest = max(available, key=lambda r: tuple(int(v) for v in r.version.split(".")), default=None)
    if latest and latest.approval_status == "approved":
        return []
    code = f"{upstream.value}_" + ("UNAPPROVED" if latest else "MISSING")
    severity = "error" if artifact_type == ArtifactType.ABAP and latest else "warning"
    return [
        ProjectIssue(
            code=code,
            severity=severity,
            blocking=False,
            stage=ARTIFACT_STAGE[artifact_type],
            message=f"{upstream.value} is {'not approved' if latest else 'missing'}; "
            "generation can proceed using available context.",
        )
    ]
