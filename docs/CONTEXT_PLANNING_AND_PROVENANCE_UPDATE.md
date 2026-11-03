# Context planning and source provenance update

Sources reviewed: `Project Management/V1.1/Behaviour/Context Planning LangGraph.docx` and `Context Sources & Provenance.docx`, alongside the four existing behavior specifications. Document content was treated as product requirements, not instructions to operate this computer or publish information.

## Implemented behavior

The existing orchestrator API now calls a native LangGraph context-planning subgraph. It defines task requirements, discovers authorized sources, plans and retrieves evidence, evaluates gaps, routes bounded retries/research/clarifications, and assembles a task-specific package. Native interrupts pause material user-owned questions; restart resumes without repeating completed planning-model calls. Worker-reported unmet requirements trigger targeted replanning with a finite limit. Missing or unapproved upstream documents remain non-blocking qualifications, including ABAP generation from an in-progress TDD.

Fixed requirement profiles for all eight artifact types live in `context_profiles/v1.json`. ModelGateway can add structured task-specific requirements without deleting fixed needs or changing authorization. Templates remain the existing current editable files; each plan records the template filename and content digest.

Source metadata separates category (SRC-01 through SRC-09), domain, scope, original identity, acquisition mechanism, version, applicability, authority, evidence status and access rights. Cached SAP references cannot establish that a custom object exists in a customer's target system. Registered adapters must provide current authorization and target-system evidence for that claim.

Organization knowledge is copied into project storage with lineage and snapshots. Verified formatting-equivalent changes can be adopted automatically. Material, uncertain or customized changes require review of a concrete comparison; acceptance checks a fingerprint to reject stale comparisons. Revocation is enforced during selection and report reads, including tracked memory and artifact derivatives. Approved artifact files are retained unchanged.

The UI context panel and CLI expose plans, gaps, original sources, adapter availability and source-update comparisons. Artifact records retain the plan/package references and evidence provenance. Source catalogs distinguish reference websites from configured connections.

## File and function mapping

| Existing entry point | New implementation |
| --- | --- |
| Parent context-loading phase | `langgraph_orchestrator.start_context_planning` → `plan_context` |
| `ContextPlanner.plan` | Compatibility domain planning retained; `requirements` and `reason` define profile and additive needs |
| `ContextHandler.load` | Authorized local discovery used by `discover_sources` |
| Direct context loading before a worker | `define_requirements` → `discover_sources` → `plan_retrieval` → `retrieve_context` → `evaluate_context` |
| Context-related clarification handling | `route_gaps` → `prepare_clarification` → native `request_clarification` interrupt → `resume_planning` |
| Context-package assembly | `assemble_context` → `return_context` |
| Worker missing-context result | Structured `context_required` → targeted planning cycle |
| Curated SAP lookup | Same capability interface, with source-policy filtering and provenance |
| StorageProvider | Additional context-run/copy methods; LocalStorageProvider stores JSON under each project's `context/runs/` |

The legacy orchestrator remains available as a parity reference. UI/CLI workflow entry points, ModelGateway, capability registry and replaceable ABAP interface retain their roles.

## Assumptions and engineering choices

1. Profiles are versioned at 1.0. The newer planning document's template-version language is interpreted as profile versioning plus a template digest, preserving the specific artifact specification's single current editable template.
2. Defaults per planning cycle: two retrieval attempts, twelve actions, ten seconds, 5,000 estimated package tokens and one planning-model request. At most two worker-triggered replans are allowed. A planning-model failure falls back to fixed requirements with an explicit qualification.
3. Candidate storage is bounded to 32 passages of at most 6,000 characters; worker excerpts are at most 1,800 characters and constrained by the package token estimate. Full gap reports and selected evidence live behind StorageProvider; checkpoints contain identifiers, references and counters rather than document bodies.
4. Independent retrieval runs concurrently only when both the action and adapter declare it safe. Stable identity/version/content hashes deduplicate evidence; merge order is deterministic. Adapter calls receive a timeout and must cooperate with it; timed-out results are not merged.
5. Thirty days is the initial evidence-freshness review threshold. Unknown release, authority or verification is qualified rather than silently treated as confirmed. Material requirements that demand authoritative verification can escalate instead of generating unsupported content.
6. Conflict evaluation detects explicit disputes, divergent snapshots and contradictory structured facts. It does not claim comprehensive semantic contradiction detection or SAP correctness validation.
7. Automatic low-risk adoption is deliberately narrow: verified formatting-equivalent text, unchanged applicability and no project customization. Other changes require review. Rejected/pending updates are deduplicated; source changes never silently rewrite approved artifacts.
8. Permissions use the existing authenticated local user plus known tenant, organization, project, publication and adapter metadata. This is not a new enterprise IAM system. Tracked derivatives are rechecked against original sources; legacy untracked material is conservatively omitted when stored sources are denied.

## Integration boundaries

The subsequent [Parent orchestration and capability update](PARENT_ORCHESTRATION_UPDATE.md) adds a bounded Research subgraph and a structured Audit subgraph. The connector boundaries below still apply.

No SAP/ADT, enterprise search, live web research or organization catalog connection is enabled automatically. The source-adapter interface and bounded research route are implemented; real connectors, credentials, enterprise authorization, indexing, publication workflows and licensing enforcement require their own integrations. Unconfigured sources are reported honestly. Project learning remains project-scoped.

Tests use isolated data and deterministic/mocked model providers. No paid OpenAI request or credential change is needed for verification. Final release evidence is recorded in `TEST_RESULTS.json` and `python-tests.xml`; the release script runs the STO browser scenario last.

## Verification results

Verified 2026-11-03 (local time): **143 backend/CLI tests, 19 UI tests, four browser experience tests and the final STO gate passed**. Python lint/format checks, dependency consistency, TypeScript/production build and frontend audit passed; the audit reported zero vulnerabilities. One new UI test's exact text matcher was corrected before the complete UI suite and subsequent gates were rerun. No backend implementation changed after its passing full suite.

Coverage includes native subgraph restart/resume, reference-only checkpoints, parallel retrieval/deduplication, bounded deadlines, targeted worker replanning and exhaustion, target-system evidence requirements, source conflicts, comparison-based source review, revoked report evidence and revoked memory/artifact derivatives. The STO test additionally checks the paused context plan and structured clarification gap before completing the full business journey.
