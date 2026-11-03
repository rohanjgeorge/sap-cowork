import { test, expect } from "@playwright/test";

test("ordinary chat invokes the selected demo model instead of repeating workflow guidance", async ({
  page,
}) => {
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
    .fill("Conversational routing");
  await page.getByLabel("Client name", { exact: true }).fill("Demo client");
  await expect(page.getByLabel("Current SDLC stage")).toBeDisabled();
  await expect(page.getByLabel("Current SDLC stage")).toHaveValue("Planning");
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
  requirement = "Automate STO delivery creation and failure reporting",
) {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("button", {
      name: /Start from scratch with the client requirement/,
    })
    .click();
  await page.getByLabel("Project name", { exact: true }).fill(name);
  await page.getByLabel(/Requirement or change request/).fill(requirement);
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  if (stage !== "Planning") {
    await page.getByLabel("Work on", { exact: true }).selectOption(stage);
    await expect(page.getByLabel("Work on", { exact: true })).toHaveValue(
      stage,
    );
    await expect(page.getByLabel("Work on", { exact: true })).toBeEnabled();
  }
}

test("clarification answers show visible processing before the server replies", async ({
  page,
}) => {
  await create(page, "Clarification processing", "Planning", "");
  await page
    .getByRole("button", { name: "Generate BRD", exact: true })
    .first()
    .click();
  await expect(page.getByLabel("Clarification answer")).toBeVisible();
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/chat/stream", async (route) => {
    if (route.request().postDataJSON().action === "answer") await held;
    await route.continue();
  });
  const answer = "Automate delivery creation with failure reporting.";
  await page.getByLabel("Clarification answer").fill(answer);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  try {
    await expect(page.getByRole("status")).toContainText(
      "Processing your answer…",
    );
    await expect(
      page.getByRole("button", { name: "Processing answer" }),
    ).toBeDisabled();
    await expect(page.getByLabel("Clarification answer")).toHaveValue(answer);
    await expect(page.getByLabel("Clarification answer")).toHaveAttribute(
      "readonly",
      "",
    );
    await page.screenshot({
      path: "test-results/clarification-processing.png",
      fullPage: true,
    });
  } finally {
    release();
  }
  await expect(
    page.getByRole("button", { name: "Open BRD v1", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Message CoWork", { exact: true })).toHaveValue(
    "",
  );
  await expect(
    page.getByRole("button", { name: "Processing answer" }),
  ).toHaveCount(0);
});

test("Work on requests model guidance without generating artifacts or advancing Current Stage", async ({
  page,
}) => {
  await create(page, "Stage guidance project");
  await page.getByLabel("Work on", { exact: true }).selectOption("Analysis");
  await expect(
    page.locator(".messages .message.assistant").last(),
  ).toContainText("You're now working on Analysis.");
  await expect(
    page.locator(".messages .message.assistant").last(),
  ).toContainText("fake · deterministic-v1");
  await expect(
    page.locator(".messages").getByText("Generate FRD", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Current Stage: Planning", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".project-workflow-summary")).toContainText(
    "No active task",
  );
  await expect(page.locator(".project-workflow-summary dd").nth(1)).toHaveText(
    "FRD",
  );
  await page.getByLabel("Work on", { exact: true }).selectOption("Development");
  await expect(
    page.locator(".messages .message.assistant").last(),
  ).toContainText("You're now working on Development.");
  const projects = await (await page.request.get("/api/projects")).json();
  const id = projects.find(
    (project: { project_name: string }) =>
      project.project_name === "Stage guidance project",
  ).project_id;
  const w = await (await page.request.get(`/api/projects/${id}`)).json();
  expect(w.state.current_draft_stage).toBe("Development");
  expect(w.state.current_approved_stage).toBe("Planning");
  expect(w.state.artifact_registry).toHaveLength(0);
  await expect(page.locator(".project-workflow-summary dd").nth(1)).toHaveText(
    w.state.expected_next_artifact,
  );
  await expect(page.locator(".project-workflow-summary dd").nth(2)).toHaveText(
    w.state.recommended_next_action,
  );
  await expect(page.getByTestId("stage-Development")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("context categories expand and status record lists return to the lifecycle", async ({
  page,
}) => {
  await create(page, "Project record navigation");
  await page.getByLabel("Message CoWork", { exact: true }).fill("Hi");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.locator(".messages .message.assistant").last(),
  ).toContainText("Demo mode");
  await expect(page.locator(".context-domains")).toBeHidden();
  const context = page.getByRole("button", { name: /^Context [\d.]+%$/ });
  await context.click();
  await expect(context).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".context-domains")).toContainText("Business");
  await context.click();
  await expect(page.locator(".context-domains")).toBeHidden();
  const projects = await (await page.request.get("/api/projects")).json();
  const id = projects.find(
    (project: { project_name: string }) =>
      project.project_name === "Project record navigation",
  ).project_id;
  const state = await (
    await page.request.get(`/api/projects/${id}/state`)
  ).json();
  const recorded = await page.request.post(
    `/api/projects/${id}/state/operations`,
    {
      data: {
        operation: "record_decision",
        payload: { description: "Use unrestricted stock" },
        expected_revision: state.state_revision,
        request_id: "record-navigation-decision",
      },
    },
  );
  expect(recorded.ok()).toBe(true);
  await page
    .getByRole("button", { name: "Refresh project", exact: true })
    .click();
  await page.getByRole("button", { name: "Decisions 1", exact: true }).click();
  await expect(page.getByRole("list", { name: "Decisions" })).toContainText(
    "Use unrestricted stock",
  );
  await page
    .getByRole("button", { name: "Back to project status", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Project lifecycle" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Flags 0", exact: true }).click();
  await expect(
    page.getByText("No flags recorded.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Back to project status", exact: true })
    .click();
});

for (const width of [1440, 390]) {
  test(`closed incomplete projects move to Completed and return to Active when reopened (${width}px)`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const name = `Closed project ${width}`;
    await create(page, name);
    await page.getByLabel("Project actions").click();
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Close project", exact: true })
      .click();
    await expect(page.getByLabel("Message CoWork")).toBeDisabled();
    await page
      .getByRole("button", { name: "All projects", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: new RegExp(name) }),
    ).toHaveCount(0);
    await page.getByRole("tab", { name: /^Completed/ }).click();
    await expect(
      page.getByRole("button", { name: new RegExp(name) }),
    ).toContainText("Closed incomplete");
    await page.reload();
    await page.getByRole("tab", { name: /^Completed/ }).click();
    await page.getByRole("button", { name: new RegExp(name) }).click();
    await expect(page.getByLabel("Message CoWork")).toBeDisabled();
    await page.getByLabel("Project actions").click();
    await page
      .getByRole("button", { name: "Reopen project", exact: true })
      .click();
    await expect(page.getByLabel("Message CoWork")).toBeEnabled();
    await page
      .getByRole("button", { name: "All projects", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: new RegExp(name) }),
    ).toBeVisible();
    await page.getByRole("tab", { name: /^Completed/ }).click();
    await expect(
      page.getByRole("button", { name: new RegExp(name) }),
    ).toHaveCount(0);
  });
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
    .getByRole("button", { name: "Approve artifact", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Request changes", exact: true })
    .click();
  await page
    .getByLabel("Revision feedback")
    .fill("Include the failure report requirement");
  await page.getByRole("button", { name: "Submit change request" }).click();
  await expect(
    page.locator(".document-panel").getByText("draft", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to chat", exact: true }).click();
  await page.getByLabel("Message CoWork").fill("Generate BRD");
  await page.getByRole("button", { name: "Send message" }).click();
  await page
    .getByRole("button", { name: "Open BRD v2", exact: true })
    .last()
    .click();
  await expect(
    page.getByLabel("Artifact version").locator("option"),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "Compare with previous" }).click();
  await expect(page.getByLabel("Version comparison")).toBeVisible();
  await page.getByLabel("Artifact version").selectOption("1");
  await expect(
    page.locator(".document-panel").getByText("approved", { exact: true }),
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
    .getByRole("button", {
      name: /Start from scratch with the client requirement/,
    })
    .click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Mobile design project");
  await page.getByLabel("Client name", { exact: true }).fill("Mobile client");
  await expect(page.getByLabel("Current SDLC stage")).toBeDisabled();
  await expect(page.getByLabel("Current SDLC stage")).toHaveValue("Planning");
  await page.getByRole("button", { name: "Back to start options" }).click();
  await page
    .getByRole("button", { name: /I have some requirements already approved/ })
    .click();
  await expect(page.getByLabel("Project name", { exact: true })).toHaveValue(
    "Mobile design project",
  );
  await expect(page.getByLabel("Client name", { exact: true })).toHaveValue(
    "Mobile client",
  );
  await page.getByLabel("Current SDLC stage").selectOption("unknown");
  await page.getByLabel("Latest available artifact").selectOption("FRD");
  await page.getByLabel("Confirm Design as my starting stage").check();
  await page.getByRole("checkbox", { name: "BRD", exact: true }).check();
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.getByRole("button", { name: "Collapse project rail" }).click();
  await expect(page.getByLabel("Message CoWork")).toBeVisible();
  expect(
    await page.evaluate(
      () => window.document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/mobile-workspace.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "All projects", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Mobile design project/ }),
  ).toContainText("Client: Mobile client");
});

test("mixed draft and approved onboarding preserves each status and survives reopening", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: /Start from scratch with the client requirement/,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /I have some requirements already approved/ })
    .click();
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Approved-document import");
  await page.getByRole("checkbox", { name: "BRD", exact: true }).check();
  await page.getByRole("checkbox", { name: "FRD", exact: true }).check();
  await expect(
    page
      .getByRole("radiogroup", { name: "BRD document status" })
      .getByRole("radio", { name: "Draft" }),
  ).toBeChecked();
  await page
    .getByRole("radiogroup", { name: "FRD document status" })
    .getByRole("radio", { name: "Approved" })
    .check();
  await expect(
    page.getByRole("checkbox", { name: /I confirm the selected documents/ }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Upload draft BRD" }),
  ).toBeVisible();
  await page.getByLabel("Draft BRD document").setInputFiles({
    name: "brd.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Draft BRD\nAutomate STO delivery creation"),
  });
  await page
    .getByRole("button", { name: "Import draft BRD", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Upload approved FRD" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "All projects" }).click();
  await page.getByRole("button", { name: /Approved-document import/ }).click();
  await expect(
    page.getByRole("heading", { name: "Upload approved FRD" }),
  ).toBeVisible();
  await page.getByLabel("Approved FRD document").setInputFiles({
    name: "frd.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "# Approved FRD\nCreate STO deliveries with error reporting",
    ),
  });
  await page
    .getByRole("button", { name: "Import approved FRD", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your documents are ready" }),
  ).toBeVisible();
  const projects = await (await page.request.get("/api/projects")).json();
  const id = projects.find(
    (p: { project_name: string }) =>
      p.project_name === "Approved-document import",
  ).project_id;
  const w = await (await page.request.get(`/api/projects/${id}`)).json();
  expect(w.onboarding.complete).toBe(true);
  expect(w.state.artifacts.BRD.status).toBe("draft");
  expect(w.state.artifacts.FRD.status).toBe("approved");
  expect(w.state.artifact_registry).toHaveLength(2);
  expect(w.project.import_artifact_statuses).toEqual({
    BRD: "draft",
    FRD: "approved",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "All projects" }).click();
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: /I have some requirements already approved/,
    }),
  ).toBeInViewport();
});

