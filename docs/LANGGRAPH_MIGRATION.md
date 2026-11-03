# LangGraph runtime migration

This records the initial runtime-only migration. The later [V1.1 implementation update](V1_1_IMPLEMENTATION_SUMMARY.md) intentionally revises state management, approvals, templates and artifact policies while retaining LangGraph. The original invariant tests remain; new policy behavior has dedicated V1.1 tests.

The default runtime is now LangGraph (`langgraph==1.2.19`, SQLite checkpoint package `3.1.3` in the lockfile). The existing `Orchestrator` import, constructor calls, `run()`, `_execute()`, `converse()`, response shapes, API routes, UI, and CLI remain compatible. The original implementation is retained unchanged in `backend/app/legacy_orchestrator.py`.

## Function map

Old references below mean the original `backend/app/orchestrator.py`, now retained as `legacy_orchestrator.py`. New nodes and functions live in `backend/app/langgraph_orchestrator.py`.

| Old file/function or block | New LangGraph node/function |
| --- | --- |
| `orchestrator.py:run()` routing and task initialization | `run()` facade → `understand_task` / `_understand_task()` |
| `orchestrator.py:_execute()` context planning/loading | `plan_context` / `_plan_context()` |
| `_execute()` dependency and clarification preflight | `check_clarifications` / `_check_clarifications()` |
| `_execute()` material clarification return; `clarifications.py:answer()` calls `_execute()` | `await_input` / `_await_input()` → `Command(resume=...)` → context replanning; clarification service unchanged |
| `_execute()` guardrail and execution transition | `before_execute` / `_before_execute()` |
| `_execute()` capability registry invocation | `execute_capability` / `_execute_capability()` |
| `_execute()` validation | `validate_result` / `_validate_result()` |
| `_execute()` artifact, project state, and memory persistence | `persist_and_continue` / `_persist_and_continue()` using existing services |
| `_execute()` pending approval return | `await_approval` / `_await_approval()` |
| `approvals.py:review()` | Unchanged domain review, then composition adapter `RuntimeAwareApprovals.review()` → `resume_approval()` acknowledges the graph wait |
| `orchestrator.py:converse()` | `prepare_conversation`, `execute_conversation`, `validate_conversation` and corresponding `_...()` functions |
| `orchestrator.py:_transition()` | Retained `_transition()` helper; callbacks and model telemetry carried across graph node threads |

## Boundaries and assumptions

- `ProjectState`, memory, artifacts, context services, `ModelGateway`, `StorageProvider`, capability registry, and ABAP interface are unchanged. LangGraph invokes the same capabilities. Draft/in-progress TDD still permits ABAP generation; Project Status reports the existing non-blocking error.
- Checkpoints contain runtime identifiers, routing cursors, and wait reasons only. Domain objects, requirements, worker output, conversation history, and model credentials are not checkpoint channels. Ordinary conversation runs without checkpoint persistence.
- Runtime checkpoints use `<settings_root>/runtime/langgraph/checkpoints.sqlite` (normally `.cowork/runtime/langgraph/checkpoints.sqlite`) with a project/task thread ID. Existing storage remains authoritative. Checkpoints are not a second project-state or memory store.
- Wait nodes have no domain side effects because LangGraph replays an interrupted node on resume. Clarification answers rebuild context through existing services. Existing paused projects without checkpoints resume from their stored domain state.
- Reviews commit through the existing approval service before checkpoint acknowledgement. A failed acknowledgement does not fail or reverse a successful review; the next orchestration request reconciles the cursor. Approval waits do not block starting the next permitted task.
- Generation failures retain the existing storage rollback/retry behavior. This migration does not add exactly-once guarantees for external model calls.
- The composition root defaults to LangGraph. For rollback or comparisons, use `Runtime(..., orchestration_backend="legacy")`. The original runtime remains available after parity verification.

## Verification

The new parent orchestration specification adds a shared event graph, separate output save/registration nodes and completed generation cursors without approval pauses. See [Parent orchestration update](PARENT_ORCHESTRATION_UPDATE.md) for the mapping, recovery contract and revision-rule assumptions.

The later behavior update adds a native context-planning subgraph while retaining this runtime boundary and legacy reference. See [Context planning and provenance update](CONTEXT_PLANNING_AND_PROVENANCE_UPDATE.md) for the additional node mapping, checkpoint design and assumptions.

Migration tests compare both runtimes across STO, clarification, approval, revisions, missing dependencies, draft-TDD ABAP, conversation, progress events, and failures. Additional tests cover restart/resume, rollback, checkpoint content, multiple questions, pre-migration waits, acknowledgement recovery, and cursor authority.

The release gate runs the existing backend/CLI and UI tests, lint/format checks, production build, dependency audit, browser experience scenarios, and finally the STO end-to-end scenario. Recorded results are in `TEST_RESULTS.json` and `python-tests.xml`. Tests use the deterministic provider and isolated project data.

Verified on 2026-10-31: **111 backend/CLI tests (including 16 migration tests), 13 UI tests, 4 browser experience tests, and the final STO browser gate passed**. Python dependency consistency, lint, formatting, TypeScript/production build, and frontend dependency audit also passed.
