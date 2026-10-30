import { useEffect, useState } from "react";
import { ArrowRight, Layers3 } from "lucide-react";
import { post, request } from "./api";
import ProjectHome from "./ProjectHome";
import type { Workspace } from "./types";
import ProjectWorkspace from "./Workspace";
import Settings from "./Settings";

export function Login({ onLogin }: { onLogin: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <section className="login-story">
        <div className="brand">
          <Layers3 /> SAP CoWork
        </div>
        <p className="eyebrow">FROM REQUIREMENT TO RELEASE READINESS</p>
        <h1>
          Your project.
          <br />
          One continuous
          <br />
          workspace.
        </h1>
        <p>
          Bring business context, SAP knowledge and development decisions
          together across your project lifecycle.
        </p>
        <div className="stage-line">
          Planning <span>→</span> Analysis <span>→</span> Design <span>→</span>{" "}
          Development <span>→</span> Testing
        </div>
      </section>
      <section className="login-form">
        <p className="eyebrow">WELCOME TO YOUR WORKSPACE</p>
        <h2>Pick up where you left off.</h2>
        <p>Sign in to create a project or continue your work.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await post("/session", { access_code: code });
              onLogin();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Local access code
            <input
              aria-label="Local access code"
              type="password"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <small>
            For a local workspace without a configured code, leave this empty.
          </small>
          {error && <p role="alert">{error}</p>}
          <button className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Enter workspace"} <ArrowRight size={17} />
          </button>
        </form>
        <p className="muted">
          Local single-user session · Enterprise SSO is deferred
        </p>
      </section>
    </main>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [settings, setSettings] = useState(false);
  useEffect(() => {
    request("/session")
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false));
  }, []);
  if (authenticated === null)
    return (
      <main className="loading" role="status">
        Opening SAP CoWork…
      </main>
    );
  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />;
  return (
    <>
      {workspace ? (
        <ProjectWorkspace
          workspace={workspace}
          onChange={setWorkspace}
          onBack={() => setWorkspace(null)}
          onSettings={() => setSettings(true)}
        />
      ) : (
        <ProjectHome
          onOpen={setWorkspace}
          onSettings={() => setSettings(true)}
          onLogout={async () => {
            await request("/session", { method: "DELETE" });
            setAuthenticated(false);
          }}
        />
      )}
      {settings && (
        <Settings
          onClose={() => {
            setSettings(false);
            if (workspace)
              request<Workspace>(
                "/projects/" + workspace.project.project_id,
              ).then(setWorkspace);
          }}
        />
      )}
    </>
  );
}