test("BRD viewer presents formatted tables and keeps wide tables inside the mobile page", async ({
  page,
}) => {
  await create(page, "Formatted document viewer");
  await page
    .getByRole("button", { name: "Generate BRD", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Open BRD v1", exact: true }),
  ).toBeVisible();
  const projects = await (await page.request.get("/api/projects")).json();
  const id = projects.find(
    (p: { project_name: string }) =>
      p.project_name === "Formatted document viewer",
  ).project_id;
  const w = await (await page.request.get(`/api/projects/${id}`)).json();
  const artifact = await (
    await page.request.get(`/api/projects/${id}/artifacts/BRD?version=1`)
  ).json();
  const content = artifact.content.replace(
    "## Document Information",
    "## Document Information\n\n| Field | Value |\n|---|---|\n| Document Title | STO Delivery Automation |\n| Client Organization | Example client [SRC-002] |\n",
  );
  const edit = await page.request.put(`/api/projects/${id}/artifacts/BRD`, {
    data: {
      content,
      expected_revision: w.state.state_revision,
      request_id: "document-formatting-edit",
    },
  });
  expect(edit.ok()).toBe(true);
  const saved = (await edit.json()).artifact;
  await page.getByRole("button", { name: "Open BRD v1", exact: true }).click();
  const document = page.locator(".document-content");
  await expect(
    document.getByRole("heading", {
      name: "Document Information",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    document.getByRole("columnheader", { name: "Field", exact: true }),
  ).toBeVisible();
  await expect(
    document.getByRole("cell", {
      name: "STO Delivery Automation",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    document.getByRole("columnheader", { name: "Field", exact: true }),
  ).toHaveCSS("background-color", "rgb(232, 236, 240)");
  await document.screenshot({
    path: "test-results/formatted-document-desktop.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  if (
    await page
      .getByRole("button", { name: "Collapse project rail" })
      .isVisible()
  )
    await page.getByRole("button", { name: "Collapse project rail" }).click();
  await expect(
    document.getByRole("cell", {
      name: "STO Delivery Automation",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => window.document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    await document
      .locator(".document-table-scroll")
      .first()
      .evaluate((el) => el.scrollWidth > el.clientWidth),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/formatted-document-mobile.png",
    fullPage: true,
  });
  const after = await (
    await page.request.get(`/api/projects/${id}/artifacts/BRD?version=1`)
  ).json();
  expect(after.content).toBe(saved.content);
});
