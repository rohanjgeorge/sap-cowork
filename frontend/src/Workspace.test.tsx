import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import Workspace from "./Workspace";
import { workspace } from "./test/fixtures";
it("keeps the project and task visible and toggles right-rail navigation", async () => {
  render(
    <Workspace
      workspace={workspace()}
      onChange={vi.fn()}
      onBack={vi.fn()}
      onSettings={vi.fn()}
    />,
  );
  expect(screen.getByText("STO Automation")).toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Files" }));
  expect(screen.getByRole("tab", { name: "Files" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Collapse project rail" }),
  );
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Expand project rail" }),
  );
  expect(screen.getByRole("tablist")).toBeVisible();
});
