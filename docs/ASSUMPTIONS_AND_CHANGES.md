# SAP CoWork V1 Implementation Assumptions and Changes

Prepared 30 October 2026

## Delivery and verification

SAP CoWork V1 is implemented as a local monorepo with a Python 3.12 FastAPI backend, Typer CLI, React and TypeScript UI, versioned Markdown templates, a local storage provider and automated tests. The backend serves the built UI at http://127.0.0.1:8000. The CLI calls the same backend services through HTTP.

The five supplied specifications remain the design baseline. Your subsequent clarification takes precedence: ABAP generation accepts a draft or in-progress technical artifact. A missing approval appears as an error in Project Management with blocking=false; it does not stop generation.

The default model is an explicitly labelled deterministic demonstration provider. The ABAP implementation is an explicitly labelled stub. Automated tests prove application behavior and contracts; they do not establish SAP correctness, production ABAP quality or live-provider access. BYOK configuration and a LiteLLM adapter are implemented. Live calls need your credentials and model access.

The attached dependency order was followed through sequential test gates. The state machine was first tested against injected contracts, then connected to context handling and workers as those layers passed. The backend vertical slice passed before CLI implementation; the CLI passed before UI implementation. The STO browser scenario is the last application release gate in scripts/verify.py.

Final verification: 86 Python/backend/CLI tests; 12 UI interaction tests; three additional Chromium experience scenarios; one final STO Chromium scenario. Python lint, formatting, TypeScript compilation, production build and npm dependency audit passed. See TEST_RESULTS.json and BUILD_LOG.md for execution evidence.

<!-- PAGE -->
## Architecture and contract changes

**A01 Local delivery.** V1 is a browser-accessible local application with one backend process, rather than a native desktop executable or hosted service. Enterprise storage, deployment automation, SSO and multi-user operation remain outside this build. Source code and startup scripts are supplied; nothing is published externally.

**A02 Composition boundary.** Runtime wiring is centralized in backend/app/runtime.py. The orchestrator knows capability IDs and contracts. Replacing ABAP generation is a registry change; tests replace its implementation without editing orchestrator code. One generic worker implements BRD, FRD, TDD, UAT and audit generation.

**A03 Task continuity.** ProjectState adds active_task_id, task_status, active_capability_id, task_inputs, requirement, started_stages, recommended_stage, issues and completed_tasks. These preserve task identity, resume data, recommendations, status derivation and committed-result deduplication. Project adds description and activity timestamps.

**A04 Severity and blocking.** ProjectIssue contains code, message, severity, blocking and stage. An error can be non-blocking. Material clarification gaps are blocking errors for their current task; TDD approval gaps are non-blocking errors for ABAP. This separates presentation from execution permission.

**A05 Contract extensions.** ArtifactGenerationRequest includes task_id, output version and revision instructions. Artifact records include source_task_id, source references and revision feedback. Clarifications retain task association and context domain. ModelProfile describes context/output limits and supported capabilities.

**A06 Persistence extensions.** StorageProvider adds project listing/updating, sessions, audit events, explicit artifact-version loading and project transactions. State and artifact references retain the document-specified naming differences: version on a reference, artifact_version on the full artifact. Application services own translation.

**A07 Decision phase.** Decide is a logical step inside the control loop. No additional persisted DECIDE enum was introduced because the supplied TaskStatus contract omits it. The specified statuses are preserved; tests cover their serialization.

<!-- PAGE -->
## Workflow and artifact assumptions

**A08 Progression.** Approval changes the recommended stage and next artifact. It does not force the user into that stage. Starting a requested downstream task changes the active stage. Users can enter any in-scope stage; missing ideal inputs appear in Project Status rather than forming universal approval gates.

**A09 ABAP input policy.** The latest available TDD version is used, including draft, pending or rejected versions. Missing approval creates TDD_UNAPPROVED with severity error and blocking=false. A completely missing TDD remains an advisory missing-input warning; the stub can run from available context. The final ABAP module may request material clarifications through the same contract.

**A10 One active task.** One active generation task per project is supported. A pending material clarification must be answered before starting another generation. Reopening restores it. Reviewing an unrelated upstream artifact must not discard that waiting task. Parallel projects remain isolated; distributed workflow coordination is deferred.

**A11 Clarification policy.** No requirement blocks BRD generation. The initial deterministic material-gap rule asks for the definition of material availability during FRD generation when the requirement uses that term and no definition or resolved answer exists. Curated SAP context can supply an Availability definition. Real model workers can return additional questions. This initial rule is extensible; it is not a complete SAP ambiguity detector.

**A12 Identity and versions.** Artifact identity is its type within a project, for example BRD. Generated versions increment as positive integer strings. Content cannot be overwritten within a version; approval metadata can change. Uploaded artifacts start as draft with template_version=uploaded. The viewer defaults to the latest version, even if an older version is approved.

**A13 Review behavior.** Rejection requires feedback and retains the rejected version. The next generation receives that feedback. Approving an older version cannot complete a newer unapproved version. Reviews record the local user as editor/approver. Team roles and approval permissions are deferred with multi-user operation.

