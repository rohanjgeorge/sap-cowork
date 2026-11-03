# SAP CoWork V1.1 implementation changes

Updated on 1 November 2026 against the four documents in `Project Management/V1.1/Behaviour` and the revised Requirements and Conceptual Architecture document. This update retains LangGraph and the existing model gateway, storage abstraction, shared backend, and replaceable ABAP capability. It changes the workflow and artifact rules to the V1.1 baseline.

## Source documents and implementation

| Source | Implemented changes | Main code |
| --- | --- | --- |
| Project State | State Management Service as the production state writer; canonical Draft/Approved stages, lifecycle status, registry pointers, clarifications, flags, decisions, revisions and schema version; authorized user confirmations; closure/reopening; request deduplication and audit events | `backend/app/models.py`, `state_management.py`, `services.py`, `api.py` |
| SDLC Cycle and Progression | Free stage navigation without generation; sequential Approved Stage calculation; both FRD and User Stories required for Analysis; code acceptance and testing confirmation with persistent baseline references and content hashes; withdrawal without deleting artifacts | `state_management.py`, `project_status.py`, `router.py`, `frontend/src/Workspace.tsx`, `ProjectStatus.tsx` |
| Artifacts and Templates | User Stories and SIT; current Markdown templates; Draft outputs; DOCX conversion/storage/download; editing; explicit version creation; approved-version preservation; upload comparison and acceptance; upstream traceability and impact recommendations | `artifact_lifecycle.py`, `artifact_worker.py`, `document_conversion.py`, `local_storage.py`, `templates.py`, `frontend/src/Files.tsx` |
| Context Model | Canonical context domain fields and task profiles, scoped provenance/applicability metadata, organization filtering, preserved conflict qualification, current artifact selection, and compatibility with existing project context | `context_domains.py`, `context_planner.py`, `context_handler.py`, `models.py` |

The UI and CLI call the same services. The UI exposes Draft Stage navigation, Approved Stage status, document editing/download, explicit new-version authors/remarks, offline approval recording, code/testing confirmations, withdrawal, and Close/Reopen Project. Significant upload changes are shown for acceptance before adoption. The CLI adds stage, closure/reopening, confirmations, artifact generation/edit/download/submission, reconciliation, and follow-up retry operations.

## State and persistence

- The canonical state uses `current_draft_stage`, `current_approved_stage`, `project_status`, `artifacts`, `clarifications`, `flags`, `schema_version`, `state_revision`, and `updated_at`. Existing V1 JSON names are accepted on read. Python compatibility properties retain `current_stage`, `open_clarifications`, and clarification `response`; new persisted names are `current_draft_stage`, `clarifications`, and `resolution`.
- Runtime task fields and the historical `artifact_registry` list remain as compatibility projections. `artifacts` has one logical entry per artifact type, with current/approved pointers; detailed versions remain independently stored. Registry pointers are integer versions; existing artifact reference/version API fields remain strings.
- State operations record actor, event, timestamp, and revision. Public operation requests require a revision and request ID. Reusing an ID with different parameters is rejected. Approval identities come from the authenticated local application context, never an agent or user-supplied actor field.
- Project file locks serialize commits across backend processes; revision checks reject stale updates. A separate execution lock preserves generation retry deduplication across processes. Atomic writes and recovery journals remain in the local provider. A verified state backup supports recovery from a corrupt state file.
- Valid document persistence and registry registration are separate recoverable steps. A registration failure retains the complete saved document; `artifacts reconcile` rebuilds registry/task references. Incomplete model output is not registered as an artifact. A memory failure does not erase a valid saved artifact.
- LangGraph checkpoints continue to hold runtime pause/resume cursors only. Domain state, confirmations, artifact bodies and conversation memory are not checkpoint channels.
- Existing V1 JSON artifacts remain readable. Word downloads can be generated from that content; new saves produce the current/archive DOCX layout. Missing historical authors or change reasons are labeled as not recorded rather than invented.
- The original V1 orchestrator and its original workflow helpers remain retained for reference and invariant tests. Their V1 policies intentionally differ from V1.1; they are not an alternative V1.1 production workflow.

Document files are stored behind StorageProvider under the existing project root, for example:

```text
.cowork/project/<project-id>/
  state/project_state.json
  state/project_state.backup.json
  artifacts/brd/
    BRD--1.json                 # Version content and machine-readable metadata
    current/BRD.docx
    archive/BRD_v1.docx
  artifacts/abap/current/ABAP.abap
  uploads/                      # Original source uploads and closure learning
  history/                      # Events, operation outcomes and conversation
```

The filesystem arrangement is an implementation detail of LocalStorageProvider. Registry storage references remain logical artifact references.

## Assumptions and choices made in gaps

