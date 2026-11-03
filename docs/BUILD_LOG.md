# Sequential build gates

Each numbered layer is implemented only after the preceding layer's tests pass.
The final release gate is the STO browser journey against the running backend.

- 2026-10-29T20:03:35.490890+00:00 | Layer 01 | PASS | backend/tests/test_bootstrap.py

- 2026-10-29T20:04:04.775287+00:00 | Layer 02 | PASS | backend/tests/test_models.py

- 2026-10-29T20:04:14.595410+00:00 | Layer 03 | PASS | backend/tests/test_storage_contract.py

- 2026-10-29T20:04:51.563331+00:00 | Layer 04 | PASS | backend/tests/test_local_storage.py backend/tests/test_storage_contract.py

- 2026-10-29T20:05:11.186123+00:00 | Layer 05 | PASS | backend/tests/test_settings.py

- 2026-10-29T20:05:38.597562+00:00 | Layer 06 | PASS | backend/tests/test_gateway.py

- 2026-10-29T20:05:50.969256+00:00 | Layer 07 | PASS | backend/tests/test_gateway.py backend/tests/test_model_capabilities.py

- 2026-10-29T20:06:02.544260+00:00 | Layer 08 | PASS | backend/tests/test_registry.py

- 2026-10-29T20:06:14.587963+00:00 | Layer 09 | PASS | backend/tests/test_router.py

- 2026-10-29T20:06:52.706877+00:00 | Layer 10 | PASS | backend/tests/test_orchestrator.py

- 2026-10-29T20:07:01.496123+00:00 | Layer 11 | PASS | backend/tests/test_context_planner.py

- 2026-10-29T20:07:19.257660+00:00 | Layer 12 | PASS | backend/tests/test_context_handler.py backend/tests/test_context_planner.py

- 2026-10-29T20:07:44.595054+00:00 | Layer 13 | PASS | backend/tests/test_clarifications.py backend/tests/test_orchestrator.py

- 2026-10-29T20:08:00.982319+00:00 | Layer 14 | PASS | backend/tests/test_templates.py backend/tests/test_clarifications.py

- 2026-10-29T20:08:30.126899+00:00 | Layer 15 | PASS | backend/tests/test_artifact_worker.py

- 2026-10-29T20:08:39.092535+00:00 | Layer 16 | PASS | backend/tests/test_brd_flow.py backend/tests/test_artifact_worker.py

- 2026-10-29T20:08:57.716234+00:00 | Layer 17 | PASS | backend/tests/test_approvals.py backend/tests/test_brd_flow.py

- 2026-10-29T20:09:15.269464+00:00 | Layer 18 | PASS | backend/tests/test_frd_flow.py backend/tests/test_clarifications.py

- 2026-10-29T20:09:35.122790+00:00 | Layer 19 | PASS | backend/tests/test_tdd_flow.py backend/tests/test_frd_flow.py backend/tests/test_approvals.py

- 2026-10-29T20:09:57.045643+00:00 | Layer 20 | PASS | backend/tests/test_memory.py backend/tests/test_tdd_flow.py backend/tests/test_local_storage.py

- 2026-10-29T20:10:25.571927+00:00 | Layer 21 | PASS | backend/tests/test_compaction.py backend/tests/test_frd_flow.py

- 2026-10-29T20:10:38.658974+00:00 | Layer 22 | PASS | backend/tests/test_hooks.py backend/tests/test_tdd_flow.py

- 2026-10-29T20:10:56.248803+00:00 | Layer 23 | PASS | backend/tests/test_abap.py backend/tests/test_hooks.py

- 2026-10-29T20:11:18.587111+00:00 | Layer 24 | PASS | backend/tests/test_project_status.py backend/tests/test_tdd_flow.py backend/tests/test_abap.py

- 2026-10-29T20:13:24.157226+00:00 | Layer 25 | PASS | backend/tests/test_api.py backend/tests

- 2026-10-29T20:14:26.769831+00:00 | Layer 26 | PASS | cli/tests backend/tests/test_api.py

- 2026-10-29T20:16:34.357751+00:00 | Layer 27-28 | PASS | UI tests and TypeScript production build

- 2026-10-29T20:17:08.977084+00:00 | Layer 29 | PASS | UI tests and TypeScript production build

- 2026-10-29T20:18:10.428193+00:00 | Layer 30 | PASS | UI tests and TypeScript production build

- 2026-10-29T20:18:53.366647+00:00 | Layer 31 | PASS | UI tests and TypeScript production build

- 2026-10-29T20:20:01.580474+00:00 | Layer 32 | PASS | UI tests and TypeScript production build

- 2026-10-29T20:21:00.942758+00:00 | Layer 33 | PASS | UI tests and TypeScript production build

- 2026-10-29T20:21:47.511611+00:00 | Layer 34 | PASS | backend/tests/test_audit.py backend/tests/test_api.py cli/tests

