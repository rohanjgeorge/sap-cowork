import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import ProjectStatus from "./ProjectStatus";
import { workspace } from "./test/fixtures";
it("shows saved task guidance and updates cleared values without assuming the stage default", () => {
  const w = workspace();
  w.status.current_stage = "Analysis";
  w.status.current_task = "Review functional requirements";
  w.status.recommended_next_action = "Prepare user stories";
  const view = render(
    <ProjectStatus
      status={w.status}
      expectedNextArtifact="USER_STORIES"
      onOpen={vi.fn()}
      onAction={vi.fn()}
    />,
  );
  const summary = screen.getByLabelText("Project task summary");
  expect(
    within(summary).getByText("Review functional requirements"),
  ).toBeVisible();
  expect(within(summary).getByText("USER_STORIES")).toBeVisible();
  expect(screen.getAllByText("Prepare user stories")).toHaveLength(1);
  view.rerender(
    <ProjectStatus
      status={{
        ...w.status,
        current_task: null,
        recommended_next_action: null,
      }}
      expectedNextArtifact={null}
      onOpen={vi.fn()}
      onAction={vi.fn()}
    />,
  );
  expect(within(summary).getByText("No active task")).toBeVisible();
  expect(within(summary).getByText("Not scheduled")).toBeVisible();
  expect(within(summary).getByText("Continue in chat")).toBeVisible();
});
it("opens complete record histories and returns without changing the workflow", async () => {
  const w = workspace();
  w.status.project_status = "completed";
  w.state.clarifications = [
    {
      clarification_id: "open",
      question: "Which plant?",
      status: "open",
      response: null,
    },
    {
      clarification_id: "resolved",
      question: "Who owns this?",
      status: "resolved",
      response: null,
      resolution: "Logistics",
    },
  ];
  w.state.decisions = [
    {
      decision_id: "d",
      description: "Use unrestricted stock",
      decided_by: "local",
    },
  ];
  w.state.flags = [
    {
      flag_id: "active",
      description: "Review target release",
      type: "warning",
      status: "active",
    },
    {
      flag_id: "resolved",
      description: "Owner confirmed",
      type: "exception",
      status: "resolved",
    },
  ];
  const action = vi.fn();
  render(
    <ProjectStatus
      status={w.status}
      records={w.state}
      onOpen={vi.fn()}
      onAction={action}
    />,
  );
  expect(
    screen.queryByText("Every stage, with the context to continue."),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Flags 2" })).toBeEnabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Clarifications 2" }),
  );
  expect(
    screen.getByRole("heading", { name: "Clarifications (2)" }),
  ).toHaveFocus();
  const questions = screen.getByRole("list", { name: "Clarifications" });
  expect(within(questions).getAllByRole("listitem")).toHaveLength(2);
  expect(within(questions).getByText("Answer: Logistics")).toBeVisible();
  expect(within(questions).getByText("Resolved")).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: "Back to project status" }),
  );
  expect(
    screen.getByRole("button", { name: "Clarifications 2" }),
  ).toHaveFocus();
  await userEvent.click(screen.getByRole("button", { name: "Decisions 1" }));
  expect(screen.getByRole("list", { name: "Decisions" })).toHaveTextContent(
    "Use unrestricted stock",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Back to project status" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Flags 2" }));
  expect(screen.getByRole("list", { name: "Flags" })).toHaveTextContent(
    "Owner confirmed",
  );
  expect(screen.getByText("Active")).toBeVisible();
  expect(screen.getByText("Resolved")).toBeVisible();
  expect(action).not.toHaveBeenCalled();
});

it.each(["Clarifications", "Decisions", "Flags"])(
  "opens an empty %s list with a way back",
  async (label) => {
    render(
      <ProjectStatus
        status={workspace().status}
        onOpen={vi.fn()}
        onAction={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: `${label} 0` }));
    expect(
      screen.getByText(`No ${label.toLowerCase()} recorded.`),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Back to project status" }),
    );
    expect(
      screen.getByRole("heading", { name: "Project lifecycle" }),
    ).toBeVisible();
  },
);
it("renders backend colors and opens the clicked stage documents", async () => {
  const w = workspace();
  w.status.stages[0].color = "green";
  w.status.stages[0].label = "Approved";
  w.status.stages[0].documents = [
    {
      artifact_id: "BRD",
      artifact_type: "BRD",
      version: "1",
      approval_status: "approved",
    },
  ];
  const open = vi.fn();
  render(<ProjectStatus status={w.status} onOpen={open} onAction={vi.fn()} />);
  expect(screen.getByTestId("stage-Planning")).toHaveAttribute(
    "data-status",
    "green",
  );
  expect(screen.getByTestId("stage-Analysis")).toHaveAttribute(
    "data-status",
    "grey",
  );
  await userEvent.click(
    screen.getByRole("button", { name: /BRD v1 approved/ }),
  );
  expect(open).toHaveBeenCalledWith("BRD", "1");
  await userEvent.click(screen.getByTestId("stage-Design"));
  expect(screen.getByText("Expected output: TDD")).toBeVisible();
});
it("shows approval error while keeping generation enabled", async () => {
  const w = workspace();
  w.status.current_stage = "Development";
  w.status.stages[3].color = "amber";
  w.status.stages[3].issues = [
    {
      code: "TDD_UNAPPROVED",
      message: "TDD is not approved",
      severity: "error",
      blocking: false,
      stage: "Development",
    },
  ];
  const action = vi.fn();
  render(
    <ProjectStatus status={w.status} onOpen={vi.fn()} onAction={action} />,
  );
  expect(screen.getByText("Error · Non-blocking")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Generate ABAP" }));
  expect(action).toHaveBeenCalled();
});

it("navigates the draft stage and requests explicit code acceptance", async () => {
  const w = workspace(),
    action = vi.fn();
  w.status.current_approved_stage = "Planning";
  w.status.current_draft_stage = "Development";
  w.status.current_stage = "Development";
  w.status.stages[3].expected_artifacts = ["ABAP"];
  render(
    <ProjectStatus status={w.status} onOpen={vi.fn()} onAction={action} />,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm code is satisfactory" }),
  );
  expect(action).toHaveBeenLastCalledWith({ action: "confirm_code" });
  await userEvent.click(screen.getByTestId("stage-Testing"));
  expect(action).toHaveBeenLastCalledWith({
    action: "set_stage",
    stage: "Testing",
  });
  expect(screen.getByText(/Working on: Development/)).toBeVisible();
  expect(screen.getByText(/Current Stage: Planning/)).toBeVisible();
});
