import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import ContextBar from "./ContextBar";
import { workspace } from "./test/fixtures";
it("shows context telemetry and invokes compaction independently of project state", async () => {
  const context = {
    ...workspace().context,
    usage_percent: 80,
    band: "compact_recommended",
    active_domains: ["BUSINESS", "SAP", "SDLC"],
  };
  const compact = vi.fn();
  const { rerender } = render(
    <ContextBar context={context} onCompact={compact} busy={false} />,
  );
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "80",
  );
  expect(
    screen.getByText("Compact context before the next large task."),
  ).toBeVisible();
  const toggle = screen.getByRole("button", { name: "Context 80%" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByText("Business")).not.toBeVisible();
  expect(screen.getByText("SDLC")).not.toBeVisible();
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(
    document.getElementById(toggle.getAttribute("aria-controls")!),
  ).toBeVisible();
  expect(screen.getByText("Business")).toBeVisible();
  expect(screen.getByText("SDLC")).toBeVisible();
  await userEvent.click(toggle);
  expect(screen.getByText("Business")).not.toBeVisible();
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(screen.getByRole("button", { name: "Compact" }));
  expect(compact).toHaveBeenCalledOnce();
  rerender(
    <ContextBar
      context={{ ...context, usage_percent: 20, band: "healthy" }}
      onCompact={compact}
      busy={false}
    />,
  );
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "20",
  );
});
