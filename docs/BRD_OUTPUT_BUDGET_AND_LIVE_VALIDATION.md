# BRD output budget and live validation

The approved minimal OpenAI diagnostic used no project content, a 256-output-token cap, a 30-second timeout and zero retries. It completed successfully in 8.73 seconds (42 prompt tokens, 12 completion tokens). This verified a small request through the configured adapter; it did not verify full BRD generation.

Read-only reconstruction of a failed BRD prompt found approximately 14,400 estimated request tokens, including roughly 6,200 tokens of workflow/clarification records, and no generation output limit in the outgoing request settings. The gateway previously checked the configured output cap but did not forward a default cap to the provider.

The gateway now sends the configured default limit to the provider, using max_completion_tokens for OpenAI and max_tokens for other configured providers. Both forms are checked in compatibility preflight; ambiguous dual limits, invalid values and overrides exceeding the configured cap are rejected. Explicit smaller limits are preserved without mutating the request. The artifact prompt omits clarification runtime IDs/timestamps, groups identical facts while preserving all references, retains distinct answers/conflicts, and requests concise sections under every template heading. Domain records remain intact.

The separately approved BRD validation sent stored project context with an explicit 4,096-token cap, 180-second timeout and zero retries. It received a provider result in 76.2 seconds but stopped at the output budget before completing document JSON (PROVIDER_OUTPUT_TRUNCATED). No incomplete artifact was registered or approved. This establishes output-budget exhaustion for that bounded validation; it does not establish successful full BRD generation.

The user subsequently asked about a 64,000-token ceiling. The saved OpenAI configuration was observed at 64,000 during that discussion; this agent did not raise it. No live 8,192- or 64,000-token validation was authorized or executed by this agent. Approval for the earlier tiny and 4,096-token probes does not authorize further paid requests.

Nine new cases in backend/tests/test_model_output_budget.py cover outbound limits, modern parameter preflight, explicit overrides, generic-provider compatibility and clarification grouping/conflict preservation. The initial run had six failures and two already-passing cases before implementation. Twenty-seven focused budget/adapter/timeout/worker checks subsequently passed.

Full release verification: 235 backend/CLI tests, 36 UI tests, 9 browser tests and 1 STO test passed, with STO executed last. Lint, formatting, production build and dependency audit passed. Seven existing non-failing LangGraph warnings remain. See TEST_RESULTS.json.

Code changes: backend/app/model_gateway.py, backend/app/artifact_worker.py; new backend/tests/test_model_output_budget.py. No model substitution, automatic retry expansion, credential change or destructive project mutation was made. The latest code still needs a server restart before the running server uses it.

References:
- [OpenAI Chat Completions parameters](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create): max_completion_tokens includes visible output and reasoning tokens.
- [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol): current output limit and pricing.

Verified release completion: 2026-11-03T06:53:55.025872+00:00

The user subsequently selected 16,384 output tokens. The saved OpenAI configuration was updated from 64,000 to 16,384, verified by reloading it, and the local server was restarted after confirming no active generation. The health endpoint passed. No additional paid generation was made.
