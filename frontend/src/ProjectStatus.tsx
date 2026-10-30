import { useEffect, useState } from "react";
import {
  Check,
  ChevronRight,
  Circle,
  FileText,
  AlertTriangle,
} from "lucide-react";
import type { ChatInput, ProjectStatus as Status, Stage } from "./types";

export default function ProjectStatus({
  status,
  onOpen,
  onAction,
  busy = false,
}: {
  status: Status;
  onOpen: (id: string, version?: string) => void;
  onAction: (action: ChatInput) => void;
  busy?: boolean;
}) {
  const [selected, setSelected] = useState<Stage>(status.current_stage);
  useEffect(() => setSelected(status.current_stage), [status.current_stage]);
  const stage = status.stages.find((s) => s.stage === selected)!;
  return (
    <section className="status-rail">
      <div className="section-heading">
        <h3>Project lifecycle</h3>
        <span className="badge">V1</span>
      </div>
      <p className="muted">Every stage, with the context to continue.</p>
      <div className="stage-ribbon">
        {status.stages.map((s, i) => (
          <button
            key={s.stage}
            data-testid={"stage-" + s.stage}
            data-status={s.color}
            className={
              "stage-button " + (selected === s.stage ? "selected" : "")
            }
            onClick={() => setSelected(s.stage)}
          >
            <span className={"stage-indicator " + s.color}>
              {s.color === "green" ? (
                <Check size={12} />
              ) : s.color === "amber" ? (
                <Circle size={8} fill="currentColor" />
              ) : (
                String(i + 1).padStart(2, "0")
              )}
            </span>
            <span className="stage-button-text">
              <strong>{s.stage}</strong>
              <small>{s.label}</small>
            </span>
            {status.recommended_stage === s.stage && (
              <span className="recommended-tag">Next</span>
            )}
            <ChevronRight size={13} />
          </button>
        ))}
      </div>
      <div className="stage-detail">
        <p className="eyebrow">STAGE DETAILS</p>
        <h3>{stage.stage}</h3>
        <p className="muted">Expected output: {stage.expected_artifact}</p>
        <div className="detail-section">
          <h4>Documents</h4>
          {stage.documents.length ? (
            stage.documents.map((d) => (
              <button
                className="status-document"
                key={d.artifact_id + d.version}
                onClick={() => onOpen(d.artifact_id, d.version)}
              >
                <FileText size={14} />
                <span>
                  {d.artifact_type} v{d.version}
                </span>
                <span className={"approval " + d.approval_status}>
                  {d.approval_status.replaceAll("_", " ")}
                </span>
              </button>
            ))
          ) : (
            <p className="muted">No document yet</p>
          )}
        </div>
        {stage.clarifications.length > 0 && (
          <div className="detail-section">
            <h4>Open clarifications</h4>
            {stage.clarifications.map((c) => (
              <p key={c.clarification_id} className="clarification-note">
                {c.question}
              </p>
            ))}
          </div>
        )}
        {stage.issues.length > 0 && (
          <div className="detail-section">
            <h4>Inputs and approval gaps</h4>
            {stage.issues.map((i) => (
              <div
                key={i.code}
                className={"project-issue " + i.severity}
                role="note"
              >
                <AlertTriangle size={15} />
                <div>
                  <strong>
                    {i.severity === "error" ? "Error" : "Warning"} ·{" "}
                    {i.blocking ? "Blocks execution" : "Non-blocking"}
                  </strong>
                  <p>{i.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}
        <button
          className="stage-action"
          disabled={busy}
          onClick={() =>
            onAction({
              action: "generate",
              artifact_type: stage.expected_artifact,
              message: "Generate " + stage.expected_artifact,
            })
          }
        >
          {stage.documents.length
            ? "Generate new version"
            : "Generate " + stage.expected_artifact}
          <ChevronRight size={14} />
        </button>
      </div>
      <div className="next-action">
        <p className="eyebrow">RECOMMENDED NEXT STEP</p>
        <p>{status.recommended_next_action || "Continue in chat"}</p>
        {status.recommended_stage && <span>{status.recommended_stage}</span>}
      </div>
    </section>
  );
}
