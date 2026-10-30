import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import ProjectStatus from "./ProjectStatus";
import { workspace } from "./test/fixtures";
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
