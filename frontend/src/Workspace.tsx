import { useState, useRef, useEffect } from "react";
import {
  ArrowLeft,
  Layers3,
  PanelRightClose,
  PanelRightOpen,
  Settings2,
  RefreshCw,
} from "lucide-react";
import type { Workspace as WorkspaceData } from "./types";
import { FilesRail, DocumentViewer } from "./Files";
import ProjectStatus from "./ProjectStatus";
import { streamChat, request } from "./api";
import { STAGES, type ChatInput } from "./types";
import Chat from "./Chat";
import ContextBar from "./ContextBar";
import ProjectMetadata, { type Metadata } from "./ProjectMetadata";

export default function Workspace({
  workspace,
  onChange: applyChange,
  onBack,
  onSettings,
}: {
  workspace: WorkspaceData;
  onChange: (w: WorkspaceData) => void;
  onBack: () => void;
  onSettings: () => void;
}) {
  const acceptingResults = useRef(true);
  const latestSnapshot = useRef(workspace.snapshot_at);
  useEffect(() => {
    acceptingResults.current = true;
    return () => {
      acceptingResults.current = false;
    };
  }, []);
  const onChange = (value: WorkspaceData) => {
    if (!acceptingResults.current) return;
    if (
      value.snapshot_at &&
      latestSnapshot.current &&
      value.snapshot_at < latestSnapshot.current
    )
      return;
    if (value.snapshot_at) latestSnapshot.current = value.snapshot_at;
    applyChange(value);
  };
  const [editingMetadata, setEditingMetadata] = useState(false);
  const [metadata, setMetadata] = useState<Metadata>({
    organization_id: workspace.project.organization_id,
    program_id: workspace.project.program_id,
    sap_applicability: workspace.project.sap_applicability || {},
  });
  const [tab, setTab] = useState<"files" | "status">("status"),
    [rail, setRail] = useState(true);
  const [document, setDocument] = useState<{
    id: string;
    version?: string;
  } | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [progress, setProgress] = useState(""),
    [lastInput, setLastInput] = useState<ChatInput | null>(null);
  async function act(input: ChatInput) {
    const task = {
      ...input,
      task_id: input.task_id || crypto.randomUUID(),
      expected_revision:
        input.expected_revision ?? workspace.state.state_revision,
    };
    setLastInput(task);
    setBusy(true);
    setProgress(
      input.action === "answer" ? "processing_answer" : "understanding",
    );
    setError("");
    try {
      const r = await streamChat(
        workspace.project.project_id,
        task,
        setProgress,
      );
      onChange(r.workspace);
      if (r.error) setError(r.error);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setProgress("");
    }
  }
  return (
    <main className="workspace">
      {editingMetadata && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-label="Edit project metadata"
          >
            <h2>Project metadata</h2>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                try {
                  const updated = await request<WorkspaceData>(
                    `/projects/${workspace.project.project_id}/metadata`,
                    {
                      method: "PUT",
                      body: JSON.stringify({
                        ...metadata,
                        expected_revision: workspace.state.state_revision,
                        request_id: crypto.randomUUID(),
                      }),
                    },
                  );
                  onChange(updated);
                  setEditingMetadata(false);
                } catch (err) {
                  setError((err as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <ProjectMetadata value={metadata} onChange={setMetadata} />
              <button disabled={busy}>Save project metadata</button>
              <button type="button" onClick={() => setEditingMetadata(false)}>
                Cancel
              </button>
              {error && <p role="alert">{error}</p>}
            </form>
          </section>
        </div>
      )}
      <header className="topbar">
        <div className="workspace-heading">
          <button
            aria-label="All projects"
            onClick={() => {
              acceptingResults.current = false;
              onBack();
            }}
          >
            <ArrowLeft size={17} />
          </button>
          <div className="brand">
            <Layers3 size={22} /> SAP CoWork
          </div>
          <span className="header-divider" />
          <div>
            <strong>{workspace.project.project_name}</strong>
          </div>
        </div>
        <div className="header-actions">
          <label>
            Work on:
            <select
              aria-label="Work on"
              value={
                workspace.state.current_draft_stage ||
                workspace.status.current_stage
              }
              disabled={
                busy ||
                (workspace.state.project_status !== undefined &&
                  workspace.state.project_status !== "active")
              }
              onChange={(e) =>
                act({
                  action: "set_stage",
                  stage: e.target.value as ChatInput["stage"],
                })
              }
            >
              {STAGES.map((stage) => (
                <option key={stage}>{stage}</option>
              ))}
            </select>
          </label>
          <span className="badge">
            Current Stage:{" "}
            {workspace.state.current_approved_stage || "Planning"}
          </span>
          <details className="project-menu">
            <summary aria-label="Project actions">⋯</summary>
            <div className="project-menu-options">
              <button
                disabled={
                  busy ||
                  Boolean(
                    workspace.state.project_status &&
                    workspace.state.project_status !== "active",
                  )
                }
                onClick={() => setEditingMetadata(true)}
              >
                Project metadata
              </button>

              {workspace.state.project_status &&
              workspace.state.project_status !== "active" ? (
                <button
                  disabled={busy}
                  onClick={() => act({ action: "reopen_project" })}
                >
                  Reopen project
                </button>
              ) : (
                <button
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        "Close this project? It will become read-only and be marked completed or incomplete based on its approvals and confirmations.",
                      )
                    )
                      act({ action: "close_project" });
                  }}
                >
                  Close project
                </button>
              )}
            </div>
          </details>
          <button
            aria-label="Refresh project"
            disabled={busy}
            onClick={async () => {
              try {
                onChange(
                  await request<WorkspaceData>(
                    "/projects/" + workspace.project.project_id,
                  ),
                );
                setError("");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <RefreshCw size={16} />
          </button>
          <button aria-label="Provider settings" onClick={onSettings}>
            <Settings2 size={17} />
          </button>
          <button
            aria-label={rail ? "Collapse project rail" : "Expand project rail"}
            onClick={() => setRail(!rail)}
          >
            {rail ? (
              <PanelRightClose size={18} />
            ) : (
              <PanelRightOpen size={18} />
            )}
          </button>
        </div>
      </header>
      <div className={"workspace-body " + (!rail ? "rail-collapsed" : "")}>
        <section className="main-panel">
          {error && (
            <div role="alert">
              {error}{" "}
              {lastInput && (
                <button disabled={busy} onClick={() => act(lastInput)}>
                  Retry request
                </button>
              )}
            </div>
          )}
          {document ? (
            <DocumentViewer
              projectId={workspace.project.project_id}
              artifactId={document.id}
              version={document.version}
              versions={workspace.state.artifact_registry}
              onVersion={(v) => setDocument({ ...document, version: v })}
              onBack={() => setDocument(null)}
              onChange={onChange}
              stateRevision={workspace.state.state_revision}
              readOnly={
                workspace.state.project_status !== undefined &&
                workspace.state.project_status !== "active"
              }
            />
          ) : (
            <Chat
              workspace={workspace}
              onChange={onChange}
              onAction={act}
              onOpen={(id, version) => setDocument({ id, version })}
              onAttach={() => {
                setTab("files");
                setRail(true);
              }}
              busy={busy}
              progress={progress}
              optimistic={busy ? lastInput?.message || "" : ""}
              pendingAction={busy ? lastInput?.action : undefined}
            >
              <ContextBar
                projectId={workspace.project.project_id}
                readOnly={
                  workspace.state.project_status !== undefined &&
                  workspace.state.project_status !== "active"
                }
                context={workspace.context}
                onCompact={() => act({ action: "compact" })}
                busy={
                  busy ||
                  (workspace.state.project_status !== undefined &&
                    workspace.state.project_status !== "active")
                }
              />
            </Chat>
          )}
          {document && (
            <ContextBar
              projectId={workspace.project.project_id}
              readOnly={
                workspace.state.project_status !== undefined &&
                workspace.state.project_status !== "active"
              }
              context={workspace.context}
              onCompact={() => act({ action: "compact" })}
              busy={
                busy ||
                (workspace.state.project_status !== undefined &&
                  workspace.state.project_status !== "active")
              }
            />
          )}
        </section>
        {rail && (
          <aside className="project-rail">
            <div
              className="rail-tabs"
              role="tablist"
              aria-label="Project navigation"
            >
              <button
                role="tab"
                aria-selected={tab === "files"}
                onClick={() => setTab("files")}
              >
                Files
              </button>
              <button
                role="tab"
                aria-selected={tab === "status"}
                onClick={() => setTab("status")}
              >
                Project Status
              </button>
            </div>
            <div className="rail-content">
              {tab === "files" ? (
                <FilesRail
                  workspace={workspace}
                  onOpen={(id, version) => setDocument({ id, version })}
                  onChange={onChange}
                />
              ) : (
                <ProjectStatus
                  status={workspace.status}
                  records={workspace.state}
                  expectedNextArtifact={workspace.state.expected_next_artifact}
                  onOpen={(id, version) => setDocument({ id, version })}
                  onAction={act}
                  busy={busy}
                />
              )}
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}
