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
it("renders a clarification and submits an answer for the waiting task", async () => {
  const w = workspace();
  w.state.task_status = "awaiting_input";
  w.status.open_clarifications = [
    {
      clarification_id: "q",
      question: "Which stock rule?",
      status: "open",
      response: null,
    },
  ];
  const action = vi.fn();
  render(
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
});