**A14 Stage completion.** Primary outputs are BRD, FRD, TDD, ABAP and UAT. Audit output is a Testing deliverable but UAT remains the primary artifact for Testing completion. Green requires the latest primary version to be approved without a relevant material clarification or upstream gap. Started/incomplete stages are amber; untouched stages are grey. No Deployment transition is generated.

<!-- PAGE -->
## Storage context and memory assumptions

**A15 Local storage.** Data lives under .cowork/project/<project-id> by default. The logical state, memory, context, uploads, artifacts and history folders are preserved. JSON supports typed serialization; project_memory.md stores the readable memory summary, with a JSON companion for its timestamp. Context ingested from Markdown or documents is normalized into provenance-bearing JSON items.

**A16 Transactions and recovery.** Writes use atomic file replacement, project file locks and an undo journal. Artifact, state, memory and audit writes roll back together if a task transaction fails. An interrupted transaction is recovered on the next project transaction. The recovery journal is retained if rollback itself fails. This is a local V1 mechanism, not a distributed database guarantee.

**A17 Retry semantics.** Provider timeouts receive at most three attempts under the same task ID. Committed task results are indexed for replay; duplicate and simultaneous retry tests produce one committed artifact. Reusing an ID for another artifact type is rejected. Provider-side billing or duplicate inference after a process crash cannot be guaranteed exactly once.

**A18 Context retrieval.** Initial context planning uses deterministic task profiles. BRD loads Business and SDLC plus conditional SAP/Organization context for SAP-related requirements. FRD and TDD request the broader defined domains; ABAP uses SAP/Organization/History/SDLC. Only requested domains and relevant upstream artifact types are loaded. Context items carry their source and source type. The relevant memory summary is included when SDLC context is requested.

**A19 Knowledge scope.** There is no bundled enterprise SAP knowledge base, landscape connector, standards library or vector store. SAP_LOOKUP searches curated project SAP context. It does not claim external SAP facts. Upload a context file into its selected domain to supply organization or SAP information. Source instructions remain source data in worker prompts.

**A20 Memory.** Significant changes rebuild a deterministic summary of objective, domain facts, decisions, resolved clarifications and current status. Memory is not authoritative workflow state. Full visible chat history is stored separately for reopening; generation uses scoped context and artifact inputs rather than replaying that history.

**A21 Compaction.** Context percentages use a conservative UTF-8 token estimate, a 5% reserve and the configured output allowance. They are telemetry estimates, not exact provider tokenization. The 60/75/85 bands are configurable service values. High-pressure preparation compacts transient conversation; explicit user compaction does the same. Durable memory, state, decisions, clarifications, artifacts and the visible transcript are preserved. Oversized required task inputs still fail the gateway preflight; compaction does not silently delete source documents.

<!-- PAGE -->
## Model access credentials and execution assumptions

**A22 Provider neutrality.** ModelGateway is the only model entry point. LiteLLM is confined to its provider adapter. OpenAI and Anthropic use provider-prefixed model identifiers; Qwen and OpenAI-compatible configurations use compatible endpoints and require a base URL. Direct provider adapters can replace LiteLLM later.

**A23 Model selection.** User settings select the default provider/model. Project model_policy and per-task model_policy can override that selection using a configured provider. API project creation and chat accept the policy; CLI chat exposes --model-policy. The UI Settings flow changes the user default. Automatic capability-based provider selection, cost routing, fallback and failover remain deferred; incompatible choices fail before invocation.

**A24 Capability declarations.** The user configures context window, output limit, structured-output support, tool calling, vision, streaming, reasoning and coding support. The gateway checks task requirements against that declaration. Profiles are not automatically discovered or benchmarked. Provider rejection remains possible when a declared capability is inaccurate.

**A25 Credential storage.** Settings persist only credential references outside the project tree. Raw API keys are written through the OS keyring and read only by the adapter. The CLI stores session tokens in its own OS keyring entry. API responses and audit records exclude credentials. Automated credential tests use a memory secret-store substitute; adapter tests mock the provider SDK and make no live requests.

**A26 Authentication.** A local single-user session shell uses a configurable access code, expiring eight-hour session tokens, an HttpOnly same-site cookie and bearer access for CLI. With no code configured, Enter workspace opens the local session. The launcher binds loopback only. Sessions are in process memory and require login after restart. This is not enterprise authentication or hosted multi-user authorization.

**A27 Worker output.** Workers request structured JSON and enforce the exact template heading sequence. An incompatible response fails rather than silently producing a malformed artifact. Fake output is prominently marked as demonstration content; it proves plumbing and lifecycle behavior, not substantive requirements quality. ABAP output is a deterministic report stub with TODOs and no SAP write operations.

**A28 Hooks and telemetry.** Guardrail hooks check project/task correlation before invocation. Validation hooks perform minimal result-contract checks afterward. Production policy, SAP correctness and artifact-quality validation remain deferred. Allowlisted audit events capture identifiers, domains, model/provider, duration, usage, outcome and coarse error category. Prompts, source contents and credentials are excluded; model telemetry is isolated per execution thread.

