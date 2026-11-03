# SAP CoWork

SAP SDLC workspace with a Python 3.12 / FastAPI backend, Typer CLI, and React / TypeScript UI. The UI and CLI use the same backend orchestration, project state, context, artifact, and model services.

The [V1.1 implementation summary](docs/V1_1_IMPLEMENTATION_SUMMARY.md) records the revised workflow, artifact rules, assumptions, and deferred designs. The current application uses separate Draft and Approved stages; Analysis requires both FRD and User Stories approval.

## Run locally

From PowerShell:

```powershell
./scripts/setup.ps1
./start.ps1
```

Open:

```text
http://127.0.0.1:8000
```

Select **Enter workspace**.

**New project** offers two starting paths. Choose **Start from scratch with the client requirement** for the usual creation form, or **I have some requirements already approved** to select approved artifacts by SDLC stage. After creation, CoWork asks for each selected document one at a time in chat. The import queue survives reopening; each import records your declared approval. See [project onboarding](docs/PROJECT_START_AND_APPROVED_DOCUMENT_ONBOARDING.md).

To enable an access code, copy `.env.example` to `.env` and set:

```text
COWORK_ACCESS_CODE
```

## Model setup

The application starts with a deterministic demo provider.

Use **Settings** to configure:

- OpenAI
- Anthropic
- Qwen
- OpenAI-compatible providers

Fill the fields according to the provider you select:

| Field | What to enter |
| --- | --- |
| **Model identifier** | The provider’s exact API model ID, copied from its console or documentation. Our app adds the provider prefix automatically. | E.g. for OpenAI is gpt-6.1-sol
| **API key** | Your API key for that provider. Paste it into Settings, not this chat. Leave blank only when retaining an already saved key. |
| **Base URL** | The provider’s API base endpoint, as explained below. |

For **Base URL**:

- **OpenAI or Anthropic:** leave it blank to use the standard endpoint.
- **Qwen or OpenAI-compatible:** enter the endpoint supplied by your provider or organization. Use the API base URL, not its website or the full `/chat/completions` URL.
- **Fake/demo:** use model identifier `deterministic-v1`; no key or Base URL is needed.

Click **Save provider**, then **Test saved connection**.

API keys are stored separately from project data.

## STO workflow

1. Create a project in **Planning**
2. Paste `test_fixtures/sto_cr.txt` into the chat
3. Ask **Generate BRD**
4. Review and approve BRD v1
5. Ask **Generate FRD**
6. Answer the material-availability clarification
7. Review and approve FRD v1
8. Ask **Generate User Stories**, then review and record approval
9. Ask **Generate TDD**, then review and record approval
10. Ask **Generate ABAP** and explicitly confirm satisfactory code
11. Generate SIT and UAT cases, then record approvals and testing confirmation
12. Review the automatically generated audit report; close the project manually

The workspace includes:

- Orchestrator chat
- Files
- Project Status
- Artifact versions and approvals
- Context usage and compaction

## CLI

Run with the server active:

```powershell
./.venv/Scripts/cowork.exe login

./.venv/Scripts/cowork.exe projects create --name "STO Automation"
./.venv/Scripts/cowork.exe projects open <id>

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

Upload project context using:

```powershell
./.venv/Scripts/cowork.exe files upload <path> --domain SAP
```

Register an upstream artifact using:

```powershell
./.venv/Scripts/cowork.exe files upload <path> --artifact-type FRD
```

## Repository map

| Directory | Responsibility |
| --- | --- |
| `backend/app/models.py` | Domain models and interface contracts |
| `backend/app/orchestrator.py` | Stable orchestration import used by existing callers |
| `backend/app/langgraph_orchestrator.py` | LangGraph execution and runtime pause/resume |
| `backend/app/legacy_orchestrator.py` | Retained original runtime for parity tests and rollback |
| `backend/app/runtime.py` | Runtime composition and capability registration |
| `backend/app/state_management.py` | Validated state operations, revisions, progression and confirmations |
| `backend/app/artifact_lifecycle.py` | Draft edits, versions, comparisons and downstream impact |
| `backend/app/document_conversion.py` | Word document conversion |
| `backend/app/storage.py` | Storage interface |
| `backend/app/local_storage.py` | Local storage implementation |
| `backend/app/model_gateway.py` | Model gateway and provider adapters |
| `backend/app/api.py` | FastAPI endpoints |
| `backend/app/services.py` | Shared application services |
| `cli/` | CLI client |
| `frontend/` | Project workspace UI |
| `templates/` | BRD / FRD / TDD / UAT templates |
| `test_fixtures/` | STO reference requirement |

## Architecture

LangGraph runs orchestration behind the existing API. Domain state, memory, artifacts, context, and provider interfaces remain in their existing services. See [the migration summary](docs/LANGGRAPH_MIGRATION.md) for the function map and checkpoint boundaries.

```text
React UI / CLI
      ↓
FastAPI / Application Services
      ↓
AI Layer
 ├─ Orchestrator
 ├─ Context Handling
 ├─ Model Gateway
 ├─ Artifact Workers
 └─ Project Management
      ↓
Project State / Memory / Context / Artifacts
      ↓
Storage Provider
```

The AI Layer uses replaceable interfaces for:

- Model providers
- Storage
- Skills / tools
- Artifact workers
- ABAP generation

Project state is structured and persistent. Project memory is maintained separately as a summarized Markdown document. Context is loaded based on the current task across:

- Business
- SAP
- Organization
- Historical Development
- SDLC

## UI development

From `frontend/`:

```powershell
npm run dev
```

The default application build is served directly by FastAPI.
