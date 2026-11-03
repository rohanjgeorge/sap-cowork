# V1.1 conformance decisions implementation

This update applies the decisions supplied after the consolidated-requirements comparison. It corrects behavior while retaining the existing parent event graph, checkpointed task graph, native Context Planning, local persistence, ModelGateway, capability registry and replaceable ABAP interface. Existing projects are read without a destructive schema migration.

## Disposition by finding

| Finding | Status | Implemented behavior |
| --- | --- | --- |
| G01 mutation semantics | Fixed | Application mutations capture a server-owned local actor, request ID and evaluated state revision. A durable mutation ledger checks payload identity, serializes external project mutations and replays completed outcomes. Chat, strict state operations, edits, uploads/deletes, metadata, reviews, confirmations/withdrawals, close/reopen, follow-up retries and source-update review use the contract. Creation accepts a retry ID and deduplicates it; omitted IDs are generated. Explicit stale revisions remain rejected. |
| G02 generation identity | Fixed | Generation identities persist normalized material request signatures separately from checkpoints. The signature includes capability/type, generation/revision intent, instructions, explicit upstream refs, model policy and requested options; runtime IDs and expected revisions are excluded. Changed payloads require a new task ID. Durable artifact commit records still support saved-output registration recovery without another generation. |
| G03 blockers | Fixed | Central deterministic eligibility handles blocking issues and active blocker flags for generation, completion confirmation and closure. Artifact/stage/capability scopes are honored. Status/guidance and navigation remain allowed. Warning/exception flags and the unapproved-TDD ABAP error remain non-blocking. Blocked JSON/SSE responses carry structured reason data. |
| G04 Testing completion | Fixed | Current SIT and UAT must be approved before confirmation. Confirmation retains version IDs, content hashes, actor/time, remarks and optional evidence references. Testing completion requires an applicable active confirmation and approved current SIT/UAT. Changed baselines and withdrawals invalidate completion while preserving history. |
| G05 output contracts | Fixed | Validation consults the capability registry's declared artifact/result contract. Artifact-producing capabilities cannot succeed without their artifact; they fail with `OUTPUT_CONTRACT_FAILED` before registration. Non-artifact tools can return a legitimate result without an artifact. |
| G06 complete package budget | Fixed | Selection accounts for serialized metadata as well as passages. Oversized optional detail is compacted into a reference to the full external Gap Report, evidence is removed where necessary, and the entire final package is re-estimated. If mandatory overhead still cannot fit, `context_budget_exceeded` is returned and no oversized package or artifact is saved. |
| G07 runtime compatibility projections | Intentionally accepted; authority handling corrected | Runtime-related ProjectState fields remain for compatibility. Valid checkpoint waits determine interruption/resume, and durable generation/commit ledgers determine identity/replay/recovery. Stale status/task projections are synchronized through StateManagementService. No-checkpoint and older-record cases retain a controlled projection fallback. See the compatibility notes below. |
| G08 compact worker view | Fixed | Registry invocation supplies a frozen `TaskProjectView`, with task-relevant artifact refs, decisions, clarifications, flags and completion information. It excludes completed-task mappings and unrelated state. Nested task options are immutable. Legacy ProjectState inputs are accepted by adapters and narrowed; the shared worker also adapts direct legacy callers. Model prompts retain only relevant facts. |
| G09 SAP applicability | Fixed | Explicit project target metadata takes precedence. A trusted adapter binding must be registered at the composition boundary, scoped to a project/organization and currently authorized. A release in retrieved evidence alone does not establish the project's product/deployment/release. Effective intervals are checked against the persisted plan's task date, project context date or current time. Missing validity remains qualified, rather than invented. |
| G10 evidence trace/assumptions | Fixed | Each discovered action has a requirement mapping and a trace of execution, evidence and failure. Actual attempts are distinct from planned/unexecuted sources, including permission denials before retrieval. Evidence deduplication retains contributing action references. The API/CLI context report and UI expose the trace. Assumptions are populated from explicitly qualified inference, never manufactured from missing items. |
| G11 project metadata | Fixed | UI creation and workspace editing expose optional organization/program and SAP product, deployment, release, system and client fields. CLI `projects create` accepts the same metadata and `projects metadata` edits it through the shared revision-checked backend operation. No Program-management subsystem was introduced. |

## Compatibility and migration decisions

The ProjectState schema keeps `active_task_id`, `task_status`, active capability, task inputs and completed-task mappings as compatibility/status projections. No field was removed and prior project JSON remains readable. `awaiting_approval` can still appear in the UI projection after a task graph has finished; it is not a live approval interrupt.

Where a valid checkpoint exists, clarification routing and resumption inspect it, validate its project/task/type correlation, and repair stale projections through the single writer. A completed generation's external commit record is consulted before the old completed-task map. The map remains a recovery fallback for older projects with no new records. Pre-migration waits without checkpoints may still resume through the existing compatibility path; older checkpoints without a generation ledger use the correlated persisted task projection as a controlled adoption fallback.

Remaining projection use is explicit: internal transition/status reporting, task preflight, construction of the compatibility task view, and revision/correlation checks still use ProjectState projections populated by the active invocation. This update does not redesign the application for concurrent independent generation tasks inside one project or remove those fields. It does not make a projection a replacement for a valid resumable checkpoint.

StorageProvider gains a project mutation-lock operation, implemented locally with a separate cross-process file lock. This is distinct from the short state-commit lock and the generation execution lock. Mutation outcomes, generation identities and artifact commit records are durable project resources under `context/runs/`; none is a LangGraph checkpoint containing document bodies.

