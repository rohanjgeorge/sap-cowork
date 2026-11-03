import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronRight,
  Circle,
  FileText,
  AlertTriangle,
  ArrowLeft,
} from "lucide-react";
import type {
  ChatInput,
  ProjectStatus as Status,
  Stage,
  ProjectRecords,
} from "./types";

type RecordView = "clarifications" | "decisions" | "flags";

export default function ProjectStatus({
  status,
  records,
  expectedNextArtifact,
  onOpen,
  onAction,
  busy = false,
}: {
  status: Status;
  records?: ProjectRecords;
  expectedNextArtifact?: string | null;
  onOpen: (id: string, version?: string) => void;
  onAction: (action: ChatInput) => void;
  busy?: boolean;
}) {
  const [selected, setSelected] = useState<Stage>(status.current_stage);
  const [recordView, setRecordView] = useState<RecordView | null>(null);
  const recordHeading = useRef<HTMLHeadingElement>(null);
  const recordButtons = useRef<
    Partial<Record<RecordView, HTMLButtonElement | null>>
  >({});
  const previousView = useRef<RecordView | null>(null);
  useEffect(() => setSelected(status.current_stage), [status.current_stage]);
  useEffect(() => {
    if (recordView) recordHeading.current?.focus();
    else if (previousView.current) {
      recordButtons.current[previousView.current]?.focus();
      previousView.current = null;
    }
  }, [recordView]);
  const stage = status.stages.find((s) => s.stage === selected)!;
  const titles = {
    clarifications: "Clarifications",
    decisions: "Decisions",
    flags: "Flags",
  };
  const recordLists = {
    clarifications: (
      records?.clarifications ??
      records?.open_clarifications ??
      status.open_clarifications
    ).map((c) => ({
      id: c.clarification_id,
      title: c.question,
      status: c.status === "resolved" ? "Resolved" : "Open",
      detail:
        c.resolution || c.response
          ? `Answer: ${c.resolution || c.response}`
          : "",
    })),
    decisions: (records?.decisions ?? []).map((d) => ({
      id: d.decision_id,
      title: d.description,
      status: "Recorded",
      detail: d.decided_by ? `Recorded by ${d.decided_by}` : "",
    })),
    flags: (records?.flags ?? status.flags ?? []).map((f) => ({
      id: f.flag_id,
      title: f.description,
      status: f.status === "resolved" ? "Resolved" : "Active",
      detail: f.type ? `Type: ${f.type}` : "",
    })),
  };
  if (recordView) {
    const entries = recordLists[recordView];
    return (
      <section className="status-rail">
        <div className="project-record-heading">
          <button
            aria-label="Back to project status"
            onClick={() => setRecordView(null)}
          >
            <ArrowLeft size={17} aria-hidden="true" />
          </button>
          <h3 ref={recordHeading} tabIndex={-1}>
            {titles[recordView]} ({entries.length})
          </h3>
        </div>
        {entries.length ? (
          <ul className="project-record-list" aria-label={titles[recordView]}>
            {entries.map((entry) => (
              <li key={entry.id}>
                <p className="project-record-title">{entry.title}</p>
                <span className="badge">{entry.status}</span>
                {entry.detail && <p className="muted">{entry.detail}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No {recordView} recorded.</p>
        )}
      </section>
    );
  }
  return (
    <section className="status-rail">
      <div className="section-heading">
        <h3>Project lifecycle</h3>
        <span className="badge">
          V1.1 · {status.project_status || "active"}
        </span>
      </div>
      <div className="project-record-counts" aria-label="Project records">
        {(["clarifications", "decisions", "flags"] as const).map((view) => (
          <button
            key={view}
            ref={(node) => {
              recordButtons.current[view] = node;
            }}
            onClick={() => {
              previousView.current = view;
              setRecordView(view);
            }}
          >
            <span>{titles[view]}</span>
            <strong>{recordLists[view].length}</strong>
          </button>
        ))}
      </div>
      <p className="muted project-stage-summary">
        Working on: {status.current_draft_stage || status.current_stage} ·
        Current Stage: {status.current_approved_stage || "Planning"}
      </p>
      <dl
        className="project-workflow-summary"
        aria-label="Project task summary"
      >
        <div>
          <dt>Current task</dt>
          <dd>{status.current_task || "No active task"}</dd>
        </div>
        <div>
          <dt>Expected next artifact</dt>
          <dd>
            {(expectedNextArtifact === undefined
              ? status.stages.find((s) => s.stage === status.current_stage)
                  ?.expected_artifact
              : expectedNextArtifact) || "Not scheduled"}
          </dd>
        </div>
        <div>
          <dt>Recommended next action</dt>
          <dd>{status.recommended_next_action || "Continue in chat"}</dd>
        </div>
      </dl>
      <div className="stage-ribbon">
        {status.stages.map((s, i) => (
          <button
            key={s.stage}
            data-testid={"stage-" + s.stage}
            data-status={s.color}
            aria-pressed={selected === s.stage}
            aria-label={`${s.stage}: ${s.label}${status.recommended_stage === s.stage ? " · Next" : ""}`}
            title={s.label}
            className={
              "stage-button " + (selected === s.stage ? "selected" : "")
            }
            disabled={
              busy ||
              (status.project_status !== undefined &&
                status.project_status !== "active")
            }
            onClick={() => {
              setSelected(s.stage);
              onAction({ action: "set_stage", stage: s.stage });
            }}
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
        {(stage.expected_artifacts || [stage.expected_artifact]).map((kind) => (
          <button
            key={kind}
            className="stage-action"
            disabled={
              busy ||
              (status.project_status !== undefined &&
                status.project_status !== "active")
            }
            onClick={() =>
              onAction({
                action: "generate",
                artifact_type: kind,
                message: "Generate " + kind,
              })
            }
          >
            {stage.documents.some((d) => d.artifact_type === kind)
              ? "Update " + kind
              : "Generate " + kind}
            <ChevronRight size={14} />
          </button>
        ))}
        {(selected === "Development" || selected === "Testing") && (
          <div className="detail-section">
            <p className="muted">
              Your confirmation records acceptance of the current{" "}
              {selected === "Development"
                ? "code version"
                : "SIT/UAT and code baseline"}
              .
            </p>
            <button
              disabled={
                busy ||
                (status.project_status !== undefined &&
                  status.project_status !== "active")
              }
              onClick={() =>
                onAction({
                  action:
                    selected === "Development"
                      ? "confirm_code"
                      : "confirm_testing",
                })
              }
            >
              {selected === "Development"
                ? "Confirm code is satisfactory"
                : "Confirm all applicable tests passed"}
            </button>
            {status.confirmations?.some(
              (c) =>
                c.active &&
                c.kind ===
                  (selected === "Development" ? "development" : "testing"),
            ) && (
              <button
                disabled={
                  busy ||
                  (status.project_status !== undefined &&
                    status.project_status !== "active")
                }
                onClick={() =>
                  onAction({
                    action:
                      selected === "Development"
                        ? "withdraw_development"
                        : "withdraw_testing",
                  })
                }
              >
                Withdraw confirmation
              </button>
            )}
          </div>
        )}
      </div>
      {status.flags
        ?.filter(
          (flag) =>
            !status.issues.some((issue) => issue.message === flag.description),
        )
        .map((flag) => (
          <p role="note" key={flag.flag_id}>
            {flag.description}
          </p>
        ))}
      {Object.entries(status.follow_ups || {})
        .filter(([, value]) => value.startsWith("retry_required"))
        .map(([kind]) => (
          <p role="note" key={kind}>
            {kind.replaceAll("_", " ")} needs retry. The recorded completion is
            retained.
          </p>
        ))}
    </section>
  );
}
