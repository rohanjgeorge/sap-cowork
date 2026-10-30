import { useState } from "react";
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
import type { ChatInput } from "./types";
import Chat from "./Chat";
import ContextBar from "./ContextBar";

export default function Workspace({
  workspace,
  onChange,
  onBack,
  onSettings,
}: {
  workspace: WorkspaceData;
  onChange: (w: WorkspaceData) => void;
  onBack: () => void;
  onSettings: () => void;
}) {
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
    const task = { ...input, task_id: input.task_id || crypto.randomUUID() };
    setLastInput(task);
    setBusy(true);
    setProgress("understanding");
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
      <header className="topbar">
        <div className="workspace-heading">
          <button aria-label="All projects" onClick={onBack}>
            <ArrowLeft size={17} />
          </button>
          <div className="brand">
            <Layers3 size={22} /> SAP CoWork
          </div>
          <span className="header-divider" />
          <div>
            <strong>{workspace.project.project_name}</strong>
            <div className="muted">
              {workspace.state.current_task || "Ready for your next step"}
            </div>
          </div>
        </div>
        <div className="header-actions">
          <span className="badge">{workspace.status.current_stage}</span>
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
            />
          ) : (
            <Chat
              workspace={workspace}
              onAction={act}
              onOpen={(id, version) => setDocument({ id, version })}
              onAttach={() => {
                setTab("files");
                setRail(true);
              }}
              busy={busy}
              progress={progress}
              optimistic={busy ? lastInput?.message || "" : ""}
            >
              <ContextBar
                context={workspace.context}
                onCompact={() => act({ action: "compact" })}
                busy={busy}
              />
            </Chat>
          )}
          {document && (
            <ContextBar
              context={workspace.context}
              onCompact={() => act({ action: "compact" })}
              busy={busy}
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