<!-- PAGE -->
## UI CLI and file experience changes

**A29 Workspace.** The UI provides login, Project Home, creation and assisted stage confirmation, dominant orchestrator chat, collapsible Files/Project Status rail, versioned document viewer, context bar and provider settings. The backend derives stage status; the frontend renders it. Color is paired with text and icons. System fonts avoid external font dependencies.

**A30 Stage assistance.** The backend suggests a starting stage from the latest artifact type the user declares. The user must confirm it. It is a deterministic availability-based suggestion; it does not semantically inspect arbitrary uploaded documents to infer the stage. Upstream files can be attached after project creation.

**A31 Chat scope and streaming.** Common generation/review/retry commands and clarification answers are routed deterministically. The UI also submits explicit actions. Long first messages are captured as change requests. General unmatched conversation returns project guidance rather than pretending to provide an unrestricted agent chat. SSE streams live task progress and the final result; native model-token streaming is deferred.

**A32 Files and revisions.** Users can upload supporting files or register them as draft artifacts, select a context domain, navigate versions, approve/reject exact versions and compare consecutive versions with a line diff. Generated artifacts are read-only; revisions create a new version. Uploaded raw files are downloadable; generated/registered artifacts open in the document viewer.

**A33 Intake limits.** Uploads are limited to 10 MB. UTF-8 text/Markdown/JSON/CSV/ABAP, DOCX paragraphs/tables and text-based PDFs can supply extracted context. Other formats are retained as raw files. Scanned PDF/image interpretation, OCR, spreadsheet parsing and binary document preview are not implemented; the UI asks for a text description where extraction is unavailable.

**A34 CLI parity.** The CLI supports login, project create/list/open, conversational and one-message chat, status, artifact list/show/approve/reject, file list/upload, provider configure/test and context status/compact. Project selection is stored in user CLI configuration. Keys are prompted privately. CLI output is textual/JSON; UI layout is not reproduced.

**A35 Recovery and accessibility.** The UI includes loading/error/empty states, stable task-ID retry, refresh, responsive mobile rail behavior, labelled form controls, keyboard interaction, reduced-motion support and a focused provider dialog with Escape. Review and revision actions identify the exact version. Reconnect is handled through refresh/retry; a durable distributed background-job service is deferred.

<!-- PAGE -->
## Acceptance evidence and operation

**Final STO gate.** The browser test starts with a newly created project, submits the supplied STO CR, verifies Planning, creates pending BRD v1 with amber Planning, approves it and verifies green Planning and recommended Analysis. It starts FRD generation, verifies relevant context and awaiting_input, answers the material clarification, verifies the same task resumes, approves FRD and checks Analysis/Design guidance. It generates and approves TDD, checks green Design and recommended Development, and invokes the ABAP module. A separate contract test replaces that module without orchestrator changes.

**Additional coverage.** Tests cover domain serialization, provider contracts, scope/provenance, state reopening, rollback and crash recovery, concurrent duplicate requests, missing-input behavior, template conformance, version immutability, review feedback, context preservation, hooks, PM errors, API authentication, SSE, CLI parity, UI interaction, uploads, diffs, mobile layout and assisted stage confirmation.

**Reproducibility.** requirements.lock.txt and frontend/package-lock.json record installed versions. scripts/setup.ps1 prepares the Python environment, dependencies, frontend build and Chromium. start.ps1 launches the local server. scripts/verify.py runs all checks and executes the STO scenario last. The supplied CI workflow runs the same verification on Windows. CI configuration is supplied but has not been executed on a remote CI runner during this build.

**Operating assumptions.** Use Python 3.12 and Node.js 22.12+ or 24. Run one Uvicorn worker. Project file locks and in-process application locks serialize local project work. Stop a preview server on port 8000 before browser tests; tests start their own isolated backend and temporary data. The production build is served by FastAPI; Vite is optional for frontend development.

**Remaining boundaries.** Real-provider access, SAP system execution, production guardrails/validation, enterprise storage, distributed jobs, SSO, role-based approvals, OCR/vision workflows, native token streaming, automatic model routing and Deployment/Maintenance automation remain deferred or require external configuration. The original five Word documents were not modified; this register records the implementation assumptions and clarifications alongside the code.

## Source baseline

1. SAP_CoWork_AI_Layer_Requirements_and_Conceptual_Architecture version 1.docx
2. SAP_CoWork_AI_Layer_Tech_Stack_and_Model_Access version 1.docx
3. SAP_CoWork_AI_Layer_V1_Data_Models_and_Interface_Contracts.docx
4. SAP_CoWork_AI_Layer_V1_Orchestration_and_State_Transition_Specification.docx
5. SAP_CoWork_AI_Layer_V1_UI_and_CLI_Experience_Specification.docx
6. Your ABAP approval clarification and attached 36-step build/test direction.

Integration references checked: https://docs.litellm.ai/docs/completion/input and https://fastapi.tiangolo.com/advanced/events/.
