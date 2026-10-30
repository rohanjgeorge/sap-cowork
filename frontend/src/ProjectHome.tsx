import { useEffect, useState } from "react";
import {
  ArrowRight,
  FolderOpen,
  Plus,
  Search,
  Settings2,
  Layers3,
  LogOut,
} from "lucide-react";
import { post, request } from "./api";
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
  const [projects, setProjects] = useState<ProjectSummary[]>([]),
    [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [stage, setStage] = useState("Planning"),
    [requirement, setRequirement] = useState(""),
    [filter, setFilter] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [suggested, setSuggested] = useState<Stage>("Planning"),
    [confirmed, setConfirmed] = useState(false);
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
          <button aria-label="Provider settings" onClick={onSettings}>
            <Settings2 size={17} /> Settings
          </button>
          <button aria-label="Sign out" onClick={onLogout}>
            <LogOut size={17} />
          </button>
          <span className="avatar">L</span>
        </div>
      </header>
      <div className="home-content">
        <div className="home-heading">
          <div>
            <p className="eyebrow">YOUR DEVELOPMENT WORKSPACE</p>
            <h1>Good work starts with context.</h1>
            <p className="subtle">
              Create something new, or pick up the thread on an existing
              project.
            </p>
          </div>
          <button className="primary" onClick={() => setCreating(true)}>
            <Plus size={18} /> New project
          </button>
        </div>
        <section className="start-panel">
          <div className="start-icon">
            <Layers3 size={30} />
          </div>
          <div>
            <p className="eyebrow">ONE PROJECT. EVERY STAGE.</p>
            <h2>From a business need to a technical plan.</h2>
            <p>
              Keep requirements, decisions and artifacts connected across the
              SAP lifecycle.
            </p>
          </div>
          <button onClick={() => setCreating(true)}>
            Start a project <ArrowRight size={18} />
          </button>
        </section>
        <section className="projects-section">
          <div className="section-heading">
            <h2>
              Your projects <span className="count">{projects.length}</span>
            </h2>
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
          <div className="project-grid">
            {projects
              .filter((p) =>
                p.project_name.toLowerCase().includes(filter.toLowerCase()),
              )
              .map((p) => (
                <button
                  className="project-card"
                  key={p.project_id}
                  onClick={() => open(p.project_id)}
                  disabled={busy}
                >
                  <div className="card-top">
                    <FolderOpen size={23} />
                    <span className="badge">{p.status.current_stage}</span>
                  </div>
                  <h3>{p.project_name}</h3>
                  <p>{p.description || p.status.recommended_next_action}</p>
                  <div className="mini-stages">
                    {p.status.stages.map((s) => (
                      <span
                        title={s.stage + ": " + s.label}
                        className={s.color}
                        key={s.stage}
                      />
                    ))}
                  </div>
                  <div className="card-bottom">
                    <span>
                      Updated {new Date(p.updated_at).toLocaleDateString()}
                    </span>
                    <ArrowRight size={16} />
                  </div>
                </button>
              ))}
          </div>
          {projects.length === 0 && (
            <p className="empty">
              <FolderOpen /> Your first project starts here. Create a project to
              begin.
            </p>
          )}
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
              <h2 id="new-project-title">Create a project</h2>
              <button
                onClick={() => setCreating(false)}
                aria-label="Close new project"
              >
                ×
              </button>
            </div>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                try {
                  onOpen(
                    await post<Workspace>("/projects", {
                      project_name: name,
                      stage: stage === "unknown" ? suggested : stage,
                      requirement,
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
                Current SDLC stage
                <select
                  value={stage}
                  onChange={(e) => {
                    setStage(e.target.value);
                    setConfirmed(false);
                  }}
                >
                  {STAGES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                  <option value="unknown">I don’t know — help me choose</option>
                </select>
              </label>
              {stage === "unknown" && (
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
                <span className="muted">Optional — you can add it in chat</span>
                <textarea
                  rows={4}
                  value={requirement}
                  onChange={(e) => setRequirement(e.target.value)}
                  placeholder="What would you like to build?"
                />
              </label>
              <p className="muted">
                Add upstream documents in the project Files tab. Missing
                approvals will remain visible in Project Status.
              </p>
              <button
                className="primary"
                disabled={
                  busy || !name.trim() || (stage === "unknown" && !confirmed)
                }
              >
                {busy ? "Creating…" : "Create project"} <ArrowRight size={17} />
              </button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
