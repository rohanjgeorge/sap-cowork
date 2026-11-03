"""Output budgets must constrain real provider requests as well as preflight."""

from types import SimpleNamespace
import pytest
from backend.app.model_gateway import ModelCompatibilityError, check_compatibility
from backend.app.models import ModelRequest, ModelProfile
from test_provider_errors import adapter


def test_openai_default_output_budget_is_sent_to_provider(monkeypatch):
    captured = []

    def complete(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK", tool_calls=[]))], usage=None
        )

    provider = adapter(monkeypatch, complete)
    provider.configuration.capabilities.max_output_tokens = 4096
    provider.complete(ModelRequest(task_id="t", messages=[]))
    assert captured[0]["max_completion_tokens"] == 4096
    assert "max_tokens" not in captured[0]


@pytest.mark.parametrize(
    "settings",
    [
        {"max_completion_tokens": 8192},
        {"max_tokens": 8192},
        {"max_tokens": 128, "max_completion_tokens": 256},
        {"max_completion_tokens": 0},
        {"max_tokens": True},
    ],
)
def test_output_override_cannot_bypass_configured_limit(settings):
    with pytest.raises(ModelCompatibilityError):
        check_compatibility(
            ModelRequest(task_id="t", messages=[], generation_settings=settings),
            ModelProfile(max_output_tokens=4096),
        )


def test_explicit_smaller_completion_budget_is_preserved(monkeypatch):
    captured = []
    provider = adapter(
        monkeypatch,
        lambda **kwargs: (
            captured.append(kwargs)
            or SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK", tool_calls=[]))], usage=None
            )
        ),
    )
    request = ModelRequest(task_id="t", messages=[], generation_settings={"max_completion_tokens": 256})
    provider.complete(request)
    assert captured[0]["max_completion_tokens"] == 256
    assert request.generation_settings == {"max_completion_tokens": 256}


def test_generic_provider_retains_compatible_max_tokens_parameter(monkeypatch):
    captured = []
    from test_provider_errors import adapter

    provider = adapter(
        monkeypatch,
        lambda **kwargs: (
            captured.append(kwargs)
            or SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK", tool_calls=[]))], usage=None
            )
        ),
    )
    provider.configuration.provider = "openai-compatible"
    provider.complete(ModelRequest(task_id="t", messages=[]))
    assert captured[0]["max_tokens"] == 4096
    assert "max_completion_tokens" not in captured[0]


def test_compact_clarifications_preserve_distinct_answers_and_all_references():
    from backend.app.artifact_worker import clarification_facts
    from backend.app.models import Clarification

    first = Clarification(
        clarification_id="a",
        question="Which plant?",
        status="resolved",
        resolution="1000",
        related_artifact="BRD",
    )
    repeat = first.model_copy(update={"clarification_id": "b", "task_id": "another-runtime"})
    conflict = first.model_copy(update={"clarification_id": "c", "resolution": "2000"})
    rows = clarification_facts([first, repeat, conflict], "BRD")
    assert len(rows) == 2
    assert rows[0]["resolution"] == "1000" and rows[0]["clarification_refs"] == ["a", "b"]
    assert rows[1]["resolution"] == "2000"
    assert "task_id" not in rows[0] and "created_at" not in rows[0]