- 2026-10-29T20:23:01.651315+00:00 | Layer 34-adapters | PASS | backend/tests/test_litellm_adapter.py

- Layer 35 | PASS | Chromium STO journey against real FastAPI backend: Planning → BRD approval → FRD clarification/resume/approval → TDD approval → ABAP interface invocation.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Layer 36 | PASS | Revision/diff/upload/compaction/reopen/mobile browser tests; lint and formatting; full final gate passed. Seven-page assumptions report rendered with Word/PDF and all pages visually checked (bundled LibreOffice is unavailable on this Windows host).

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Context behavior update | PASS | Full backend/CLI checks; corrected UI assertion and passed all remaining release checks, with STO last. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Landing page copy update (2026-11-03) | Removed the brand tagline, business-context paragraph and SDLC row; changed the main heading to 'Welcome to Project Workspace' (interpreting 'Projet' as a typo); prefixed the local-session footer with 'Note:'. Desktop (1800 x 800) and mobile (390 x 844) screenshots were visually checked with no horizontal overflow. Login behavior and backend contracts are unchanged.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Project home simplification (2026-11-03) | Removed the development-workspace introduction and the entire 'One project. Every stage.' panel. 'Your projects' is now the page heading at the top of the content, and '+ New project' is in the top bar. Mobile header actions and project search stack to fit narrow screens. Verified populated layouts, search filtering and both creation choices at 1840, 390 and 320 px widths with isolated browser responses; desktop/mobile screenshots visually checked. Existing project creation, approved-document onboarding and backend contracts are preserved.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Compact project folders (2026-11-03) | Added keyboard-accessible Active/Completed folder tabs with counts and folder-specific search/empty states. Completed uses the backend project_status='completed'; legacy/missing statuses and projects closed incomplete remain discoverable under Active, with closed-incomplete projects labeled explicitly. Cards now place the name beside the folder icon and show current Draft SDLC stage (legacy current_stage fallback) plus last-updated date, replacing descriptions and stage ribbons. Reduced card padding/height and use four columns on desktop, two on tablet and one on mobile. Added lifecycle/search/keyboard unit coverage and extended the final STO journey to find its completed project in Completed and reopen its read-only workspace. Mocked browser checks passed at 1840, 390 and 320 px; desktop/mobile screenshots were visually checked. Backend lifecycle and mutation contracts are unchanged.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Metadata field guidance (2026-11-03) | Added a small inline note beneath each of the seven optional project metadata fields, explaining its meaning, an example and how it helps match scoped context or SAP applicability. Notes are shared by New Project and project metadata editing. Each input references its note via aria-describedby with instance-unique IDs; existing field labels and submission payloads are preserved. Desktop (1440 x 1000) and mobile (390 x 844) browser checks confirmed all seven accessible descriptions and a scrollable modal without horizontal overflow; screenshots visually checked.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Project creation navigation and client names (2026-11-03) | Added a small header back arrow on both creation forms, preserving entered values when returning to the start options. Scratch creation displays a disabled Planning stage and always submits Planning, including after returning from assisted stage selection. Added optional Client name below Project name on both paths, persisted via the Project/API/service contracts and displayed on compact project cards. Client names are trimmed and limited to 150 characters; older records/callers remain compatible, and omitted names preserve existing creation retry signatures. Added persistence/restart/retry/conflict/legacy-record API coverage and UI back-navigation/stage-lock/client-name coverage. Desktop and mobile real-browser checks against isolated temporary data verified both creation paths, saved names after reload and compact cards; screenshots visually checked. Stage assistance remains on the approved-document path, and later workspace stage navigation is unchanged.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.
- Local backend refresh | Restarted port 8000 after verification using the original process environment, working directory and project-data location; checked that no task was running before restart. Health passed and the served NewProject API schema includes client_name.

- Closed-project folder correction (2026-11-03) | Corrected the earlier folder decision: Completed now contains both completed and incomplete lifecycle statuses, while Active contains active projects and legacy records with no status. Closed-incomplete cards retain their explicit label; reopening returns a project to Active. Updated lifecycle unit assertions and added real desktop/mobile browser regressions covering close, Completed placement after reload, read-only reopening and return to Active. Backend closure/completion rules remain unchanged.
- Mobile regression discovered during validation | The new mobile close/reopen test found the expanded project menu behind the project rail. Raised the menu above the rail so Close/Reopen remains clickable; both targeted desktop and mobile lifecycle regressions passed. The complete browser suite and STO are rerun after this correction; the first failed browser attempt is retained in verification evidence.

- Closed-project release verification | PASS | Preserved successful lint, backend/CLI, UI and audit results; rebuilt after the mobile menu fix, reran all seven browser tests, then passed STO as the final gate. The initial failed mobile attempt is retained in TEST_RESULTS.json.

