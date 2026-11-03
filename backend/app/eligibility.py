"""Central deterministic execution eligibility, independent of model discretion."""

from .router import ARTIFACT_STAGE


def ensure_eligible(state, operation, artifact_type=None):
    from .state_management import StateError

    if operation not in ("generation", "confirm_code", "confirm_testing", "close_project"):
        return
    relevant = (
        {artifact_type}
        if artifact_type
        else {"ABAP"}
        if operation == "confirm_code"
        else {"SIT", "UAT", "ABAP"}
        if operation == "confirm_testing"
        else set(state.artifacts)
    )
    stages = {ARTIFACT_STAGE[k] for k in relevant if k in ARTIFACT_STAGE}
    reasons = [
        {"kind": "issue", "code": i.code, "reason": i.message}
        for i in state.issues
        if i.blocking and (not stages or i.stage in stages)
    ]
    for flag in state.flags:
        if flag.status != "active" or flag.type != "blocker":
            continue
        if flag.related_artifact and flag.related_artifact not in relevant:
            continue
        if flag.related_stage and flag.related_stage not in stages:
            continue
        from .router import ARTIFACT_CAPABILITY

        if flag.capability_id and flag.capability_id not in {ARTIFACT_CAPABILITY.get(k) for k in relevant}:
            continue
        reasons.append({"kind": "flag", "flag_id": flag.flag_id, "reason": flag.description})
    if reasons:
        raise StateError(
            "BLOCKED",
            "Operation blocked: " + "; ".join(r["reason"] for r in reasons),
            state.state_revision,
            details=reasons,
        )
