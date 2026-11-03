import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("FINAL GATE: STO CR → BRD → FRD clarification → TDD → replaceable ABAP", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("button", {
      name: /Start from scratch with the client requirement/,
    })
    .click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("STO Automation Final Gate");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  const cr = fs.readFileSync(
    path.resolve("../test_fixtures/sto_cr.txt"),
    "utf-8",
  );
  await page.getByLabel("Message CoWork").fill(cr);
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("Requirement captured. Generate the BRD when ready."),
  ).toBeVisible();
  await expect(page.getByTestId("stage-Planning")).toHaveAttribute(
    "data-status",
    "amber",
  );
  async function chat(message: string) {
    await page.getByLabel("Message CoWork").fill(message);
    await page.getByRole("button", { name: "Send message" }).click();
  }
  await chat("Generate BRD");
  await expect(
    page.getByRole("button", { name: "Open BRD v1", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("stage-Planning")).toHaveAttribute(
    "data-status",
    "amber",
  );
  await page.getByRole("button", { name: "Open BRD v1", exact: true }).click();
  await expect(
    page.locator(".document-panel").getByText("draft", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Business Requirements Document (BRD)",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Mark pending offline approval" })
    .click();
  await expect(
    page
      .locator(".document-panel")
      .getByText("pending approval", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Approve artifact", exact: true })
    .click();
  await expect(page.getByTestId("stage-Planning")).toHaveAttribute(
    "data-status",
    "green",
  );
  await expect(page.getByTestId("stage-Analysis")).toContainText("Next");
  await page.getByRole("button", { name: "Back to chat", exact: true }).click();
  await chat("Generate FRD");
  await expect(page.getByLabel("Pending clarification")).toBeVisible();
  await expect(page.getByLabel("Clarification answer")).toBeVisible();
  // Inspect the actual shared backend, not component mocks.
  const projects = await (await page.request.get("/api/projects")).json();
  const project = projects.find(
    (p: { project_name: string }) =>
      p.project_name === "STO Automation Final Gate",
  );
  const id = project.project_id;
  const paused = await (
    await page.request.get(`/api/projects/${id}/state`)
  ).json();
  expect(paused.task_status).toBe("awaiting_input");
  const context = await (
    await page.request.get(`/api/projects/${id}/context`)
  ).json();
  expect(context.active_domains).toContain("BUSINESS");
  expect(context.active_domains).toContain("SDLC");
  expect(context.planning.plan_ref).toBeTruthy();
  const contextReport = await (
    await page.request.get(
      `/api/projects/${id}/context/plans/${context.planning.plan_ref}`,
    )
  ).json();
  expect(contextReport.plan.profile_version).toBe("1.0");
  expect(contextReport.plan.outcome).toBe("awaiting_input");
  expect(
    contextReport.gap_report.some(
      (gap: { gap_type: string }) => gap.gap_type === "user_owned",
    ),
  ).toBeTruthy();
  await page
    .getByLabel("Clarification answer")
    .fill(
      "Use unrestricted stock in supplying plant 1000. Require the full STO quantity; do not create partial deliveries.",
    );
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByRole("button", { name: "Open FRD v1", exact: true }),
  ).toBeVisible();
  const resumed = await (
    await page.request.get(`/api/projects/${id}/state`)
  ).json();
  expect(resumed.active_task_id).toBe(paused.active_task_id);
  expect(resumed.task_status).toBe("awaiting_approval");
  await page.getByRole("button", { name: "Open FRD v1", exact: true }).click();
  await page
    .getByRole("button", { name: "Approve artifact", exact: true })
    .click();
  await expect(page.getByTestId("stage-Analysis")).toHaveAttribute(
    "data-status",
    "amber",
  );
  await page.getByRole("button", { name: "Back to chat", exact: true }).click();
  await chat("Generate User Stories");
  await page
    .getByRole("button", { name: "Open USER_STORIES v1", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Approve artifact", exact: true })
    .click();
  await expect(page.getByTestId("stage-Analysis")).toHaveAttribute(
    "data-status",
    "green",
  );
  await expect(page.getByTestId("stage-Design")).toContainText("Next");
  await page.getByRole("button", { name: "Back to chat", exact: true }).click();
  await chat("Generate TDD");
  await expect(
    page.getByRole("button", { name: "Open TDD v1", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open TDD v1", exact: true }).click();
  await page
    .getByRole("button", { name: "Approve artifact", exact: true })
    .click();
  await expect(page.getByTestId("stage-Design")).toHaveAttribute(
    "data-status",
    "green",
  );
  await expect(page.getByTestId("stage-Development")).toContainText("Next");
  await page.getByRole("button", { name: "Back to chat", exact: true }).click();
  await chat("Generate ABAP");
  await expect(
    page.getByRole("button", { name: "Open ABAP v1", exact: true }),
  ).toBeVisible();
  const abap = await (
    await page.request.get(`/api/projects/${id}/artifacts/ABAP?version=1`)
  ).json();
  expect(abap.template_version).toBe("abap-stub-1.0");
  expect(abap.content).toContain("REPORT zcowork_sto_demo");
  expect(abap.sources).toContain("artifact:TDD:v1");
  const final = await (
    await page.request.get(`/api/projects/${id}/status`)
  ).json();
  expect(
    final.stages.slice(0, 3).map((s: { color: string }) => s.color),
  ).toEqual(["green", "green", "green"]);
  expect(errors).toEqual([]);
  await expect(page.getByTestId("stage-Development")).toHaveAttribute(
    "data-status",
    "amber",
  );
  await page
    .getByRole("button", { name: "Confirm code is satisfactory" })
    .click();
  for (const kind of ["SIT", "UAT"]) {
    await chat("Generate " + kind);
    await page
      .getByRole("button", { name: `Open ${kind} v1`, exact: true })
      .click();
    await page
      .getByRole("button", { name: "Approve artifact", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Back to chat", exact: true })
      .click();
  }
  await page
    .getByRole("button", { name: "Confirm all applicable tests passed" })
    .click();
  await expect(
    page.getByRole("button", { name: "Open AUDIT_REPORT v1", exact: true }),
  ).toBeVisible();
  const confirmed = await (
    await page.request.get(`/api/projects/${id}/state`)
  ).json();
  expect(confirmed.current_approved_stage).toBe("Testing");
  expect(confirmed.follow_ups.audit_report).toBe("completed");
  await page.getByLabel("Project actions").click();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Close project", exact: true })
    .click();
  await expect(page.getByLabel("Message CoWork")).toBeDisabled();
  const closed = await (
    await page.request.get(`/api/projects/${id}/state`)
  ).json();
  expect(closed.project_status).toBe("completed");
  await page.screenshot({
    path: "test-results/sto-final-workspace.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "All projects", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /STO Automation/ }),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: /^Completed/ }).click();
  await page.getByRole("button", { name: /STO Automation/ }).click();
  await expect(page.getByLabel("Message CoWork")).toBeDisabled();
});
