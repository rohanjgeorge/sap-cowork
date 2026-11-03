import ApprovedDocumentImport from "./ApprovedDocumentImport";
import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowUp,
  Check,
  FileText,
  Layers3,
  LoaderCircle,
  Paperclip,
  Sparkles,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatInput, Workspace } from "./types";

export default function Chat({
  workspace,
  onChange,
  onAction,
  onOpen,
  onAttach,
  busy,
  progress,
  optimistic,
  pendingAction,
  children,
}: {
  workspace: Workspace;
  onChange?: (workspace: Workspace) => void;
  onAction: (input: ChatInput) => void;
  onOpen: (id: string, version?: string) => void;
  onAttach: () => void;
  busy: boolean;
  progress: string;
  optimistic: string;
  pendingAction?: string;
  children?: ReactNode;
}) {
  const [message, setMessage] = useState("");
  const [submittedQuestionId, setSubmittedQuestionId] = useState<string | null>(
    null,
  );
  const processingId = useId();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [workspace.session.messages.length, busy, progress]);
  useEffect(() => {
    if (
      !busy &&
      submittedQuestionId &&
      !workspace.status.open_clarifications.some(
        (question) =>
          question.clarification_id === submittedQuestionId &&
          question.status === "open",
      )
    ) {
      setMessage("");
      setSubmittedQuestionId(null);
    }
  }, [busy, submittedQuestionId, workspace.status.open_clarifications]);
  const pending = workspace.status.open_clarifications.filter(
    (question) =>
      question.status === "open" &&
      (!workspace.state.active_task_id ||
        !question.task_id ||
        question.task_id === workspace.state.active_task_id),
  );
  const active = workspace.state.task_status === "awaiting_input";
  const answering = busy && pendingAction === "answer";
  const answerProgress: Record<string, string> = {
    planning_context: "Checking project context…",
    ready_to_execute: "Preparing to continue…",
    executing: "Continuing the task…",
    validating: "Checking the result…",
    awaiting_approval: "Preparing the response…",
  };
  const closed =
    workspace.state.project_status !== undefined &&
    workspace.state.project_status !== "active";
  return (
    <div className="chat-layout">
      <div className="workspace-chat">
        <div className="chat-project-line">
          <span className="status-dot" /> PROJECT CONTEXT ACTIVE{" "}
          <span>{workspace.status.current_stage}</span>
        </div>
        {onChange && (
          <ApprovedDocumentImport workspace={workspace} onChange={onChange} />
        )}
        {workspace.session.messages.length === 0 &&
        workspace.onboarding &&
        !workspace.onboarding.complete ? null : workspace.session.messages
            .length === 0 ? (
          <div className="chat-intro">
            <div className="assistant-mark">
              <Layers3 size={28} />
            </div>
            <p className="eyebrow">YOUR SAP DEVELOPMENT PARTNER</p>
            <h1>Let’s move your project forward.</h1>
            <p>
              {workspace.state.requirement
                ? "Your requirement is captured. Generate the next artifact, or add more context."
                : "Share your change request to begin. I’ll help you turn it into a clear plan."}
            </p>
            <div className="starter-actions">
              <button
                onClick={() =>
                  onAction({
                    action: "generate",
                    artifact_type:
                      workspace.state.expected_next_artifact || "BRD",
                    message:
                      "Generate " + workspace.state.expected_next_artifact,
                  })
                }
                disabled={busy || closed}
              >
                <FileText size={15} /> Generate{" "}
                {workspace.state.expected_next_artifact}
              </button>
              <button disabled={closed} onClick={onAttach}>
                <Paperclip size={15} /> Add project files
              </button>
            </div>
          </div>
        ) : (
          <div className="messages">
            {workspace.session.messages.map((m, i) => {
              const match =
                m.role === "assistant"
                  ? m.content.match(
                      /^(BRD|FRD|USER_STORIES|TDD|ABAP|SIT|UAT|AUDIT_REPORT) v([\d.]+):/,
                    )
                  : null;
              const approved =
                !!match &&
                workspace.state.artifact_registry.some(
                  (a) =>
                    a.artifact_id === match[1] &&
                    a.version === match[2] &&
                    a.approval_status === "approved",
                );
              return (
                <div className={"message " + m.role} key={i}>
                  <div className="message-avatar">
                    {m.role === "user" ? "L" : <Layers3 size={15} />}
                  </div>
                  <div className="message-body">
                    <p className="message-author">
                      {m.role === "user" ? "You" : "CoWork"}
                      <span>
                        {m.role === "assistant"
                          ? m.origin === "model"
                            ? `${m.provider} · ${m.model}`
                            : "Workflow"
                          : ""}
                      </span>
                    </p>
                    <ReactMarkdown>{m.content}</ReactMarkdown>
                    {match && (
                      <div className="artifact-message-actions">
                        <button onClick={() => onOpen(match[1], match[2])}>
                          <FileText size={13} /> Open {match[1]} v{match[2]}
                        </button>
                        <button
                          disabled={busy || closed || approved}
                          onClick={() =>
                            onAction({
                              action: "approve",
                              artifact_type: match[1],
                              version: match[2],
                            })
                          }
                        >
                          <Check size={13} />{" "}
                          {approved
                            ? "Approved"
                            : "Approve " + match[1] + " v" + match[2]}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {busy && !answering && (
          <div className="execution-progress" role="status">
            <Sparkles size={15} />
            <span>
              {progress
                ? progress.replaceAll("_", " ")
                : "Understanding your request"}
              {optimistic && <small> · {optimistic}</small>}
            </span>
            <span className="pulse" />
          </div>
        )}
        {pending.length > 0 && (
          <section
            className="pending-clarifications"
            aria-label="Pending clarification"
            aria-busy={answering}
          >
            <p className="eyebrow">A QUICK CLARIFICATION</p>
            <p>{pending[0].question}</p>
            <small>
              {pending.length > 1
                ? "Answer this question to continue to the next one."
                : "Your answer will resume the same task."}
            </small>
          </section>
        )}
        <div ref={end} />
      </div>
      <div className="chat-bottom">
        {workspace.session.compaction_notice && (
          <p className="compaction-notice" role="status">
            {workspace.session.compaction_notice}
          </p>
        )}
        {children}
        {answering && (
          <div
            className="answer-processing"
            id={processingId}
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <LoaderCircle
              size={16}
              className="processing-spinner"
              aria-hidden="true"
            />
            <span>Processing your answer…</span>
            {answerProgress[progress] && (
              <small>{answerProgress[progress]}</small>
            )}
          </div>
        )}
        <form
          className="composer"
          aria-busy={busy}
          onSubmit={(e) => {
            e.preventDefault();
            if (!message.trim() || busy || closed) return;
            if (active)
              setSubmittedQuestionId(pending[0]?.clarification_id || null);
            onAction({
              message,
              action: active ? "answer" : undefined,
              clarification_id: active
                ? pending[0]?.clarification_id
                : undefined,
            });
            if (!active) setMessage("");
          }}
        >
          <textarea
            disabled={closed}
            readOnly={answering}
            aria-describedby={answering ? processingId : undefined}
            aria-label={active ? "Clarification answer" : "Message CoWork"}
            placeholder={
              active
                ? "Answer the clarification to continue…"
                : "Ask CoWork, or share a change request…"
            }
            rows={2}
            value={answering ? optimistic || message : message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-toolbar">
            <button
              type="button"
              aria-label="Attach project file"
              disabled={closed}
              onClick={onAttach}
            >
              <Paperclip size={16} />
            </button>
            <span>
              {workspace.context.provider === "fake"
                ? "Deterministic demo model"
                : workspace.context.model}
            </span>
            <button
              type="submit"
              className="send-button"
              aria-label={
                answering
                  ? "Processing answer"
                  : busy
                    ? "Processing request"
                    : "Send message"
              }
              aria-busy={busy}
              disabled={busy || closed || !message.trim()}
            >
              {busy ? (
                <LoaderCircle
                  size={18}
                  className="processing-spinner"
                  aria-hidden="true"
                />
              ) : (
                <ArrowUp size={18} />
              )}
            </button>
          </div>
        </form>
        <p className="composer-note">
          Review generated artifacts before approving. Your project state stays
          with this workspace.
        </p>
      </div>
    </div>
  );
}
