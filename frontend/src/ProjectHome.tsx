import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  FolderOpen,
  Plus,
  Search,
  Settings2,
  Layers3,
  LogOut,
} from "lucide-react";
import { post, request } from "./api";
import ProjectMetadata, { type Metadata } from "./ProjectMetadata";
import {
  STAGES,
  type Stage,
  type ProjectSummary,
  type Workspace,
} from "./types";

export default function ProjectHome({
  onOpen,
  onSettings,
  onLogout,
}: {
  onOpen: (w: Workspace) => void;
  onSettings: () => void;
  onLogout: () => void;
}) {
  const [startMode, setStartMode] = useState<"choose" | "scratch" | "existing">(
    "choose",
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [artifactStatuses, setArtifactStatuses] = useState<
    Record<string, "draft" | "approved">
  >({});
  const artifactStages = [
    ["Planning", ["BRD"]],
    ["Analysis", ["FRD", "USER_STORIES"]],
    ["Design", ["TDD"]],
    ["Development", ["ABAP"]],
    ["Testing", ["SIT", "UAT", "AUDIT_REPORT"]],
  ] as const;
  const begin = () => {
    setStartMode("choose");
    setCreating(true);
    setError("");
  };
  const [metadata, setMetadata] = useState<Metadata>({});
  const [projectTab, setProjectTab] = useState<"active" | "completed">(
    "active",
  );
  const [projects, setProjects] = useState<ProjectSummary[]>([]),
    [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [clientName, setClientName] = useState(""),
    [stage, setStage] = useState("Planning"),
    [requirement, setRequirement] = useState(""),
    [filter, setFilter] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [suggested, setSuggested] = useState<Stage>("Planning"),
    [confirmed, setConfirmed] = useState(false);
  const completedProjects = projects.filter(
    (project) =>
      project.status.project_status === "completed" ||
      project.status.project_status === "incomplete",
  );
  const activeProjects = projects.filter(
    (project) =>
      !project.status.project_status ||
      project.status.project_status === "active",
  );
  const tabProjects =
    projectTab === "active" ? activeProjects : completedProjects;
  const visibleProjects = tabProjects.filter((project) =>
    project.project_name.toLowerCase().includes(filter.toLowerCase()),
  );
  useEffect(() => {
    request<ProjectSummary[]>("/projects")
      .then(setProjects)
      .catch((e) => setError(e.message));
  }, []);
  async function open(id: string) {
    setBusy(true);
    try {
      onOpen(await request<Workspace>("/projects/" + id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="home">
      <header className="topbar">
        <div className="brand">
          <Layers3 /> SAP CoWork <span className="badge">WORKSPACE</span>
        </div>
        <div className="header-actions">
          <button className="primary" onClick={begin}>
            <Plus size={18} /> New project
          </button>
          <button aria-label="Provider settings" onClick={onSettings}>
            <Settings2 size={17} />{" "}
            <span className="home-settings-label">Settings</span>
          </button>
          <button aria-label="Sign out" onClick={onLogout}>
            <LogOut size={17} />
          </button>
          <span className="avatar">L</span>
        </div>
      </header>
      <div className="home-content">
        <section className="projects-section">
          <div className="section-heading">
            <h1>
              Your projects <span className="count">{projects.length}</span>
            </h1>
            <label className="search">
              <Search size={16} />
              <input
                aria-label="Search projects"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Search projects…"
              />
            </label>
          </div>
          {error && <p role="alert">{error}</p>}
          <div
            className="project-folder-tabs"
            role="tablist"
            aria-label="Project folders"
            onKeyDown={(event) => {
              if (
                !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              )
                return;
              event.preventDefault();
              const next =
                event.key === "Home"
                  ? "active"
                  : event.key === "End"
                    ? "completed"
                    : projectTab === "active"
                      ? "completed"
                      : "active";
              setProjectTab(next);
              event.currentTarget
                .querySelector<HTMLButtonElement>(`#projects-${next}-tab`)
                ?.focus();
            }}
          >
            {(["active", "completed"] as const).map((tab) => (
              <button
                key={tab}
                id={`projects-${tab}-tab`}
                role="tab"
                aria-selected={projectTab === tab}
                aria-controls="projects-panel"
                tabIndex={projectTab === tab ? 0 : -1}
                onClick={() => setProjectTab(tab)}
              >
                <FolderOpen size={18} aria-hidden="true" />
                {tab === "active" ? "Active" : "Completed"}
                <span className="count">
                  {tab === "active"
                    ? activeProjects.length
                    : completedProjects.length}
                </span>
              </button>
            ))}
          </div>
          <div
            className="project-folder-panel"
            id="projects-panel"
            role="tabpanel"
            aria-labelledby={`projects-${projectTab}-tab`}
            tabIndex={0}
          >
            <div className="project-grid">
              {visibleProjects.map((p) => (
                <button
                  className="project-card"
                  key={p.project_id}
                  onClick={() => open(p.project_id)}
                  disabled={busy}
                >
                  <div className="project-card-title">
                    <FolderOpen size={20} aria-hidden="true" />
                    <h3>{p.project_name}</h3>
                  </div>
                  {p.client_name && (
                    <span className="project-card-client">
                      Client: {p.client_name}
                    </span>
                  )}
                  <div className="project-card-details">
                    <span className="badge">
                      SDLC:{" "}
                      {p.status.current_draft_stage || p.status.current_stage}
                    </span>
                    <time dateTime={p.updated_at}>
                      Updated {new Date(p.updated_at).toLocaleDateString()}
                    </time>
                  </div>
                  {p.status.project_status === "incomplete" && (
                    <span className="muted">Closed incomplete</span>
                  )}
                </button>
              ))}
            </div>
            {visibleProjects.length === 0 && (
              <p className="empty">
                <FolderOpen aria-hidden="true" />
                {filter.trim()
                  ? "No projects match your search in this folder."
                  : projectTab === "completed"
                    ? "No completed projects yet."
                    : "No active projects. Create a project to begin."}
              </p>
            )}
          </div>
        </section>
        <footer className="home-footer">
          PROJECT CONTEXT THAT STAYS WITH YOU{" "}
          <span>Planning · Analysis · Design · Development · Testing</span>
        </footer>
      </div>
      {creating && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-project-title"
          >
            <div className="section-heading">
              <div className="new-project-heading">
                {startMode !== "choose" && (
                  <button
                    type="button"
                    aria-label="Back to start options"
                    disabled={busy}
                    onClick={() => setStartMode("choose")}
                  >
                    <ArrowLeft size={18} />
                  </button>
                )}
                <h2 id="new-project-title">
                  {startMode === "choose"
                    ? "How would you like to start?"
                    : startMode === "existing"
                      ? "Start with approved requirements"
                      : "Create a project"}
                </h2>
              </div>
              <button
                onClick={() => setCreating(false)}
                aria-label="Close new project"
              >
                ×
              </button>
            </div>
            {startMode === "choose" ? (
              <div className="project-start-tiles">
                <button
                  className="project-start-tile"
                  onClick={() => setStartMode("scratch")}
                >
                  <Plus size={24} />
                  <strong>
                    Start from scratch with the client requirement
                  </strong>
                  <span>
                    Share the requirement and create your SDLC artifacts with
                    CoWork.
                  </span>
                </button>
                <button
                  className="project-start-tile"
                  onClick={() => setStartMode("existing")}
                >
                  <FolderOpen size={24} />
                  <strong>I have some requirements already approved</strong>
                  <span>
                    Select your documents and mark each as Draft or Approved,
                    then upload them one at a time.
                  </span>
                </button>
              </div>
            ) : (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  setError("");
                  try {
                    onOpen(
                      await post<Workspace>("/projects", {
                        project_name: name,
                        ...(clientName.trim()
                          ? { client_name: clientName.trim() }
                          : {}),
                        stage:
                          startMode === "scratch"
                            ? "Planning"
                            : stage === "unknown"
                              ? suggested
                              : stage,
                        requirement,
                        ...metadata,
                        ...(startMode === "existing"
                          ? {
                              import_artifacts: selected,
                              import_artifact_statuses: Object.fromEntries(
                                selected.map((kind) => [
                                  kind,
                                  artifactStatuses[kind] || "draft",
                                ]),
                              ),
                            }
                          : {}),
                      }),
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label>
                  Project name
                  <input
                    autoFocus
                    required
                    maxLength={150}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label>
                  Client name
                  <input
                    maxLength={150}
                    value={clientName}
                    onChange={(e) => setClientName(e.target.value)}
                  />
                </label>
                <label>
                  Current SDLC stage
                  <select
                    value={startMode === "scratch" ? "Planning" : stage}
                    disabled={startMode === "scratch"}
                    onChange={(e) => {
                      setStage(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    {STAGES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                    <option value="unknown">
                      I don’t know — help me choose
                    </option>
                  </select>
                </label>
                {startMode === "existing" && stage === "unknown" && (
                  <>
                    <label>
                      Latest available artifact
                      <select
                        onChange={async (e) => {
                          const r = await post<{ suggested_stage: Stage }>(
                            "/stage-suggestion",
                            e.target.value ? [e.target.value] : [],
                          );
                          setSuggested(r.suggested_stage);
                          setConfirmed(false);
                        }}
                      >
                        <option value="">No artifacts yet</option>
                        {["BRD", "FRD", "TDD", "ABAP"].map((a) => (
                          <option key={a}>{a}</option>
                        ))}
                      </select>
                    </label>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        onChange={(e) => setConfirmed(e.target.checked)}
                      />{" "}
                      Confirm {suggested} as my starting stage
                    </label>
                  </>
                )}
                <label>
                  Requirement or change request{" "}
                  <span className="muted">
                    Optional — you can add it in chat
                  </span>
                  <textarea
                    rows={4}
                    value={requirement}
                    onChange={(e) => setRequirement(e.target.value)}
                    placeholder="What would you like to build?"
                  />
                </label>
                {startMode === "existing" && (
                  <fieldset className="artifact-checklist">
                    <legend>Which documents do you already have?</legend>
                    <p className="muted">
                      Choose each document's current status. Selecting Approved
                      records your offline approval for that document.
                    </p>
                    {artifactStages.map(([s, artifacts]) => (
                      <div key={s}>
                        <h3>{s}</h3>
                        {artifacts.map((kind) => (
                          <div className="artifact-import-row" key={kind}>
                            <label className="checkbox">
                              <input
                                type="checkbox"
                                checked={selected.includes(kind)}
                                onChange={(e) =>
                                  setSelected(
                                    e.target.checked
                                      ? [...selected, kind]
                                      : selected.filter((k) => k !== kind),
                                  )
                                }
                              />
                              {kind.replaceAll("_", " ")}
                            </label>
                            <div
                              role="radiogroup"
                              aria-label={`${kind.replaceAll("_", " ")} document status`}
                              className="artifact-import-status"
                            >
                              {(["draft", "approved"] as const).map(
                                (status) => (
                                  <label className="checkbox" key={status}>
                                    <input
                                      type="radio"
                                      name={`import-status-${kind}`}
                                      checked={
                                        (artifactStatuses[kind] || "draft") ===
                                        status
                                      }
                                      disabled={!selected.includes(kind)}
                                      onChange={() =>
                                        setArtifactStatuses({
                                          ...artifactStatuses,
                                          [kind]: status,
                                        })
                                      }
                                    />
                                    {status === "draft" ? "Draft" : "Approved"}
                                  </label>
                                ),
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </fieldset>
                )}
                <ProjectMetadata value={metadata} onChange={setMetadata} />
                <p className="muted">
                  {startMode === "existing"
                    ? "After starting, CoWork will ask for each document in SDLC order. Drafts stay draft; documents marked Approved record your offline approval."
                    : "Add upstream documents in the project Files tab. Missing approvals will remain visible in Project Status."}
                </p>
                <button
                  className="primary"
                  disabled={
                    busy ||
                    !name.trim() ||
                    (startMode === "existing" &&
                      stage === "unknown" &&
                      !confirmed) ||
                    (startMode === "existing" && !selected.length)
                  }
                >
                  {busy ? "Creating…" : "Create project"}{" "}
                  <ArrowRight size={17} />
                </button>
                {error && <p role="alert">{error}</p>}
              </form>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
