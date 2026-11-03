# Parent orchestration update

The new `Project Management/V1.1/Behaviour/LangGraph Orchestration.docx` specifies the parent event flow above the context-planning subgraph implemented in the previous update. `Capabilities Agents and Workers.docx`, added during this review, defines the worker, research, audit and service boundaries. This change implements those boundaries, adds shared intent routing and authorization, ends new generation runs without an approval interrupt, strengthens execution/output checks, and makes artifact registration recoverable without repeating generation. Source documents were read as product specifications; their content was not executed as computer instructions.

## Implemented changes

Requests from the existing chat, review, state-operation, upload and edit endpoints now pass through a finite parent event graph. It loads project truth, normalizes and classifies the request, authorizes it, routes the operation, and refreshes the status projection. Existing service operations perform the domain work, memory updates and response construction. UI and CLI payloads remain compatible. Direct generation remains available through the typed orchestrator API; direct reviews also use the event graph through the approval adapter.

Interpretation and classification do not write ProjectState. Unknown actions, non-user actors, missing review targets and closed-project mutations are rejected before the action handler runs. A review resolves one exact artifact version. Navigation and status commands remain usable during a clarification wait and do not answer the pending question or generate an artifact.

Generation resolves the capability, checks structural preconditions and enters the existing native context-planning subgraph. Execution-time guardrails recheck project/task correlation, capability configuration, blocking conditions and current source rights. The permission check now includes project-local curated sources revoked after package assembly, in addition to organization copies and tracked derivatives.

Worker invocation and result inspection are separate nodes. Successful outputs are checked for task/capability/project/type correlation, nonempty content, current application-template metadata and heading order, and known source references before persistence. Unresolved package gaps are visibly attached as qualifications and retained in artifact metadata. ABAP retains its module-owned output format. These checks do not establish business or SAP semantic correctness.

Saving, registration and impact assessment are separate durable steps. The validated document and its recovery record are committed in one storage transaction. If registration fails, the document survives. Retrying the same task after restart uses its stable artifact/version and content digest to reconcile registration and impact without another model call or duplicate version. A changed saved output produces an error requiring reconciliation. ProjectState writes still go through StateManagementService.

New generation checkpoints finish after persistence and response preparation. The domain may still report `task_status=awaiting_approval` for UI/CLI compatibility; that does not mean LangGraph is paused. Approval is a separate user event. The former `await_approval` node remains only to acknowledge pre-update checkpoints, and its acknowledgement recovery is tested.

## Function and node mapping

| Previous path | Current parent node or operation |
| --- | --- |
| Chat-specific text parsing in `ApplicationService.chat` | `ParentEventGraph.understand_request` → `classify_intent` using `normalize_request` |
| Per-endpoint dispatch | `load_project` → `authorize_action` → `route_intent` |
| Stage navigation / status | `navigate_stage` / `project_guidance`, delegating to existing service operations |
| Generation request | Parent `resolve_task` → existing typed execution API → `understand_task` → `check_task_preconditions` |
| Context loading | Existing `start_context_planning` → native `plan_context` subgraph |
| Execution checks | `before_execute` with expanded `GuardrailHook.before_execute` |
| Combined worker invocation and inspection | `execute_capability` → `inspect_worker_result` |
| Minimal result check | `validate_result` with expanded `ValidationHook.after_execute` |
| Combined artifact persistence/registration | `persist_output` → `register_artifact` → `assess_change_impact` → `persist_and_continue` |
| `ArtifactLifecycle.persist` | Compatibility wrapper over `save_output` and `register_output` |
| Retry after a registration failure | `_recover_output`, using a stable external artifact-commit record |
| Generation's approval interrupt | Generation ends; separate review event invokes the approval service; legacy wait acknowledgement retained |

## Assumptions and decisions

1. **Compatibility boundary:** The parent event graph coordinates the existing task execution graph through its public APIs. The task graph continues to own checkpointed pause/resume and contains the native context-planning subgraph. The parent event graph has no checkpointer. Request bodies, callbacks, uploads and response objects stay in invocation context, outside checkpoint channels.
2. **Intent taxonomy:** The document's finite intents are implemented. Requirement capture and administrative project operations retain explicit compatibility intents because existing UI/CLI endpoints use them. Later handlers receive normalized actions and references rather than reparsing conversational text. The compatibility service retains a normalization call for the legacy runtime, whose implementation is preserved.
3. **Conflicting revision rules:** The specific Artifacts & Templates specification explicitly requires changes to an existing Draft to stay in that version by default. That rule is retained despite the conceptual orchestration document's simplified rejection/revision flow. Request Changes records feedback; a later explicit generation executes the revision. Approved edits always fork a Draft. Explicit new-version requests require authors and remarks. The word “revise” alone does not silently opt into a new version or invent author metadata.
4. **Memory and responses:** Existing domain services remain responsible for meaningful memory updates and user response construction. The parent terminal nodes coordinate completion and status refresh; they do not duplicate those writes. Read-only guidance does not invoke a worker. Ordinary conversation retains the user's configured model behavior.
5. **Recovery:** Artifact-commit records use the existing StorageProvider context-run persistence seam under each project's `context/runs/`, with `kind=artifact_commit`. They hold identifiers, a digest, phase and impact requirement, not another copy of ProjectState. Reconciliation requires retrying the original task ID, or the existing explicit artifact-reconciliation operation.
6. **Approval compatibility:** Domain status remains `awaiting_approval` after generation so existing clients keep working. The runtime cursor is complete. Old approval waits can still be acknowledged after a committed review, and a checkpoint acknowledgement failure cannot undo the approval.
7. **Validation scope:** Structural and source-link checks are enforced for generated application documents. ABAP formatting belongs to the replaceable ABAP interface. Deep SAP accuracy, arbitrary semantic consistency and enterprise policy validation still require their dedicated integrations.
8. **Existing boundaries:** Local user authorization is retained; enterprise IAM is not inferred from organization identifiers. No SAP/ADT/research connection, publication, credential change, paid model call, Git commit or push is performed by this update. The legacy orchestrator and existing user template edits remain available.

