# SAP CoWork

SAP SDLC workspace with a Python 3.12/FastAPI backend, a Typer CLI and a React/TypeScript UI. All clients share backend orchestration, status, artifact, context and settings services.

## Run locally

From this directory in PowerShell:

```powershell
./scripts/setup.ps1    # Fresh setup; Python 3.12 and Node.js 22.12+ / 24 required
./start.ps1
```

Open http://127.0.0.1:8000 and choose **Enter workspace**. The default local session has no access code. To set one, copy `.env.example` to `.env` and set `COWORK_ACCESS_CODE` before starting. This is a local, single-user application; enterprise SSO and hosted multi-user operation remain deferred.

The application starts with an explicitly labelled **deterministic demo model**. It requires no API key and generates demonstration documents. Use **Settings** to configure OpenAI, Anthropic, Qwen or an OpenAI-compatible provider, its model identifier, capability profile and API key. Qwen and compatible providers require their base URL. API keys use the OS credential store; project data contains no provider keys. Real provider calls require the user's own working credentials and were not exercised with live credentials during the automated build.

The **ABAP module is a replaceable demonstration stub**, not production ABAP generation or SAP integration. Draft/in-progress TDDs are accepted. An unapproved TDD produces an **error in Project Status with `blocking=false`** and code generation still proceeds.

## Try the STO workflow

1. Create a project in Planning; paste `test_fixtures/sto_cr.txt` in chat.
2. Ask **Generate BRD**. Open BRD v1 and approve it.
3. Ask **Generate FRD**. Answer the material-availability clarification, then approve FRD v1.
4. Ask **Generate TDD**, review it and approve it.
5. Ask **Generate ABAP** to invoke the replaceable module.

The right rail contains Files and Project Status. Documents preserve versions; Request Changes retains feedback for the next generation. Compaction reduces transient working conversation while preserving state, memory, artifacts and the visible transcript.

## CLI

Run these with the server running, from another terminal:

```powershell
./.venv/Scripts/cowork.exe login
./.venv/Scripts/cowork.exe projects create --name "STO Automation"
./.venv/Scripts/cowork.exe chat -m "Automate STO delivery creation"
./.venv/Scripts/cowork.exe chat -m "Generate BRD"
./.venv/Scripts/cowork.exe artifacts show BRD --version 1
./.venv/Scripts/cowork.exe artifacts approve BRD --version 1
./.venv/Scripts/cowork.exe status
./.venv/Scripts/cowork.exe context status
./.venv/Scripts/cowork.exe context compact
./.venv/Scripts/cowork.exe provider configure --provider fake --model deterministic-v1
./.venv/Scripts/cowork.exe provider test
```

`projects open <id>` selects an existing project. `files upload <path> --domain SAP` ingests context. Add `--artifact-type FRD` to register a draft upstream artifact. API keys are entered through a hidden prompt. CLI session tokens use the OS keyring. Set `COWORK_API_URL` to change the API location. `chat --model-policy <configured-provider>` overrides the default model provider for that task. API project creation also supports `model_policy`.

## Verification

Stop any development server on port 8000 first. The browser tests own an isolated server and temporary project data.

```powershell
./.venv/Scripts/python.exe scripts/verify.py
```

This runs Python lint/formatting, all backend and CLI tests, React interaction tests, TypeScript/production build, npm audit, browser experience tests, and **the complete STO journey last**. A nonzero exit stops the gate. Results are in `docs/TEST_RESULTS.json`; sequential build gates are in `docs/BUILD_LOG.md`.

## Repository map

| Directory | Responsibility |
| --- | --- |
| `backend/app/models.py` | Typed domain and interface payloads |
| `backend/app/orchestrator.py` | Resumable task state machine |
| `backend/app/runtime.py` | Composition root and replaceable capability registrations |
| `backend/app/storage.py` / `local_storage.py` | Persistence contract and local implementation |
| `backend/app/model_gateway.py` | Capability checking, fake provider and LiteLLM adapter |
| `backend/app/api.py` / `services.py` | Shared API and application services |
| `cli/` | HTTP client; no duplicated business logic |
| `frontend/` | Workspace, artifact viewer, files/status rail and context controls |
| `templates/` | Versioned Markdown artifact structures |
| `test_fixtures/` | STO reference change request |
| `docs/` | Assumptions, changes and test evidence |

## Architecture and operational boundaries

- State is authoritative; memory is a separate Markdown summary. Context is retrieved only for the current task with provenance.
- Model SDK imports stay inside the provider adapter. Workers use `ModelGateway`; the orchestrator only knows capability IDs and contracts.
- Local writes use atomic file replacement and a recoverable project journal. Artifact content is immutable per version; approval metadata can change.
- One active task per project is supported. Answer pending material clarifications before starting another generation. Retries reuse task IDs to avoid duplicate committed artifacts.
- Run one Uvicorn worker for this local V1. Project locks protect transactions. Enterprise job queues, distributed session storage and concurrent multi-user approval workflows are not implemented.
- Context usage is a conservative estimate, not exact provider tokenization. Active task context is displayed separately from durable memory. Requests exceeding the gateway's safe budget are rejected even after conversational compaction.
- Text, Markdown, JSON, CSV, ABAP, DOCX and text-based PDF uploads can supply context; maximum size is 10 MB. Scanned documents/images are stored but require a text description; OCR/multimodal generation is deferred.
- SAP lookup searches curated project context only. No SAP landscape, live knowledge base or organization standards are bundled. Final guardrails and substantive SAP validation remain deferred as specified.
- SSE streams execution progress and the final response; native model-token streaming is deferred. General chat uses deterministic command routing and project guidance; artifact content uses the selected model.
- Run `npm run dev` from `frontend/` for UI development; Vite proxies `/api` to the backend. For the default run, the backend serves the built UI on the same origin.

See `docs/ASSUMPTIONS_AND_CHANGES.md` for the complete decision register and `docs/TEST_RESULTS.json` for verified results.
