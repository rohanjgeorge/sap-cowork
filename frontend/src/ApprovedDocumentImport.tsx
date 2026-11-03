import { useState } from "react";
import { Upload } from "lucide-react";
import { request } from "./api";
import type { Workspace } from "./types";
export default function ApprovedDocumentImport({
  workspace,
  onChange,
}: {
  workspace: Workspace;
  onChange: (w: Workspace) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const queue = workspace.onboarding;
  if (!queue) return null;
  const kind = queue.pending_artifacts[0];
  const status = queue.artifact_statuses?.[kind] || "approved";
  return (
    <section
      className="approved-import"
      aria-label="Approved document onboarding"
    >
      <p className="eyebrow">COWORK · PROJECT SETUP</p>
      <h2>
        {queue.complete
          ? "Your documents are ready"
          : `Upload ${status} ${kind.replaceAll("_", " ")}`}
      </h2>
      <p>{queue.message}</p>
      <ol className="import-progress">
        {queue.selected_artifacts.map((a) => (
          <li key={a} aria-current={a === kind ? "step" : undefined}>
            {queue.pending_artifacts.includes(a) ? "○" : "✓"}{" "}
            {a.replaceAll("_", " ")} ·{" "}
            {queue.artifact_statuses?.[a] || "approved"}
          </li>
        ))}
      </ol>
      {!queue.complete && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!file) return;
            setBusy(true);
            setError("");
            const data = new FormData();
            data.append("file", file);
            data.append("artifact_type", kind);
            data.append("request_id", requestId);
            if (workspace.state.state_revision !== undefined)
              data.append(
                "expected_revision",
                String(workspace.state.state_revision),
              );
            try {
              onChange(
                await request<Workspace>(
                  `/projects/${workspace.project.project_id}/onboarding/upload`,
                  { method: "POST", body: data },
                ),
              );
              setFile(null);
              setRequestId(crypto.randomUUID());
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            {status === "approved" ? "Approved" : "Draft"}{" "}
            {kind.replaceAll("_", " ")} document
            <input
              key={kind}
              type="file"
              disabled={busy}
              accept=".docx,.pdf,.txt,.md,.json,.abap,.csv"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setRequestId(crypto.randomUUID());
                setError("");
              }}
            />
          </label>
          <p className="muted">
            {status === "approved"
              ? "This document will record your offline approval selected during setup."
              : "This document will be imported as a draft for review and later approval."}{" "}
            Choose a document with extractable text (maximum 10 MB).
          </p>
          <button className="primary" disabled={!file || busy}>
            <Upload size={16} />
            {busy
              ? "Importing…"
              : `Import ${status} ${kind.replaceAll("_", " ")}`}
          </button>
          {error && <p role="alert">{error}</p>}
        </form>
      )}
    </section>
  );
}