Automatically generated request IDs do not let a server identify two separately submitted requests as the same user intent. Clients wanting an explicit retry use the original request/task ID; the UI's existing task IDs and strict state-operation IDs remain compatible. Changing material generation instructions requires a new task ID.

Failed generation outcomes and clarification waits are not cached as completed mutations. An identical retry can therefore recover/resume instead of replaying a permanent failure or stale question. Omitted optional values and explicitly supplied defaults normalize equivalently. Automatic chat revisions are captured from the state used to evaluate the action, before execution is serialized.

## Ratified engineering choices

The parent event graph remains non-checkpointed and continues to delegate existing application services. The task graph remains checkpointed; Context Planning remains native LangGraph. Maintenance operations may use direct application-service paths. No graph was refactored merely to resemble a diagram.

Artifact profiles remain versioned. Artifact type, template reference, generation instructions and profile version drive task behavior/metadata. The context requirement profile, named validation profile, expected-result identifier and revision-behavior text describe the selected V1.1 contracts; they do not dynamically load plugins. The registry/validation and lifecycle services enforce the actual output and revision rules.

Defaults remain two retrieval attempts, twelve actions, ten seconds of planning budget, 5,000 estimated package tokens, two worker replans and thirty-day freshness review. Model capability profiles remain configuration-driven. There is no new monetary/project-wide cost control, dynamic model discovery, routing optimization or failover.

The current local evidence representation and controlled copy/review behavior remain. No full knowledge catalog, organization/global publication, live SAP/ADT/Notes/ATC integration, enterprise SSO/tenant isolation, production ABAP generator, deep SAP correctness certification, advanced Word fidelity, distributed checkpointer or Deployment/Maintenance workflow was added.

## Files changed in this pass

New application modules: `backend/app/mutations.py`, `generation_identity.py` and `eligibility.py`.

Backend changes: `models.py`, `api.py`, `services.py`, `state_management.py`, `artifact_lifecycle.py`, `langgraph_orchestrator.py`, `clarifications.py`, `capabilities.py`, `artifact_worker.py`, `hooks.py`, `runtime.py`, `context_planning.py`, `context_sources.py`, `storage.py` and `local_storage.py`. These implement the contract, guard, baseline, view, evidence and compatibility changes above.

Client changes: `cli/main.py`; `frontend/src/ProjectMetadata.tsx` (new), `ProjectHome.tsx`, `Workspace.tsx`, `ContextEvidence.tsx`, `types.ts` and the project-action dropdown styling in `styles.css`. Metadata editing uses the existing Project actions menu so mobile header controls remain accessible.

Tests/reports: `backend/tests/test_conformance_decisions.py` and `frontend/src/ProjectMetadata.test.tsx` are new; the existing context-planning, capability-isolation and clarification regression fixtures were updated to satisfy the newly required contracts. This report and the consolidated review/evidence files record the disposition.

## Acceptance and regression evidence

The initial new acceptance run recorded thirteen failures and one already-passing strict mutation case. Later focused creation, UI metadata and discovery-denial cases also failed before their fixes. The new backend acceptance module now covers all decided findings, including stale requests and replay, upload/edit/delete deduplication, memory-failure edit recovery, scoped blockers, Testing approvals/hash changes/withdrawal, missing outputs, 1,000-token and minimum-overhead cases, effective dates, trusted target binding, unexecuted sources, explicit inference, immutable views, stale runtime projections, metadata parity and upstream-version identity.

Additional regression checks cover transient generation retries, omitted-versus-explicit default normalization, compact ordinary-conversation prompts, and late UI responses after navigation. Conversation context no longer serializes full execution projections into model input. Leaving a workspace remains available while a request runs; a late response cannot reopen it.

Existing successful-source fixtures now register an explicit trusted target binding. The multiple-clarification fixture now returns a real valid artifact instead of artifact-free success, retaining its no-premature-resume and call-count assertions. The capability-isolation test now asserts that attempted mutation is rejected by the frozen view. These are stronger checks for deliberately changed contracts; no failure assertion was removed to hide a regression. The existing exact UI creation-payload test was preserved: optional untouched metadata is omitted from that request.

The full release result is recorded below and in `TEST_RESULTS.json` / `python-tests.xml`. The STO journey ran as the final automated gate.

## Final release result

Verified 2026-11-03 03:00:07 IST using `COWORK_E2E_PORT=8001 .venv/Scripts/python.exe scripts/verify.py`. All eight required release steps passed:

| Check | Result |
| --- | --- |
| Python lint and formatting | Passed |
| Backend and CLI | 194 passed |
| UI unit and interaction | 22 passed |
| TypeScript and production build | Passed |
| Frontend dependency audit | 0 vulnerabilities |
| Browser experience | 4 passed |
| **Final STO end-to-end gate** | **1 passed, executed last** |

The new acceptance coverage comprises 30 backend cases and 3 UI metadata/navigation cases. The full run retains seven existing non-failing LangGraph warnings about durability on subgraphs without a checkpointer; these do not change the checkpointed task runtime or its pause/resume tests. Browser execution also emits the existing color-environment warning. No paid model requests, live SAP integrations, user-credential changes or destructive project migrations were needed.

No unresolved material deviations were found within the agreed scope. Deferred capabilities and accepted compatibility choices remain as listed above. No commit or push was performed.
