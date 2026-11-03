"""External mutation envelope, durable deduplication and per-project serialization."""

from hashlib import sha256
import json
from fastapi.encoders import jsonable_encoder
from .models import Artifact, ProjectState, Project, ProjectMemory, uid
from .state_management import StateError


def restore(value):
    if not isinstance(value, dict):
        return value
    result = dict(value)
    for key, model in {
        "state": ProjectState,
        "artifact": Artifact,
        "project": Project,
        "memory": ProjectMemory,
    }.items():
        if isinstance(result.get(key), dict):
            result[key] = model.model_validate(result[key])
    if isinstance(result.get("workspace"), dict):
        result["workspace"] = restore(result["workspace"])
    return result


class MutationCoordinator:
    def __init__(self, storage, workspace=None):
        self.storage = storage
        self.workspace = workspace

    def run(
        self,
        project_id,
        operation,
        payload,
        handler,
        *,
        request_id=None,
        expected_revision=None,
        actor="local",
    ):
        if actor != "local":
            raise StateError("UNAUTHORIZED", "Only the authenticated user may mutate a project")
        request_id = request_id or uid()
        signature = sha256(
            json.dumps({"operation": operation, "payload": payload}, sort_keys=True, default=str).encode()
        ).hexdigest()
        key = "mutation-" + sha256(request_id.encode()).hexdigest()
        with self.storage.mutation_lock(project_id):
            try:
                prior = self.storage.load_context_run(project_id, key)
            except FileNotFoundError:
                prior = None
            if prior:
                if prior["signature"] != signature or prior["actor"] != actor:
                    raise StateError(
                        "IDENTITY_CONFLICT", "Request ID already belongs to a different mutation"
                    )
                if prior.get("status") == "complete":
                    return restore(prior["outcome"])
            state = self.storage.load_state(project_id)
            committed = (
                next(
                    (
                        e
                        for e in self.storage.list_events(project_id)
                        if e.get("request_id") == request_id and e.get("outcome")
                    ),
                    None,
                )
                if prior
                else None
            )
            if committed and operation != "chat:generate" and self.workspace:
                outcome = {
                    "state": ProjectState.model_validate(committed["outcome"]),
                    "workspace": self.workspace(project_id),
                    "message": "Previously committed mutation recovered.",
                }
                kind = payload.get("artifact_id") or payload.get("artifact_type")
                if kind and kind in outcome["state"].artifacts:
                    entry = outcome["state"].artifacts[kind]
                    outcome["artifact"] = self.storage.load_artifact(
                        project_id, kind, payload.get("version") or str(entry.latest_version)
                    )
                assets = self.storage.list_project_assets(project_id)
                saved = next((a for a in assets if a.get("mutation_request_id") == request_id), None)
                if saved:
                    outcome["file_id"] = saved["file_id"]
                prior.update(status="complete", outcome=jsonable_encoder(outcome))
                with self.storage.transaction(project_id):
                    self.storage.save_context_run(project_id, key, prior)
                return outcome
            if (
                (prior is None or operation.startswith("state:"))
                and expected_revision is not None
                and state.state_revision != expected_revision
            ):
                raise StateError("REVISION_CONFLICT", "Reload the latest project", state.state_revision)
            record = {
                "kind": "mutation",
                "request_id": request_id,
                "actor": actor,
                "operation": operation,
                "signature": signature,
                "expected_revision": state.state_revision if expected_revision is None else expected_revision,
                "status": "pending",
            }
            with self.storage.transaction(project_id):
                self.storage.save_context_run(project_id, key, record)
            outcome = handler(
                request_id, state.state_revision if prior or expected_revision is None else expected_revision
            )
            if isinstance(outcome, dict):
                outcome.setdefault("request_id", request_id)
                outcome["mutation_request_id"] = request_id
            retryable = isinstance(outcome, dict) and bool(outcome.get("error") or outcome.get("questions"))
            record.update(status="retryable" if retryable else "complete", outcome=jsonable_encoder(outcome))
            with self.storage.transaction(project_id):
                self.storage.save_context_run(project_id, key, record)
            return outcome