## Verification

The added acceptance tests cover authorization before handler execution, navigation during clarification, separate exact-version approval, invalid worker output before saving, source revocation between planning and execution, closed-project mutation rejection, and restart recovery without regeneration. Existing native context pause/resume, targeted replanning, legacy parity and old approval-wait recovery remain in the regression suite.

The complete release pipeline runs Python lint/format checks, backend/CLI tests, UI tests, TypeScript/production build, dependency audit and browser scenarios, with the STO journey last. Final results are recorded in `TEST_RESULTS.json` and `python-tests.xml`.

Verified 2026-11-03 local time: **164 backend/CLI tests, 19 UI tests, four browser experience tests and the final STO gate passed**. Python lint/format checks, dependency consistency, TypeScript/production build and frontend audit passed; the audit reported zero vulnerabilities. The STO journey exercised native clarification/resume, replaceable ABAP invocation, explicit code/testing confirmation, the new Audit subgraph and completed project closure. No required test is failing.

## Capability architecture additions

BRD, FRD, User Stories, TDD, SIT and UAT continue to share one ArtifactWorker. Versioned `ArtifactTaskProfile` definitions now live in `artifact_profiles/v1.json`, including generation instructions, template reference, context profile, output contract, validation profile and revision policy. Artifacts record their task-profile reference/version. Application templates remain current editable files, separately identified by filename and the context plan's digest.

Generation-worker questions are converted into material user-owned unmet-context requirements. The parent re-enters Context Planning, which owns the native clarification interrupt; the worker neither retrieves evidence nor pauses the user independently. Legacy clarification status remains accepted for compatibility with existing external modules.

Research is now a bounded LangGraph subgraph using ModelGateway to select among already discovered, authorized research adapter actions. Its nodes are `understand_research_question` → `select_permitted_sources_tools` → `search_or_retrieve` → `inspect_evidence`, with bounded iteration, then `compare_corroborate` → `qualify_findings` → `return_result`. The model cannot introduce a tool, URL or permission. Rights are rechecked before retrieval. Conflicts, lack of independent corroboration and unresolved evidence remain qualified. Research never generates an application artifact, publishes knowledge or changes ProjectState.

Context Planning passes its remaining retrieval/time/action budget to Research. Default planning allows two total retrieval attempts; Research is additionally capped at four attempts, twelve actions, ten seconds and 5,000 estimated evidence tokens even when called independently. A selection is at most 350 output tokens, with one model request per selection and no provider retries for that operation. Question/action/evidence summaries are clipped. The token estimate bounds retained evidence and summaries; it is not a monetary billing guarantee or an exact tokenizer count. Adapters and providers must honor supplied timeouts; late adapter results are discarded. No registered research adapter means no research tool or model call.

Audit now uses a fixed LangGraph workflow: `load_code_design_standards` → `run_structural_static_checks` → `run_coding_standard_checks` → `run_security_performance_checks` → `check_requirement_design_traceability` → `model_assisted_semantic_review` → `aggregate_findings` → `return_audit_result`. It uses only selected context excerpts and known references, includes available TDD/FRD evidence, aggregates structured findings, and calls the shared report worker through ModelGateway. Findings are stored in artifact metadata and visible report content. Missing code/standards/design, demonstration TODOs, review patterns and unexecuted SAP checks are explicitly identified. Text checks are review leads, not proof of vulnerabilities, compiler success, performance or passing tests. No confirmation or approval is granted by Audit.

Research and Audit have no interruptions and explicitly disable their own checkpoints. Their bodies/findings remain in invocation context; the parent task and context-planning runtime remain responsible for durable pause/resume. Explicit non-sync invocation avoids inheriting the installed LangGraph runtime's synchronous checkpoint behavior for these checkpoint-free graphs; LangGraph emits an informational no-checkpointer durability warning during tests.

The common capability envelope gains optional request identity, actor, input references, context-package reference, constraints, warnings and telemetry. Existing fields and stable IDs remain compatible, including the replaceable ABAP interface. Registry invocation supplies a deep snapshot of input state, preventing a capability's in-memory edits from changing the parent's state object, and validates response/request correlation. This is a component boundary, not a sandbox for arbitrary hostile Python plugins. `/api/capabilities` exposes the configured classification: artifact worker, tool/adapter, external module, subgraph or agentic subgraph.

New tests cover shared profile-driven generation, worker-to-planner clarification, iterative research and corroboration, forbidden model-selected tools, zero budget, permission revocation after selection, actual planner-to-research integration, audit findings without progression changes, and capability snapshot isolation. Real SAP/ADT/ATC/search connectors and final domain-specific Audit rules remain separate integrations; none is enabled automatically.
