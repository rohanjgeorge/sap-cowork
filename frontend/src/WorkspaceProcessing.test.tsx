import { useState } from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import Workspace from "./Workspace";
import { streamChat } from "./api";
import { workspace } from "./test/fixtures";
import type { Workspace as WorkspaceData, ChatResult } from "./types";

vi.mock("./api", () => ({ streamChat: vi.fn(), request: vi.fn() }));
beforeEach(() => vi.resetAllMocks());

const answer = "Unrestricted stock, full quantity only";
function waiting() {
  const value = workspace();
  value.state.task_status = "awaiting_input";
  value.state.active_task_id = "generation-task";
  value.status.open_clarifications = [
    {
      clarification_id: "question",
      task_id: "generation-task",
      question: "Which stock rule?",
      status: "open",
      response: null,
    },
  ];
  value.session.messages = [
    { role: "assistant", content: "Which stock rule?" },
  ];
  return value;
}
function completed(initial: WorkspaceData): ChatResult {
  return {
    message: "Answer processed.",
    workspace: {
      ...initial,
      state: { ...initial.state, task_status: "awaiting_approval" },
      status: { ...initial.status, open_clarifications: [] },
      session: {
        messages: [
          ...initial.session.messages,
          { role: "user", content: answer },
          { role: "assistant", content: "Answer processed." },
        ],
      },
    },
  };
}
function Harness({ initial }: { initial: WorkspaceData }) {
  const [value, setValue] = useState(initial);
  return (
    <Workspace
      workspace={value}
      onChange={setValue}
      onBack={vi.fn()}
      onSettings={vi.fn()}
    />
  );
}

it("shows immediate answer processing before any server progress, keeps the answer visible and clears it after success", async () => {
  const initial = waiting();
  let finish!: (result: ChatResult) => void;
  let progress!: (status: string) => void;
  vi.mocked(streamChat).mockImplementation((_id, _input, callback) => {
    progress = callback;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  render(<Harness initial={initial} />);
  await userEvent.type(screen.getByLabelText("Clarification answer"), answer);
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(screen.getByRole("status")).toHaveTextContent(
    "Processing your answer…",
  );
  const input = screen.getByLabelText("Clarification answer");
  expect(input).toHaveValue(answer);
  expect(input).toHaveAttribute("readonly");
  expect(input).toHaveAccessibleDescription("Processing your answer…");
  expect(
    screen.getByRole("button", { name: "Processing answer" }),
  ).toBeDisabled();
  await userEvent.click(input);
  await userEvent.keyboard("{Enter}");
  expect(streamChat).toHaveBeenCalledOnce();
  act(() => progress("planning_context"));
  expect(screen.getByRole("status")).toHaveTextContent(
    "Checking project context…",
  );
  await act(async () => finish(completed(initial)));
  expect(
    screen.queryByRole("button", { name: "Processing answer" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Message CoWork")).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "Send message" }),
  ).toBeInTheDocument();
});

it("retains a failed answer and retries with the original request identity", async () => {
  const initial = waiting();
  let finish!: (result: ChatResult) => void;
  vi.mocked(streamChat)
    .mockRejectedValueOnce(new Error("Connection lost"))
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  render(<Harness initial={initial} />);
  await userEvent.type(screen.getByLabelText("Clarification answer"), answer);
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection lost");
  expect(screen.getByLabelText("Clarification answer")).toHaveValue(answer);
  expect(screen.getByLabelText("Clarification answer")).not.toHaveAttribute(
    "readonly",
  );
  await userEvent.click(screen.getByRole("button", { name: "Retry request" }));
  expect(screen.getByRole("status")).toHaveTextContent(
    "Processing your answer…",
  );
  expect(vi.mocked(streamChat).mock.calls[1][1]).toEqual(
    vi.mocked(streamChat).mock.calls[0][1],
  );
  await act(async () => finish(completed(initial)));
  expect(screen.getByLabelText("Message CoWork")).toHaveValue("");
});
