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
import remarkGfm from "remark-gfm";
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
    [busy, setBusy] = useState(false),
    [comparison, setComparison] = useState<{ diff: string } | null>(null),
    [confirmed, setConfirmed] = useState(false);
  const uploads = workspace.assets.filter((a) => a.kind === "upload");
  return (
    <section className="files-rail">
      <div className="section-heading">
        <h3>Project files</h3>
        <button
          aria-label="Upload file"
          disabled={
            workspace.state.project_status !== undefined &&
            workspace.state.project_status !== "active"
          }
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
              data.append("confirmed", String(confirmed));
              if (kind) data.append("artifact_type", kind);
              const r = await request<{
                workspace: Workspace;
                text_extracted: boolean;
                requires_confirmation?: boolean;
                comparison?: { diff: string };
              }>("/projects/" + workspace.project.project_id + "/files", {
                method: "POST",
                body: data,
              });
              onChange(r.workspace);
              if (r.requires_confirmation && r.comparison) {
                setComparison(r.comparison);
                return;
              }
              setComparison(null);
              setConfirmed(false);
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
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setComparison(null);
                setConfirmed(false);
              }}
            />
          </label>
          <label>
            Register as
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Supporting file</option>
              {[
                "BRD",
                "FRD",
                "USER_STORIES",
                "TDD",
                "SIT",
                "UAT",
                "ABAP",
                "AUDIT_REPORT",
              ].map((k) => (
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
                "FUNCTIONAL_PROCESS",
                "SAP_FUNCTIONAL",
                "SAP_TECHNICAL",
                "STANDARDS_GOVERNANCE",
              ].map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          {comparison && (
            <section aria-label="Uploaded document comparison">
              <p>
                Significant changes detected. Review before adopting the
                uploaded source.
              </p>
              <pre className="upload-comparison">{comparison.diff}</pre>
              <label>
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                Accept this uploaded document as the source of truth
              </label>
            </section>
          )}
          <button
            className="primary"
            disabled={
              !file ||
              busy ||
              (!!comparison && !confirmed) ||
              (workspace.state.project_status !== undefined &&
                workspace.state.project_status !== "active")
            }
          >
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
      {[
        "BRD",
        "FRD",
        "USER_STORIES",
        "TDD",
        "ABAP",
        "SIT",
        "UAT",
        "AUDIT_REPORT",
      ].map((kind) => {
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
  stateRevision,
  readOnly = false,
}: {
  projectId: string;
  artifactId: string;
  version?: string;
  versions: ArtifactRef[];
  onVersion: (v: string) => void;
  onBack: () => void;
  onChange: (w: Workspace) => void;
  stateRevision?: number;
  readOnly?: boolean;
}) {
  const [artifact, setArtifact] = useState<Artifact | null>(null),
    [error, setError] = useState(""),
    [feedback, setFeedback] = useState(""),
    [revising, setRevising] = useState(false),
    [busy, setBusy] = useState(false);
  const [previous, setPrevious] = useState<Artifact | null>(null),
    [comparing, setComparing] = useState(false);
  const [editing, setEditing] = useState(false),
    [content, setContent] = useState("");
  const [newVersion, setNewVersion] = useState(false),
    [authors, setAuthors] = useState(""),
    [remarks, setRemarks] = useState("");
  const latestVersion = versions
    .filter((v) => v.artifact_id === artifactId)
    .sort((a, b) => Number(b.version) - Number(a.version))[0]?.version;
  const archived =
    !!artifact &&
    !!latestVersion &&
    artifact.artifact_version !== latestVersion;
  useEffect(() => {
    let active = true;
    setArtifact(null);
    setPrevious(null);
    setComparing(false);
    setEditing(false);
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
      if (
        r.artifact &&
        r.artifact.artifact_version !== artifact.artifact_version
      )
        onVersion(r.artifact.artifact_version);
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
        <button disabled={busy} onClick={onBack}>
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
              Template {artifact.template_ref || artifact.template_version}
            </p>
          </div>
          {artifact.feedback && (
            <p className="revision-note">
              Revision feedback: {artifact.feedback}
            </p>
          )}
          {artifact.recommendations?.map((note) => (
            <p className="revision-note" key={note}>
              {note}
            </p>
          ))}
          {editing && (
            <form
              className="revision-form"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                try {
                  const r = await request<{
                    artifact: Artifact;
                    workspace: Workspace;
                  }>(`/projects/${projectId}/artifacts/${artifactId}`, {
                    method: "PUT",
                    body: JSON.stringify({
                      content,
                      new_version: newVersion,
                      authors,
                      remarks,
                      expected_revision: stateRevision,
                    }),
                  });
                  setArtifact(r.artifact);
                  onChange(r.workspace);
                  setEditing(false);
                  onVersion(r.artifact.artifact_version);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {artifact.approval_status === "approved" && (
                <p>
                  This version is approved. Saving creates a new Draft and
                  retains this approval.
                </p>
              )}
              <label>
                Document content
                <textarea
                  aria-label="Document content"
                  rows={18}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={newVersion}
                  onChange={(e) => setNewVersion(e.target.checked)}
                />
                Create a new version
              </label>
              <label>
                Authors
                <input
                  value={authors}
                  required={newVersion}
                  onChange={(e) => setAuthors(e.target.value)}
                />
              </label>
              <label>
                Change remarks
                <input
                  value={remarks}
                  required={newVersion}
                  onChange={(e) => setRemarks(e.target.value)}
                />
              </label>
              <button
                disabled={busy || readOnly || archived || !content.trim()}
              >
                Save document
              </button>
              <button type="button" onClick={() => setEditing(false)}>
                Cancel edit
              </button>
            </form>
          )}
          <article className="document-content">
            {artifact.artifact_type === "ABAP" ? (
              <pre>
                <code>{artifact.content}</code>
              </pre>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div
                      className="document-table-scroll"
                      tabIndex={0}
                      role="region"
                      aria-label="Document table"
                    >
                      <table>{children}</table>
                    </div>
                  ),
                }}
              >
                {artifact.content}
              </ReactMarkdown>
            )}
          </article>
          <div className="document-actions">
            <a
              href={`/api/projects/${projectId}/artifacts/${artifactId}/download?version=${artifact.artifact_version}`}
              download
            >
              <Download size={16} /> Download{" "}
              {artifact.artifact_type === "ABAP" ? "ABAP" : "Word document"}
            </a>
            <button
              disabled={busy || readOnly || archived}
              onClick={() => {
                setContent(artifact.content);
                setEditing(true);
              }}
            >
              Edit document
            </button>
            {artifact.approval_status === "draft" && (
              <>
                <button
                  disabled={busy || readOnly || archived}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    try {
                      const result = await post<{ workspace: Workspace }>(
                        `/projects/${projectId}/state/operations`,
                        {
                          operation: "submit_artifact",
                          payload: {
                            artifact_id: artifactId,
                            version: artifact.artifact_version,
                          },
                          expected_revision: stateRevision,
                          request_id: crypto.randomUUID(),
                        },
                      );
                      onChange(result.workspace);
                      setArtifact({
                        ...artifact,
                        approval_status: "pending_approval",
                      });
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Mark pending offline approval
                </button>
                <button
                  disabled={
                    busy ||
                    readOnly ||
                    (version !== undefined &&
                      version !==
                        versions
                          .filter((v) => v.artifact_id === artifactId)
                          .sort(
                            (a, b) => Number(b.version) - Number(a.version),
                          )[0]?.version)
                  }
                  onClick={async () => {
                    if (
                      !window.confirm(
                        "Delete the active Draft? The preceding version will become active again.",
                      )
                    )
                      return;
                    try {
                      onChange(
                        await request<Workspace>(
                          `/projects/${projectId}/artifacts/${artifactId}?version=${artifact.artifact_version}`,
                          { method: "DELETE" },
                        ),
                      );
                      onBack();
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Delete active Draft
                </button>
              </>
            )}
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
              title="Record the approval communicated to you offline"
              disabled={
                busy || readOnly || artifact.approval_status === "approved"
              }
            >
              <Check size={16} /> Approve artifact
            </button>
            <button
              onClick={() => setRevising(!revising)}
              disabled={busy || readOnly || archived}
            >
              <MessageSquare size={16} /> Request changes
            </button>
          </div>
          <p className="muted">
            Approvals are handled offline. Approve artifact records your
            declaration for this version.
          </p>
          {archived && (
            <p className="muted">
              Historical versions are read-only. Open the latest version to
              edit.
            </p>
          )}
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
              <button
                disabled={busy || readOnly || archived || !feedback.trim()}
              >
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
            {artifact.evidence_provenance?.map((source, i) => (
              <p key={source.source_id + ":" + i}>
                <strong>{source.original_uri || source.source}</strong>
                <br />
                {source.source_category} · {source.scope} · {source.domain} ·
                version {source.source_version || "not recorded"}
                <br />
                Evidence: {source.evidence_status || "unknown"}; authority:{" "}
                {source.authority || "unverified"}
              </p>
            ))}
            {artifact.context_gaps?.map((gap, i) => (
              <p role="note" key={gap.requirement_id + i}>
                {gap.reason}
                <br />
                <small>{gap.qualification}</small>
              </p>
            ))}
          </details>
        </>
      )}
    </section>
  );
}
