"""Durable generation identity, independent of checkpoints and projections."""

from hashlib import sha256
import json
from .router import route
from .state_management import StateError


def bind_generation(storage, state, task_id, artifact_type, inputs):
    key = "request-" + sha256(f"{state.project_id}:{task_id}".encode()).hexdigest()
    try:
        prior = storage.load_context_run(state.project_id, key)
    except FileNotFoundError:
        prior = None
    selected = route(state.current_stage, artifact_type or (prior or {}).get("artifact_type"))[1]
    values = inputs or {}
    payload = {
        "artifact_type": selected.value,
        "capability": route(state.current_stage, selected)[0],
        "intent": "revision" if values.get("new_version") or values.get("instructions") else "generation",
        "instructions": (values.get("instructions") or "").replace("\r\n", "\n").strip(),
        "new_version": bool(values.get("new_version")),
        "authors": values.get("authors") or "",
        "remarks": values.get("remarks") or "",
        "model_policy": values.get("model_policy")
        or storage.load_project(state.project_id).model_policy
        or "user_default",
        "upstream_refs": sorted(
            values.get("upstream_refs") or values.get("upstream_artifacts") or [], key=str
        ),
        "options": {
            k: v
            for k, v in values.items()
            if k
            not in {
                "instructions",
                "new_version",
                "authors",
                "remarks",
                "model_policy",
                "upstream_refs",
                "upstream_artifacts",
                "expected_revision",
                "request_id",
                "task_id",
            }
        },
    }
    signature = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    if prior and prior["signature"] != signature:
        raise StateError(
            "IDENTITY_CONFLICT",
            "Generation task ID is bound to a different artifact or generation request; use a new task ID",
            state.state_revision,
        )
    if prior is None:
        with storage.transaction(state.project_id):
            storage.save_context_run(
                state.project_id,
                key,
                {
                    "kind": "generation_request",
                    "task_id": task_id,
                    "artifact_type": selected.value,
                    "signature": signature,
                    "request": payload,
                },
            )
    return selected
