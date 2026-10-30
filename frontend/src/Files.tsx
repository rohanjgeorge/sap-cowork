import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronDown,
  Download,
  FileText,
  Upload,
  Check,
  MessageSquare,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { diffLines } from "diff";
import { post, request } from "./api";
import type { Artifact, ArtifactRef, ChatResult, Workspace } from "./types";

export function FilesRail({
  workspace,
  onOpen,
  onChange,
}: {
  workspace: Workspace;
  onOpen: (id: string, version?: string) => void;
  onChange: (w: Workspace) => void;
}) {
  const [uploading, setUploading] = useState(false),
    [file, setFile] = useState<File | null>(null),
    [kind, setKind] = useState(""),
    [domain, setDomain] = useState("BUSINESS"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const uploads = workspace.assets.filter((a) => a.kind === "upload");
  return (
    <section className="files-rail">
      <div className="section-heading">
        <h3>Project files</h3>
        <button
          aria-label="Upload file"
          onClick={() => setUploading(!uploading)}
        >
          <Upload size={15} />
        </button>
      </div>
      <p className="muted">Your inputs and versioned deliverables.</p>
      {uploading && (
        <form
          className="upload-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!file) return;
            setBusy(true);
            setError("");
            try {
              const data = new FormData();
              data.append("file", file);
              data.append("domain", domain);
              if (kind) data.append("artifact_type", kind);
              const r = await request<{
                workspace: Workspace;
                text_extracted: boolean;
              }>("/projects/" + workspace.project.project_id + "/files", {
                method: "POST",
                body: data,
              });
              onChange(r.workspace);
              setUploading(false);
              if (!r.text_extracted)
                setError(
                  "Stored file. Supply a text description for scanned documents and images.",
                );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Choose file
            <input
              aria-label="Choose file"
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <label>
            Register as
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Supporting file</option>
              {["BRD", "FRD", "TDD", "UAT", "ABAP", "AUDIT_REPORT"].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label>
            Context domain
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              {[
                "BUSINESS",
                "SAP",
                "ORGANIZATION",
                "HISTORICAL_DEVELOPMENT",
                "SDLC",
              ].map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={!file || busy}>
            {busy ? "Uploading…" : "Add to project"}
          </button>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
      <details open className="file-folder">
        <summary>
          <ChevronDown size={13} /> Uploads <span>{uploads.length}</span>
        </summary>
        {uploads.map((u) => (
          <a
            key={u.file_id}
            className="upload-link"
            href={
              "/api/projects/" +
              workspace.project.project_id +
              "/files/" +
              u.file_id
            }
            download={u.name}
          >
            <FileText size={14} />
            <span>{u.name}</span>
            <Download size={13} />
          </a>
        ))}
        {!uploads.length && (
          <p className="muted folder-empty">No uploads yet</p>
        )}
      </details>
      {["BRD", "FRD", "TDD", "ABAP", "UAT", "AUDIT_REPORT"].map((kind) => {
        const versions = workspace.state.artifact_registry
          .filter((a) => a.artifact_type === kind)
          .sort((a, b) => Number(b.version) - Number(a.version));
        return (
          <details
            key={kind}
            open={versions.length > 0}
            className="file-folder"
          >
            <summary>
              <ChevronDown size={13} />{" "}
              {kind === "AUDIT_REPORT" ? "Audit" : kind}{" "}
              <span>{versions.length}</span>
            </summary>
            {versions.map((a) => (
              <button
                key={a.artifact_id + a.version}
                className="file-row"
                onClick={() => onOpen(a.artifact_id, a.version)}
              >
                <FileText size={15} />
                <span>
                  {kind} v{a.version}
                </span>
                <span className={"approval " + a.approval_status}>
                  {a.approval_status.replaceAll("_", " ")}
                </span>
              </button>
            ))}
          </details>
        );
      })}
    </section>
  );
}

export function DocumentViewer({
  projectId,
  artifactId,
  version,
  versions,
  onVersion,
  onBack,
  onChange,
}: {
  projectId: string;
  artifactId: string;
  version?: string;
  versions: ArtifactRef[];
  onVersion: (v: string) => void;
  onBack: () => void;
  onChange: (w: Workspace) => void;
}) {
  const [artifact, setArtifact] = useState<Artifact | null>(null),
    [error, setError] = useState(""),
    [feedback, setFeedback] = useState(""),
    [revising, setRevising] = useState(false),
    [busy, setBusy] = useState(false);
  const [previous, setPrevious] = useState<Artifact | null>(null),
    [comparing, setComparing] = useState(false);
  useEffect(() => {
    let active = true;
    setArtifact(null);
    setPrevious(null);
    setComparing(false);
    setError("");
    request<Artifact>(
      `/projects/${projectId}/artifacts/${artifactId}` +
        (version ? "?version=" + version : ""),
    )
      .then((a) => {
        if (active) setArtifact(a);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [projectId, artifactId, version]);
  async function review(approve: boolean) {
    if (!artifact) return;
    setBusy(true);
    setError("");
    try {
      const r = await post<ChatResult>(
        `/projects/${projectId}/artifacts/${artifactId}/review`,
        {
          action: approve ? "approve" : "reject",
          version: artifact.artifact_version,
          feedback,
        },
      );
      onChange(r.workspace);
      setArtifact(r.artifact || artifact);
      setRevising(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="document-panel">
      <div className="document-toolbar">
        <button onClick={onBack}>
          <ArrowLeft size={15} /> Back to chat
        </button>
        <label className="version-label">
          Version
          <select
            aria-label="Artifact version"
            value={version || artifact?.artifact_version || ""}
            onChange={(e) => onVersion(e.target.value)}
          >
            {versions
              .filter((v) => v.artifact_id === artifactId)
              .sort((a, b) => Number(b.version) - Number(a.version))
              .map((v) => (
                <option value={v.version} key={v.version}>
                  v{v.version} · {v.approval_status.replaceAll("_", " ")}
                </option>
              ))}
          </select>
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {!artifact && !error && <p role="status">Loading artifact…</p>}
      {artifact && (
        <>
          <div className="document-meta">
            <div>
              <p className="eyebrow">
                {artifact.artifact_type} · VERSION {artifact.artifact_version}
              </p>
              <span className={"approval " + artifact.approval_status}>
                {artifact.approval_status.replaceAll("_", " ")}
              </span>
            </div>
            <p>
              Created {new Date(artifact.created_date).toLocaleString()}
              <br />
              Edited by {artifact.edited_by || "Unknown"} · Approved by{" "}
              {artifact.approved_by || "Awaiting approval"}
              <br />
              Template {artifact.template_version}
            </p>
          </div>
          {artifact.feedback && (
            <p className="revision-note">
              Revision feedback: {artifact.feedback}
            </p>
          )}
          <article className="document-content">
            {artifact.artifact_type === "ABAP" ? (
              <pre>
                <code>{artifact.content}</code>
              </pre>
            ) : (
              <ReactMarkdown>{artifact.content}</ReactMarkdown>
            )}
          </article>
          <div className="document-actions">
            {Number(artifact.artifact_version) > 1 && (
              <button
                disabled={busy}
                onClick={async () => {
                  if (comparing) {
                    setComparing(false);
                    return;
                  }
                  setBusy(true);
                  try {
                    const p = await request<Artifact>(
                      `/projects/${projectId}/artifacts/${artifactId}?version=${Number(artifact.artifact_version) - 1}`,
                    );
                    setPrevious(p);
                    setComparing(true);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {comparing ? "Hide comparison" : "Compare with previous"}
              </button>
            )}
            <button
              className="primary"
              onClick={() => review(true)}
              disabled={busy || artifact.approval_status === "approved"}
            >
              <Check size={16} /> Approve artifact
            </button>
            <button onClick={() => setRevising(!revising)} disabled={busy}>
              <MessageSquare size={16} /> Request changes
            </button>
          </div>
          {revising && (
            <form
              className="revision-form"
              onSubmit={(e) => {
                e.preventDefault();
                review(false);
              }}
            >
              <label>
                Revision feedback
                <textarea
                  autoFocus
                  required
                  rows={3}
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
              </label>
              <button disabled={busy || !feedback.trim()}>
                Submit change request
              </button>
            </form>
          )}
          {comparing && previous && (
            <section aria-label="Version comparison" className="version-diff">
              <h3>
                v{previous.artifact_version} → v{artifact.artifact_version}
              </h3>
              <p className="muted">
                Added lines are marked +; removed lines are marked −.
              </p>
              <pre>
                {diffLines(previous.content, artifact.content).map(
                  (part, i) => (
                    <span
                      key={i}
                      className={
                        part.added
                          ? "diff-added"
                          : part.removed
                            ? "diff-removed"
                            : ""
                      }
                    >
                      {part.value.split("\n").map((line, n) => (
                        <span className="diff-line" key={n}>
                          {part.added ? "+ " : part.removed ? "− " : "  "}
                          {line}
                          {"\n"}
                        </span>
                      ))}
                    </span>
                  ),
                )}
              </pre>
            </section>
          )}
          <details className="source-details">
            <summary>Source references ({artifact.sources.length})</summary>
            {artifact.sources.map((s) => (
              <p key={s}>{s}</p>
            ))}
          </details>
        </>
      )}
    </section>
  );
}
