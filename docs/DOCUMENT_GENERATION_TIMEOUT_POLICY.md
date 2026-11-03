# Document generation timeout policy

The live BRD error identified a provider timeout. Inspection found the adapter hard-coded to 60 seconds per call, while ModelGateway retried normal document requests up to three times. A document that needs longer than 60 seconds could be interrupted and restarted three times instead of receiving one longer response window. This finding does not establish why the remote request was slow, or guarantee completion within a larger window.

Shared artifact-worker requests now identify their operation as `artifact_generation`. The provider adapter allows these requests 180 seconds by default. ModelGateway makes one attempt for this operation and leaves SDK retries disabled, avoiding automatic duplicate generation calls after a timeout. Explicit user retry retains the existing task identity and recovery safeguards. Ordinary chat retains its previous 60-second default and retry policy; planning/research attempt limits and explicit request timeouts remain unchanged. No model, reasoning setting, credentials, schema, artifact acceptance rule or saved provider setting is changed.

Set `COWORK_ARTIFACT_TIMEOUT_SECONDS` in the server's environment before startup to adjust the document timeout (1–600 seconds, finite numbers only). For example, from PowerShell in the repository root:

```powershell
$env:COWORK_ARTIFACT_TIMEOUT_SECONDS = '240'
.\start.ps1
```

An unset variable uses 180 seconds. Invalid values fail before provider invocation. This controls the provider-request timeout, not an end-to-end task deadline including context planning and persistence. No monetary routing, fallback provider or automatic model substitution was added.

Tests: `backend/tests/test_model_timeout_policy.py` has eight offline cases: document timeout, environment override while retaining planning/chat limits, one provider attempt on document timeout, shared-worker operation tagging, and four invalid configuration values. The first four failed before the implementation; all eight now pass. Existing provider-error, adapter and worker tests also pass. Test stubs use no API calls and do not simulate actual wall-clock provider performance.

Changed application files: `backend/app/model_gateway.py` and `backend/app/artifact_worker.py`. Prior safe provider-error reporting is retained. A timed-out request does not create an incomplete artifact. The exact upstream latency/network cause still requires a live retry; no paid model call was made for development verification.

Reference: OpenAI's latency guidance explains that generated output and request design affect response latency: https://developers.openai.com/api/docs/guides/latency-optimization . This supports allowing sufficient generation time but does not diagnose this particular provider request.

Full release results are recorded in `docs/TEST_RESULTS.json`; the STO scenario remains the last gate.

Final verification (2026-11-03T06:10:31.892069+00:00): 226 backend/CLI tests, 36 UI tests, 9 browser experience tests and the final STO scenario passed. Lint, formatting, production build and dependency audit passed. Seven existing non-failing LangGraph durability warnings remain. The verified local server was restarted after confirming no active generation. No live model generation request, credential/settings change, commit or push was performed.
