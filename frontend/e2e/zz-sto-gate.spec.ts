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
    page
      .locator(".document-panel")
      .getByText("pending approval", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Business Requirements Document",
      exact: true,
    }),
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
  await page.screenshot({
    path: "test-results/sto-final-workspace.png",
    fullPage: true,
  });
});
