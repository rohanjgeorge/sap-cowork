# BRD provider failure diagnostics

The reported `Capability execution failed (ModelAccessError)` was produced by a catch-all runtime handler that discarded the provider failure category. This made the displayed message insufficient to identify the cause of a real failed request.

The model adapter now classifies allowlisted status/code metadata into safe application errors: missing credential, rejected authentication, denied access, missing model/endpoint, quota, rate limiting, invalid request, context overflow, provider availability/connectivity, and bounded timeout. It distinguishes truncated generation, refusal and malformed document JSON before registering any artifact. The current and retained legacy runtimes return the safe reason and machine-readable `error_code`; arbitrary worker/SDK exception text stays hidden. Raw messages, headers, keys and generated/source content are not added to errors or logs.

Eleven new offline acceptance cases in `backend/tests/test_provider_errors.py` reproduced the missing classification/propagation before implementation. They test seven provider status/code cases, three structured-response cases, and a failed BRD that remains failed with no artifact and no leaked secret. Existing adapter sanitization and runtime parity tests remain required.

Read-only diagnosis of the local default configuration found OpenAI selected, a configured model ID of `gpt-6.1-sol`, the default endpoint, and an available OS-keyring credential. The saved connection status was connected. The key value was never displayed or written to a report. No saved settings, credentials or user projects were changed, and no live model call was made.

The exact cause of the previously failed provider request cannot be reconstructed from the discarded error. A basic connection test uses a short text request; artifact generation uses structured JSON and a larger prompt. OpenAI documents unsupported strict schemas and incomplete/refused output as separate failure cases: https://developers.openai.com/api/docs/guides/structured-outputs . These are possible categories, not a finding about this user's failed call.

After restarting the backend, retry the same failed BRD request from the UI. If the provider still fails, the new error gives the category and next action. This change does not assert that billing, model permissions, network access or the provider-side request has been verified successfully.

Files changed: `backend/app/model_gateway.py`, `backend/app/langgraph_orchestrator.py`, `backend/app/legacy_orchestrator.py`, and new `backend/tests/test_provider_errors.py`. Full release evidence is in `docs/TEST_RESULTS.json`; results are appended after verification.

Final verification (2026-11-03T05:30:37.553577+00:00): 218 backend/CLI tests, 36 UI tests, 9 browser experience tests and 1 final STO test passed. Lint, formatting, TypeScript/production build and dependency audit passed. The seven existing non-failing LangGraph durability warnings remain. Verification used mocks/demo providers and temporary project data, not a real OpenAI generation request. No commit or push was performed.