- Per-document import status (2026-11-03) | Added Draft/Approved radios beside every document in the existing-requirements checklist, defaulting to Draft and enabled for selected documents. Removed the shared approval confirmation checkbox. New UI creation requests persist import_artifact_statuses for selected documents; each upload prompt/progress item reflects that status. Drafts stay Draft and finish their queue step without approval; only Approved selections invoke the existing offline approval service. Older projects and callers without a status map preserve prior all-approved behavior and creation retry signatures. Mixed-status persistence, restart, retries, invalid inputs and no approval of draft imports have focused backend/UI coverage; the browser onboarding scenario now verifies a Draft BRD plus Approved FRD.
- Per-document status browser validation | Real desktop (1440 x 1000) and mobile (390 x 844) sessions with isolated temporary data verified Draft defaults, independent Approved selection, removal of the shared checkbox, sequential uploads, reopen persistence, and final Draft BRD/Approved FRD states. Checklist screenshots were visually checked and the modal had no horizontal overflow.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.
- Local backend refresh | After all release gates passed, restarted port 8000 with its original process environment and data location after checking no project task was running. Health passed and the served NewProject schema exposes import_artifact_statuses.

- Chat stage guidance and sequential clarification (2026-11-03) | Renamed the workspace selector to Work on: and the approved-stage badge to Current Stage; while preserving domain meanings. Removed the stale Generate task subtitle. Stage changes now obtain read-only contextual guidance through the selected ModelGateway and existing LangGraph conversation path; they do not generate artifacts or replace paused task/checkpoint identity. Provider errors remain visible and successful navigation retries replay their saved response. Chat renders one active-task clarification and submits its ID; assistant messages ask only the next question while full queues remain in ProjectState/status/API. Added model-provider, failure, replay, paused-checkpoint and sequential persisted-answer tests, plus a stage-guidance browser scenario. Mobile topbar now grows to fit controls and the rail anchors below it, keeping Work on and Current Stage visible without clipping. See CHAT_STAGE_GUIDANCE_AND_CLARIFICATIONS.md.
- Chat visual validation | Isolated real-browser checks passed on desktop and mobile for stage guidance, paused clarification display and no horizontal overflow. Rebuilt mobile header was visually checked: Work on and Current Stage remain visible and every header control fits within the bar. All automated provider checks used deterministic demo or mocked providers.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.
- Chat release and local refresh | All release steps passed: 207 backend/CLI tests, 31 UI tests, eight browser experience tests and STO last. Restarted port 8000 with its original process environment and project-data location after checking no task was executing; health passed and persisted checkpoints were left intact.

- Compact chat and Project Status records (2026-11-03) | Moved loaded context category badges into the Context details and added a visible expand/collapse chevron with aria-expanded/aria-controls. Reduced clarification padding and paragraph spacing without hiding question text. Replaced the Project Status subtitle with Clarifications/Decisions/Flags totals backed by full existing workspace state, including resolved records. Clicking a total opens a read-only list with statuses, saved clarification answers and a back arrow; returning restores focus. API/backend and workflow behavior are unchanged. Focused UI and real-browser decision/context-navigation tests passed; populated desktop/mobile screenshots were visually checked with no horizontal overflow. Full release verification follows.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Project Status task summary and compact stages (2026-11-03) | Added saved Current task, Expected next artifact and Recommended next action near the top of Project Status, passing expected_next_artifact directly from workspace state. Null values are labeled explicitly; the duplicate recommended-action footer was removed. Stage labels now read Working on: and Current Stage:, with matching colon punctuation in the top bar. All five stage selectors use small rectangular two-column buttons, preserving backend colors, accessible status descriptions, selection state, the Next marker and existing navigation/approval handlers. Focused tests covered saved values versus stage defaults and cleared fields. Desktop/mobile browser checks verified summary values against the API and measured the stage grid at 160/138 px high; screenshots visually checked. Backend behavior is unchanged.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.

- Clarification processing feedback (2026-11-03) | Added an immediate Processing your answer... status above the composer, a loading spinner on the send button and phase descriptions as backend progress arrives. Feedback stays visible outside the scrolling chat. Submitted answers remain readable/read-only while processing and clear when the server's pending question is resolved; request failures retain editable text and existing retries preserve their original identity. Duplicate submissions remain blocked. Spinner animation respects reduced-motion preferences. Added deferred-response and failure/retry UI tests plus a delayed-response browser regression. Desktop/mobile visuals were checked; mobile transport-failure/retry and reduced-motion checks passed with isolated demo data. Backend and API behavior are unchanged.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.
- Clarification feedback release verification | PASS | 235 backend/CLI tests, 38 UI tests, 10 browser experience tests and STO as the final gate. Build, lint, formatting and dependency audit passed. Frontend-only changes; no backend restart or project-data changes were needed.

- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.