1. **Source precedence:** The four specific behavior specifications and the architecture document's updated artifact section supersede older V1 behavior. Your explicit decision to allow ABAP from an in-progress TDD is retained: generation proceeds and Project Status displays a non-blocking error.
2. **Stage approvals:** An Approved Stage represents the next stage reached through completed prerequisites. New Drafts retain earlier version approvals and therefore do not automatically revoke earlier progression. Status can still show attention for an active Draft or unresolved dependency. Missing prerequisites cannot advance Approved Stage, even if a later artifact was approved.
3. **Closure:** Completion requires the latest active BRD, FRD, User Stories, TDD, SIT and UAT to be approved, plus active code and testing confirmations. Audit approval is not required. Otherwise manual closure records `incomplete`. An active unapproved revision prevents a `completed` closure even when an older approved version exists.
4. **Confirmation baselines:** Code confirmation binds to the current ABAP version and content hash. Testing confirmation binds to SIT/UAT and ABAP versions/hashes. Editing the same Draft test version invalidates its old confirmation; changed code requires fresh acceptance. These records survive restart and retain withdrawal history.
5. **Approval declaration:** The existing Approve Artifact control records the authenticated user's declaration of an offline approval. It does not contact or verify an external approval system. Generated artifacts begin as Draft; a separate submission operation can mark pending offline approval. Returning a Draft for changes updates that Draft; requesting changes to an Approved artifact forks a Draft.
6. **Templates:** The existing repository `templates/` folder is retained as the logical application template directory, preserving your manual template changes. No template version registry is introduced. The compatibility `template_version` field holds the filename for newly generated documents; historical values are retained. Templates affect future generation; existing documents are not silently restructured.
7. **Editing and upload alignment:** The in-app editor edits document Markdown structure; the backend converts it to Word. For an uploaded document whose structure does not match the template, sections are created with explicit TBD/review markers and the complete extracted source is retained for review. The system does not invent a semantic section mapping. Original upload bytes are retained separately.
8. **Significant upload changes:** Text similarity below 80% triggers a unified comparison and explicit acceptance. This deterministic threshold is an initial implementation choice, not a settled product rule. Text extraction and heading/table round trips are covered; full fidelity for arbitrary Word styling, tracked changes, embedded objects, and images is not claimed.
9. **Version history and impact:** Explicit version creation requires authors and remarks. Approved edits automatically create a Draft without requiring an explicit version request. History records changed sections, author, reason and dates. Impact detection uses source links and known artifact dependencies; recommendations conservatively list sections for revalidation. It does not silently rewrite downstream business content or claim SAP correctness.
10. **Information gaps:** Missing/unapproved upstream artifacts remain warnings rather than stage-navigation blockers. An explicit generation request is treated as the user's choice to proceed with available context. A material task-specific clarification can still pause that generation task until answered; navigation remains independent.
11. **Follow-ups:** Testing confirmation triggers the existing isolated Audit Worker. Audit failure leaves confirmation intact and records retry status. Closure produces a qualified project learning summary; failure leaves the project closed. Follow-up status is recoverable and retryable through the shared backend/CLI. Closed projects must be reopened before generating additional project artifacts.
12. **Local authorization:** This remains the existing authenticated local single-user application. Organization/program identifiers and metadata do not introduce a production multi-tenant identity system. Enterprise authorization and Projects/Programs access control remain separate work.

## Explicitly deferred by the source documents

Subsequent behavior documents now add native context planning, bounded retrieval and controlled project-copy reconciliation. See [Context planning and provenance update](CONTEXT_PLANNING_AND_PROVENANCE_UPDATE.md) for the implemented scope and remaining connector/enterprise boundaries. The paragraph below describes the earlier four-document baseline.

The Context Model document finalizes conceptual rules while deferring Knowledge Management, catalog/schema, indexing/search, organization-copy synchronization/reconciliation mechanics, detailed applicability/ranking/token budgeting, Research Agent tools/triggers/publication, and enterprise authorization. This update adds compatible domain/provenance boundaries; it does **not** implement or claim those engines. No automatic cross-project, organization, or global publication is enabled. Closure learning is retained at project scope until the controlled publication interfaces are designed.

Deep SAP correctness validation, final guardrail policy, full ABAP generation, advanced Word round-trip editing, Deployment and Maintenance remain outside this update. Existing validation and guardrail hooks remain available.

## Verification

The release pipeline runs backend/CLI unit and contract tests, UI interaction tests, lint/format checks, TypeScript production build, dependency audit, browser experience scenarios, and the STO flow **last**. The STO journey now includes User Stories approval before Analysis completion, then code acceptance, SIT/UAT, testing confirmation, audit generation, and completed read-only closure.

See `TEST_RESULTS.json` and `python-tests.xml` for the final recorded results. Tests use isolated temporary project data and deterministic or mocked model providers; no live OpenAI calls or user credential changes are required.

Final verification on 1 November 2026: **129 backend/CLI tests, 17 UI tests, four browser experience scenarios, and the extended STO scenario passed**. Python lint/format checks, dependency consistency, TypeScript production build, and frontend dependency audit passed. STO was the final automated gate. A representative generated BRD was rendered in Microsoft Word and all three pages were visually checked.
