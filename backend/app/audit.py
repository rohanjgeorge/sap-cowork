"""Allowlisted execution telemetry. Never records prompts, file contents or credentials."""

import json
import logging
from time import monotonic

from .models import now

LOGGER = logging.getLogger("cowork.audit")


class AuditObserver:
    def __init__(self, storage, gateway, context_handler):
        self.storage = storage
        self.gateway = gateway
        self.context_handler = context_handler
        self.starts = {}

    def __call__(self, state, event):
        task = state.active_task_id
        key = (state.project_id, task)
        self.starts.setdefault(key, monotonic())
        request = next(
            (
                r
                for r in reversed(self.context_handler.requests)
                if r.task_id == task and r.project_id == state.project_id
            ),
            None,
        )
        model_response = self.gateway.last_response if self.gateway.last_task_id == task else None
        record = {
            "timestamp": now().isoformat(),
            "project_id": state.project_id,
            "task_id": task,
            "capability_id": state.active_capability_id,
            "kind": event.get("kind"),
            "task_status": state.task_status.value,
            "provider": model_response.provider if model_response else None,
            "model": model_response.model if model_response else None,
            "context_domains": [d.value for d in request.required_domains] if request else [],
            "artifact_id": event.get("artifact_id"),
            "duration_ms": round((monotonic() - self.starts[key]) * 1000),
            "usage": model_response.usage if model_response else None,
            "outcome": event.get("outcome", state.task_status.value),
            "error_category": "execution_failure" if state.task_status == "failed" else None,
        }
        self.storage.append_event(state.project_id, record)
        LOGGER.info(json.dumps(record))
