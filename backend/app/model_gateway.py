"""The only application entry point for model inference."""

import json
import math
import os
from typing import Protocol
from threading import local

from .models import ModelRequest, ModelResponse
from .settings import SettingsService


class ModelProvider(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


MODEL_ERROR_MESSAGES = {
    "MODEL_ACCESS_ERROR": "Provider request failed; check provider settings and model access.",
    "PROVIDER_CREDENTIAL_MISSING": "Provider credential is missing. Save your API key in Settings.",
    "PROVIDER_AUTHENTICATION_FAILED": "The provider rejected the API key. Check the saved key in Settings.",
    "PROVIDER_PERMISSION_DENIED": "The provider denied access. Check project permissions and model access.",
    "PROVIDER_MODEL_NOT_FOUND": "The configured model or endpoint was not found. Check model ID and Base URL.",
    "PROVIDER_QUOTA_EXCEEDED": "Provider API quota is exhausted. Check API billing, credits and spend limits.",
    "PROVIDER_RATE_LIMITED": "The provider rate limit was reached. Wait briefly and retry the same task.",
    "PROVIDER_INVALID_REQUEST": (
        "The provider rejected the generation request. Check model support for structured JSON output "
        "and the configured request parameters. A successful connection test does not verify artifact generation."
    ),
    "PROVIDER_CONTEXT_EXCEEDED": "The provider context limit was exceeded. Reduce context or check model limits.",
    "PROVIDER_UNAVAILABLE": "The provider is temporarily unavailable. Retry the same task later.",
    "PROVIDER_CONNECTION_FAILED": "Could not connect to the provider. Check network access and Base URL.",
    "PROVIDER_TIMEOUT": (
        "The provider did not finish within the request timeout. Retry the same task. "
        "Document generation uses one longer attempt to avoid automatically repeating a timed-out request."
    ),
    "PROVIDER_OUTPUT_TRUNCATED": (
        "The provider stopped before completing the document JSON. Review the model output/reasoning "
        "budget or request a shorter document, then retry. No incomplete artifact was saved."
    ),
    "PROVIDER_REFUSAL": "The provider declined this generation request. Review the requirement before retrying.",
    "PROVIDER_INVALID_OUTPUT": "The provider returned invalid or empty document JSON. Retry the same task.",
}


class ModelAccessError(RuntimeError):
    def __init__(self, message="Provider request failed", *, code="MODEL_ACCESS_ERROR"):
        self.code = code if code in MODEL_ERROR_MESSAGES else "MODEL_ACCESS_ERROR"
        self.safe_message = MODEL_ERROR_MESSAGES[self.code]
        # Keep existing callers' exception strings compatible. Only safe_message
        # is permitted across capability/API boundaries.
        super().__init__(message)


def provider_error(exc):
    """Classify allowlisted metadata only; never expose SDK exception text/bodies."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    code = getattr(exc, "code", None)
    if code in ("insufficient_quota", "billing_hard_limit_reached"):
        selected = "PROVIDER_QUOTA_EXCEEDED"
    elif name == "ContextWindowExceededError":
        selected = "PROVIDER_CONTEXT_EXCEEDED"
    elif name == "APIConnectionError":
        selected = "PROVIDER_CONNECTION_FAILED"
    elif status in (401, 403, 404, 429):
        selected = {
            401: "PROVIDER_AUTHENTICATION_FAILED",
            403: "PROVIDER_PERMISSION_DENIED",
            404: "PROVIDER_MODEL_NOT_FOUND",
            429: "PROVIDER_RATE_LIMITED",
        }[status]
    elif status in (400, 422) or name == "UnsupportedParamsError":
        selected = "PROVIDER_INVALID_REQUEST"
    elif isinstance(status, int) and status >= 500:
        selected = "PROVIDER_UNAVAILABLE"
    else:
        selected = "MODEL_ACCESS_ERROR"
    return ModelAccessError(MODEL_ERROR_MESSAGES[selected], code=selected)


class ModelCompatibilityError(ValueError):
    pass


def request_timeout(request):
    if (request.context or {}).get("operation") != "artifact_generation":
        return 60
    try:
        seconds = float(os.getenv("COWORK_ARTIFACT_TIMEOUT_SECONDS", "180"))
        if not math.isfinite(seconds) or not 1 <= seconds <= 600:
            raise ValueError
        return seconds
    except ValueError:
        raise ModelCompatibilityError(
            "COWORK_ARTIFACT_TIMEOUT_SECONDS must be a number between 1 and 600"
        ) from None


def estimate_tokens(value) -> int:
    """Conservative UTF-8 estimate for cross-provider preflight; telemetry labels it estimated."""
    return max(1, (len(json.dumps(value, ensure_ascii=False).encode("utf-8")) + 2) // 3)


def output_limit(request, profile):
    limits = [k for k in ("max_tokens", "max_completion_tokens") if k in request.generation_settings]
    if len(limits) > 1:
        raise ModelCompatibilityError("Specify only one output token limit")
    output = request.generation_settings[limits[0]] if limits else profile.max_output_tokens
    if not isinstance(output, int) or isinstance(output, bool) or output <= 0:
        raise ModelCompatibilityError("Output token limit must be a positive integer")
    if output > profile.max_output_tokens:
        raise ModelCompatibilityError("Requested output exceeds model output limit")
    return output


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
    output = output_limit(request, profile)
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
        if context.get("operation") == "research_selection":
            actions = context.get("permitted_actions", [])
            result = {"action_id": actions[0]["action_id"] if actions else "", "stop": not bool(actions)}
            return ModelResponse(
                content=json.dumps(result),
                structured_output=result,
                provider="fake",
                model="deterministic-v1",
                usage={"prompt_tokens": estimate_tokens(context), "completion_tokens": 30},
                status="success",
            )
        if context.get("operation") == "context_planning":
            needs = []
            if "sto" in context.get("requirement", "").lower():
                needs.append(
                    {
                        "description": "STO process evidence for this change request",
                        "domain": "SAP_FUNCTIONAL",
                        "query": "STO",
                        "user_owned": False,
                        "material": False,
                    }
                )
            result = {"requirements": needs}
            return ModelResponse(
                content=json.dumps(result),
                structured_output=result,
                provider="fake",
                model="deterministic-v1",
                status="success",
                usage={
                    "prompt_tokens": estimate_tokens(context),
                    "completion_tokens": estimate_tokens(result),
                },
            )
        if context.get("operation") == "conversation":
            content = (
                "Demo mode is selected; no live model was called. Select and save a real provider "
                "in Settings to have a model answer your questions. You can still try the "
                "project workflow with Generate BRD, FRD and TDD."
            )
            if context.get("stage_guidance"):
                content = (
                    f"You're now working on {context['stage_guidance']}. "
                    "Demo mode is selected; no live model was called. A saved live provider can review "
                    "your project context and discuss the next step for this stage. "
                    "Your documents, approvals and any pending task are unchanged."
                )
            return ModelResponse(
                content=content,
                provider="fake",
                model="deterministic-v1",
                status="success",
                usage={
                    "prompt_tokens": estimate_tokens(request.messages),
                    "completion_tokens": estimate_tokens(content),
                },
            )
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
        result = {"content": content, "clarification_questions": [], "unmet_context_requirements": []}
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
            raise ModelAccessError("Provider credential is missing", code="PROVIDER_CREDENTIAL_MISSING")
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
            "timeout": request_timeout(request),
            "num_retries": 0,
            **request.generation_settings,
        }
        limit = output_limit(request, config.capabilities)
        kwargs.pop("max_tokens", None)
        kwargs.pop("max_completion_tokens", None)
        limit_parameter = "max_completion_tokens" if config.provider == "openai" else "max_tokens"
        kwargs[limit_parameter] = limit
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
        except Exception as exc:
            # Provider exceptions may contain request headers or credentials.
            raise provider_error(exc) from None
        if not response.choices:
            raise ModelAccessError(
                MODEL_ERROR_MESSAGES["PROVIDER_INVALID_OUTPUT"], code="PROVIDER_INVALID_OUTPUT"
            )
        choice = response.choices[0]
        message = choice.message
        if getattr(choice, "finish_reason", None) == "length":
            raise ModelAccessError(
                MODEL_ERROR_MESSAGES["PROVIDER_OUTPUT_TRUNCATED"], code="PROVIDER_OUTPUT_TRUNCATED"
            )
        if getattr(message, "refusal", None) or getattr(choice, "finish_reason", None) == "content_filter":
            raise ModelAccessError(MODEL_ERROR_MESSAGES["PROVIDER_REFUSAL"], code="PROVIDER_REFUSAL")
        content = message.content or ""
        try:
            structured = json.loads(content) if request.structured_output_schema else None
        except ValueError:
            raise ModelAccessError(
                "Provider returned invalid structured output", code="PROVIDER_INVALID_OUTPUT"
            ) from None
        if request.structured_output_schema and not isinstance(structured, dict):
            raise ModelAccessError(
                "Provider returned invalid structured output", code="PROVIDER_INVALID_OUTPUT"
            )
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
        operation = (request.context or {}).get("operation")
        attempts = 1 if operation in ("context_planning", "research_selection", "artifact_generation") else 3
        for attempt in range(attempts):
            try:
                response = provider.complete(request)
                self.last_response = response
                self.last_task_id = request.task_id
                return response
            except TimeoutError:
                if attempt == attempts - 1:
                    raise ModelAccessError(
                        "Provider timed out after bounded attempts", code="PROVIDER_TIMEOUT"
                    ) from None
        raise AssertionError("Unreachable")
