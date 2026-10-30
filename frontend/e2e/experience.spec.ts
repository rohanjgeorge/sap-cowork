import { test, expect } from "@playwright/test";

test("ordinary chat invokes the selected demo model instead of repeating workflow guidance", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Conversational routing");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.getByLabel("Message CoWork").fill("hi");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText(/Demo mode is selected; no live model was called/),
  ).toBeVisible();
  await expect(
    page.getByText("fake · deterministic-v1", { exact: true }),
  ).toBeVisible();
  const projects = await (await page.request.get("/api/projects")).json();
  const id = projects.find(
    (p: { project_name: string }) =>
      p.project_name === "Conversational routing",
  ).project_id;
  const state = await (
    await page.request.get(`/api/projects/${id}/state`)
  ).json();
  expect(state.requirement).toBe("");
  expect(state.artifact_registry).toEqual([]);
  await page
    .getByLabel("Message CoWork")
    .fill("Requirement: Automate deliveries");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Workflow", { exact: true })).toBeVisible();
});

async function create(
  page: import("@playwright/test").Page,
  name: string,
  stage = "Planning",
) {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page.getByLabel("Project name", { exact: true }).fill(name);
  await page.getByLabel("Current SDLC stage").selectOption(stage);
  await page
    .getByLabel(/Requirement or change request/)
    .fill("Automate STO delivery creation and failure reporting");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
}

test("files, revision history, comparison, compaction and project reopen", async ({
  page,
}) => {
  await create(page, "Files and revision journey");
  await page
    .getByRole("button", { name: "Generate BRD", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Open BRD v1", exact: true }).click();
  await page
    .getByRole("button", { name: "Request changes", exact: true })
    .click();
  await page
    .getByLabel("Revision feedback")
    .fill("Include the failure report requirement");
  await page.getByRole("button", { name: "Submit change request" }).click();
  await expect(
    page.locator(".document-panel").getByText("rejected", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to chat", exact: true }).click();
  await page.getByLabel("Message CoWork").fill("Generate BRD");
  await page.getByRole("button", { name: "Send message" }).click();
  await page.getByRole("button", { name: "Open BRD v2", exact: true }).click();
  await expect(
    page.getByLabel("Artifact version").locator("option"),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "Compare with previous" }).click();
  await expect(page.getByLabel("Version comparison")).toBeVisible();
  await page.getByLabel("Artifact version").selectOption("1");
  await expect(
    page.locator(".document-panel").getByText("rejected", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Files", exact: true }).click();
  await page.getByRole("button", { name: "Upload file" }).click();
  await page.getByLabel("Choose file").setInputFiles({
    name: "sap_context.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("Availability definition: use unrestricted stock"),
  });
  await page.getByLabel("Context domain").selectOption("SAP");
  await page.getByRole("button", { name: "Add to project" }).click();
  await expect(
    page.getByRole("link", { name: "sap_context.md" }),
  ).toBeVisible();
  const projects = await (await page.request.get("/api/projects")).json();
  const id = projects.find(
    (p: { project_name: string }) =>
      p.project_name === "Files and revision journey",
  ).project_id;
  const before = await (await page.request.get(`/api/projects/${id}`)).json();
  await page.getByRole("button", { name: "Compact", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/projects/${id}/context`)).json())
          .compactions,
    )
    .toBe(1);
  const after = await (await page.request.get(`/api/projects/${id}`)).json();
  expect(after.state).toEqual(before.state);
  expect(after.memory).toEqual(before.memory);
  expect(after.assets).toEqual(before.assets);
  await page.getByRole("button", { name: "All projects" }).click();
  await page
    .getByRole("button", { name: /Files and revision journey/ })
    .click();
  await expect(
    page.getByText("Files and revision journey", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/reopened-workspace.png",
    fullPage: true,
  });
});

test("draft TDD permits ABAP with a visible non-blocking PM error", async ({
  page,
}) => {
  await create(page, "Draft TDD ABAP journey", "Design");
  await page
    .getByRole("button", { name: "Generate TDD", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Open TDD v1", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Message CoWork").fill("Generate ABAP");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByRole("button", { name: "Open ABAP v1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Error · Non-blocking", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "TDD is not approved; generation can proceed using available context.",
    ),
  ).toBeVisible();
});

test("mobile workspace, provider settings and assisted stage confirmation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("button", { name: "Provider settings" }).click();
  await page.getByRole("button", { name: "Test saved connection" }).click();
  await expect(
    page.getByText("fake: connected", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Mobile design project");
  await page.getByLabel("Current SDLC stage").selectOption("unknown");
  await page.getByLabel("Latest available artifact").selectOption("FRD");
  await page.getByLabel("Confirm Design as my starting stage").check();
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.getByRole("button", { name: "Collapse project rail" }).click();
  await expect(page.getByLabel("Message CoWork")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/mobile-workspace.png",
    fullPage: true,
  });
});
