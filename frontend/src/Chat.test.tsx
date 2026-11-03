import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import Chat from "./Chat";
import { workspace } from "./test/fixtures";
it("submits a chat request through its orchestrator action handler", async () => {
  const action = vi.fn();
  render(
    <Chat
      workspace={workspace()}
      onAction={action}
      onOpen={vi.fn()}
      onAttach={vi.fn()}
      busy={false}
      progress=""
      optimistic=""
    />,
  );
  await userEvent.type(screen.getByLabelText("Message CoWork"), "Generate BRD");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(action).toHaveBeenCalledWith(
    expect.objectContaining({ message: "Generate BRD" }),
  );
});

it("keeps a closed project readable while disabling mutation controls", () => {
  const w = workspace();
  w.state.project_status = "completed";
  w.session.messages = [
    { role: "assistant", content: "BRD v1: draft. Review the document." },
  ];
  render(
    <Chat
      workspace={w}
      onAction={vi.fn()}
      onOpen={vi.fn()}
      onAttach={vi.fn()}
      busy={false}
      progress=""
      optimistic=""
    />,
  );
  expect(screen.getByRole("button", { name: "Open BRD v1" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Approve BRD v1" })).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Attach project file" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Message CoWork")).toBeDisabled();
});
it("renders a clarification and submits an answer for the waiting task", async () => {
  const w = workspace();
  w.state.task_status = "awaiting_input";
  w.state.active_task_id = "current-task";
  w.status.open_clarifications = [
    {
      clarification_id: "old",
      task_id: "other-task",
      question: "Unrelated older question?",
      status: "open",
      response: null,
    },
    {
      clarification_id: "q",
      question: "Which stock rule?",
      status: "open",
      response: null,
    },
    {
      clarification_id: "q2",
      task_id: "current-task",
      question: "Which plant?",
      status: "open",
      response: null,
    },
  ];
  const action = vi.fn();
  const view = render(
    <Chat
      workspace={w}
      onAction={action}
      onOpen={vi.fn()}
      onAttach={vi.fn()}
      busy={false}
      progress=""
      optimistic=""
    />,
  );
  expect(screen.getByText("Which stock rule?")).toBeVisible();
  expect(screen.queryByText("Which plant?")).not.toBeInTheDocument();
  expect(
    screen.queryByText("Unrelated older question?"),
  ).not.toBeInTheDocument();
  await userEvent.type(
    screen.getByLabelText("Clarification answer"),
    "Unrestricted stock",
  );
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(action).toHaveBeenCalledWith({
    message: "Unrestricted stock",
    action: "answer",
    clarification_id: "q",
  });
  view.rerender(
    <Chat
      workspace={{
        ...w,
        status: {
          ...w.status,
          open_clarifications: [w.status.open_clarifications[2]],
        },
      }}
      onAction={action}
      onOpen={vi.fn()}
      onAttach={vi.fn()}
      busy={false}
      progress=""
      optimistic=""
    />,
  );
  expect(screen.queryByText("Which stock rule?")).not.toBeInTheDocument();
  expect(screen.getByText("Which plant?")).toBeVisible();
  await userEvent.type(
    screen.getByLabelText("Clarification answer"),
    "Plant 1000",
  );
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(action).toHaveBeenLastCalledWith({
    message: "Plant 1000",
    action: "answer",
    clarification_id: "q2",
  });
});

it("distinguishes actual model replies from workflow confirmations", () => {
  const w = workspace();
  w.session.messages = [
    {
      role: "assistant",
      content: "How can I help with your SAP project?",
      origin: "model",
      provider: "openai",
      model: "configured-openai-model",
    },
    { role: "assistant", content: "Requirement captured.", origin: "workflow" },
  ];
  render(
    <Chat
      workspace={w}
      onAction={vi.fn()}
      onOpen={vi.fn()}
      onAttach={vi.fn()}
      busy={false}
      progress=""
      optimistic=""
    />,
  );
  expect(screen.getByText("openai · configured-openai-model")).toBeVisible();
  expect(screen.getByText("Workflow")).toBeVisible();
});
