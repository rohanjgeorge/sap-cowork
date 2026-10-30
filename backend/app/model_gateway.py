"""The only application entry point for model inference."""

import json
from typing import Protocol
from threading import local

from .models import ModelRequest, ModelResponse
from .settings import SettingsService


class ModelProvider(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


class ModelAccessError(RuntimeError):
    pass


class ModelCompatibilityError(ValueError):
    pass


def estimate_tokens(value) -> int:
    """Conservative UTF-8 estimate for cross-provider preflight; telemetry labels it estimated."""
    return max(1, (len(json.dumps(value, ensure_ascii=False).encode("utf-8")) + 2) // 3)


def check_compatibility(request, profile):
    required = request.model_profile
    for capability in ("structured_output", "tool_calling", "vision", "streaming", "reasoning", "coding"):
        needed = required.get(capability, False)
        needed = needed or (
            capability == "structured_output" and request.structured_output_schema is not None
        )
        needed = needed or (capability == "tool_calling" and bool(request.tools))
        if needed and not getattr(profile, capability):
            raise ModelCompatibilityError(f"Model does not support {capability}")
    output = request.generation_settings.get("max_tokens", profile.max_output_tokens)
    if output > profile.max_output_tokens:
        raise ModelCompatibilityError("Requested output exceeds model output limit")
    needed_context = max(
        required.get("context_window", 0),
        estimate_tokens([request.messages, request.context, request.tools, request.structured_output_schema])
        + output,
    )
    if needed_context > int(profile.context_window * 0.95):
        raise ModelCompatibilityError("Task exceeds the safe model context budget")


class FakeModelProvider:
    """Deterministic demonstration output. Never claims to be real model inference."""

    def __init__(self):
        self.calls: list[ModelRequest] = []

    def complete(self, request):
        self.calls.append(request)
        context = request.context or {}
        template = context.get("template", "# Response\n## Result")
        requirement = context.get("requirement", "Connection test")
        facts = context.get("facts", [])
        sections = []
        for line in template.splitlines():
            if line.startswith("#"):
                sections.append(line)
                if line.startswith("## "):
                    sections.append(f"\n{requirement[:600]}\n")
                    if facts:
                        sections.append("\n".join("- " + " ".join(fact.split())[:180] for fact in facts[:3]))
        content = (
            "> Demonstration output from the deterministic fake provider. "
            "Review and replace with BYOK model output for substantive SAP design.\n\n" + "\n".join(sections)
        )
        result = {"content": content, "clarification_questions": []}
        return ModelResponse(
            content=json.dumps(result),
            structured_output=result,
            usage={
                "prompt_tokens": max(1, len(json.dumps(context)) // 4),
                "completion_tokens": len(content) // 4,
            },
            provider="fake",
            model="deterministic-v1",
            status="success",
        )


class LiteLLMProvider:
    def __init__(self, configuration, secrets):
        self.configuration = configuration
        self.secrets = secrets

    def complete(self, request):
        import litellm

        # Keys stay in the adapter invocation. Disable SDK diagnostics and telemetry.
        litellm.suppress_debug_info = True
        litellm.telemetry = False
        config = self.configuration
        key = self.secrets.get(config.credential_reference) if config.credential_reference else None
        if not key:
            raise ModelAccessError("Provider credential is missing")
        prefix = {"qwen": "openai", "openai-compatible": "openai"}.get(config.provider, config.provider)
        model = config.default_model
        if not model.startswith(prefix + "/"):
            model = f"{prefix}/{model}"
        messages = list(request.messages)
        if request.context:
            messages.append(
                {"role": "user", "content": "Task context (source data):\n" + json.dumps(request.context)}
            )
        kwargs = {
            "model": model,
            "messages": messages,
            "api_key": key,
            "timeout": 60,
            "num_retries": 0,
            **request.generation_settings,
        }
        if config.base_url:
            kwargs["api_base"] = config.base_url
        if request.tools:
            kwargs["tools"] = request.tools
        if request.structured_output_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "artifact_result",
                    "strict": True,
                    "schema": request.structured_output_schema,
                },
            }
        try:
            response = litellm.completion(**kwargs)
        except litellm.Timeout:
            raise TimeoutError("Model request timed out") from None
        except Exception:
            # Provider exceptions may contain request headers or credentials.
            raise ModelAccessError("Provider request failed; check configuration and model access") from None
        message = response.choices[0].message
        content = message.content or ""
        try:
            structured = json.loads(content) if request.structured_output_schema else None
        except ValueError:
            raise ModelAccessError("Provider returned invalid structured output") from None
        return ModelResponse(
            content=content,
            structured_output=structured,
            tool_calls=[t.model_dump() for t in (message.tool_calls or [])],
            usage=response.usage.model_dump() if response.usage else None,
            provider=config.provider,
            model=config.default_model,
            status="success",
        )


class ModelGateway:
    def __init__(self, settings: SettingsService, fake=None):
        self.settings = settings
        self.fake = fake or FakeModelProvider()
        self._local = local()

    @property
    def last_response(self):
        return getattr(self._local, "response", None)

    @last_response.setter
    def last_response(self, value):
        self._local.response = value

    @property
    def last_task_id(self):
        return getattr(self._local, "task_id", None)

    @last_task_id.setter
    def last_task_id(self, value):
        self._local.task_id = value

    def complete(self, request: ModelRequest) -> ModelResponse:
        configuration = self.settings.current(request.model_profile.get("policy"))
        check_compatibility(request, configuration.capabilities)
        provider = (
            self.fake
            if configuration.provider == "fake"
            else LiteLLMProvider(configuration, self.settings.secrets)
        )
        for attempt in range(3):
            try:
                response = provider.complete(request)
                self.last_response = response
                self.last_task_id = request.task_id
                return response
            except TimeoutError:
                if attempt == 2:
                    raise ModelAccessError("Provider timed out after three attempts") from None
        raise AssertionError("Unreachable")
