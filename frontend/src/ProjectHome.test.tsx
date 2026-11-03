import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, vi, expect } from "vitest";
import ProjectHome from "./ProjectHome";
import { post, request } from "./api";
import { workspace } from "./test/fixtures";
vi.mock("./api", () => ({ post: vi.fn(), request: vi.fn() }));
it("groups projects by lifecycle and searches and opens completed projects", async () => {
  const w = workspace();
  vi.mocked(request)
    .mockResolvedValueOnce([
      { ...w.project, project_name: "Legacy project", status: w.status },
      {
        ...w.project,
        project_id: "active",
        project_name: "Active project",
        status: { ...w.status, project_status: "active" },
      },
      {
        ...w.project,
        project_id: "incomplete",
        project_name: "Unfinished project",
        status: { ...w.status, project_status: "incomplete" },
      },
      {
        ...w.project,
        project_id: "completed",
        project_name: "Delivered project",
        status: {
          ...w.status,
          project_status: "completed",
          current_draft_stage: "Testing",
        },
      },
    ])
    .mockResolvedValueOnce(w);
  const open = vi.fn();
  render(<ProjectHome onOpen={open} onSettings={vi.fn()} onLogout={vi.fn()} />);
  expect(
    await screen.findByRole("button", { name: /Legacy project/ }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: /Active project/ })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Unfinished project/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Delivered project/ }),
  ).not.toBeInTheDocument();
  const active = screen.getByRole("tab", { name: "Active 2" });
  expect(active).toHaveAttribute("aria-selected", "true");
  active.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Completed 2" })).toHaveFocus();
  expect(
    screen.getByRole("button", { name: /Unfinished project/ }),
  ).toHaveTextContent("Closed incomplete");
  const completed = screen.getByRole("button", { name: /Delivered project/ });
  expect(completed).toHaveTextContent("SDLC: Testing");
  expect(completed.querySelector("time")).toHaveAttribute(
    "datetime",
    w.project.updated_at,
  );
  expect(
    screen.queryByRole("button", { name: /Active project/ }),
  ).not.toBeInTheDocument();
  await userEvent.type(
    screen.getByRole("textbox", { name: "Search projects" }),
    "unmatched",
  );
  expect(screen.getByRole("tabpanel")).toHaveTextContent(
    "No projects match your search in this folder.",
  );
  await userEvent.clear(
    screen.getByRole("textbox", { name: "Search projects" }),
  );
  await userEvent.click(
    within(screen.getByRole("tabpanel")).getByRole("button", {
      name: /Delivered project/,
    }),
  );
  expect(request).toHaveBeenLastCalledWith("/projects/completed");
  expect(open).toHaveBeenCalledWith(w);
});

it("shows folder-specific empty states and supports keyboard tab navigation", async () => {
  vi.mocked(request).mockResolvedValue([]);
  render(
    <ProjectHome onOpen={vi.fn()} onSettings={vi.fn()} onLogout={vi.fn()} />,
  );
  const active = screen.getByRole("tab", { name: "Active 0" });
  active.focus();
  await userEvent.keyboard("{End}");
  expect(screen.getByRole("tabpanel")).toHaveTextContent(
    "No completed projects yet.",
  );
  await userEvent.keyboard("{Home}");
  expect(active).toHaveFocus();
  expect(screen.getByRole("tabpanel")).toHaveTextContent(
    "No active projects. Create a project to begin.",
  );
  await userEvent.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { name: "Completed 0" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});
it("creates a project with explicit stage and opens the returned workspace", async () => {
  vi.mocked(request).mockResolvedValue([]);
  vi.mocked(post).mockResolvedValue(workspace());
  const open = vi.fn();
  render(
    <ProjectHome onOpen={open} onSettings={() => {}} onLogout={() => {}} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "New project" }));
  await userEvent.click(
    screen.getByRole("button", {
      name: /Start from scratch with the client requirement/,
    }),
  );
  await userEvent.type(screen.getByLabelText("Project name"), "STO Automation");
  await userEvent.type(screen.getByLabelText("Client name"), "Acme Industries");
  expect(screen.getByLabelText("Current SDLC stage")).toBeDisabled();
  expect(screen.getByLabelText("Current SDLC stage")).toHaveValue("Planning");
  await userEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(post).toHaveBeenCalledWith("/projects", {
    project_name: "STO Automation",
    client_name: "Acme Industries",
    stage: "Planning",
    requirement: "",
  });
  expect(open).toHaveBeenCalled();
});
it("reopens an existing project from backend metadata", async () => {
  const w = workspace();
  vi.mocked(request)
    .mockResolvedValueOnce([{ ...w.project, status: w.status }])
    .mockResolvedValueOnce(w);
  const open = vi.fn();
  render(
    <ProjectHome onOpen={open} onSettings={() => {}} onLogout={() => {}} />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: /STO Automation/ }),
  );
  expect(request).toHaveBeenCalledWith("/projects/p");
  expect(open).toHaveBeenCalledWith(w);
});
it("offers both start tiles and creates a checklist-based import plan", async () => {
  vi.mocked(request).mockResolvedValue([]);
  vi.mocked(post).mockResolvedValue(workspace());
  render(
    <ProjectHome onOpen={vi.fn()} onSettings={vi.fn()} onLogout={vi.fn()} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "New project" }));
  expect(
    screen.getByRole("button", {
      name: /Start from scratch with the client requirement/,
    }),
  ).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", {
      name: /I have some requirements already approved/,
    }),
  );
  await userEvent.type(
    screen.getByLabelText("Project name"),
    "Imported project",
  );
  await userEvent.type(screen.getByLabelText("Client name"), "Approved Client");
  for (const stage of [
    "Planning",
    "Analysis",
    "Design",
    "Development",
    "Testing",
  ]) {
    expect(screen.getByRole("heading", { name: stage })).toBeVisible();
  }
  expect(screen.getByRole("button", { name: "Create project" })).toBeDisabled();
  for (const group of screen.getAllByRole("radiogroup")) {
    expect(within(group).getByRole("radio", { name: "Draft" })).toBeChecked();
    expect(
      within(group).getByRole("radio", { name: "Approved" }),
    ).toBeDisabled();
  }
  expect(
    screen.queryByRole("checkbox", {
      name: /I confirm the selected documents/,
    }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: "BRD" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "FRD" }));
  expect(screen.getByRole("button", { name: "Create project" })).toBeEnabled();
  await userEvent.click(
    within(
      screen.getByRole("radiogroup", { name: "FRD document status" }),
    ).getByRole("radio", { name: "Approved" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(post).toHaveBeenCalledWith(
    "/projects",
    expect.objectContaining({
      import_artifacts: ["BRD", "FRD"],
      import_artifact_statuses: { BRD: "draft", FRD: "approved" },
      client_name: "Approved Client",
    }),
  );
});

it("returns to start options without losing names and locks scratch to Planning after switching paths", async () => {
  vi.mocked(request).mockResolvedValue([]);
  vi.mocked(post).mockResolvedValue(workspace());
  render(
    <ProjectHome onOpen={vi.fn()} onSettings={vi.fn()} onLogout={vi.fn()} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "New project" }));
  await userEvent.click(
    screen.getByRole("button", {
      name: /I have some requirements already approved/,
    }),
  );
  await userEvent.type(
    screen.getByLabelText("Project name"),
    "Retained project",
  );
  await userEvent.type(screen.getByLabelText("Client name"), "Retained client");
  expect(screen.getByLabelText("Current SDLC stage")).toBeEnabled();
  await userEvent.selectOptions(
    screen.getByLabelText("Current SDLC stage"),
    "unknown",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Back to start options" }),
  );
  expect(
    screen.getByRole("heading", { name: "How would you like to start?" }),
  ).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: /Start from scratch/ }),
  );
  expect(screen.getByLabelText("Project name")).toHaveValue("Retained project");
  expect(screen.getByLabelText("Client name")).toHaveValue("Retained client");
  expect(screen.getByLabelText("Current SDLC stage")).toBeDisabled();
  expect(screen.getByLabelText("Current SDLC stage")).toHaveValue("Planning");
  expect(
    screen.queryByLabelText("Latest available artifact"),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Back to start options" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: /Start from scratch/ }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(post).toHaveBeenLastCalledWith("/projects", {
    project_name: "Retained project",
    client_name: "Retained client",
    stage: "Planning",
    requirement: "",
  });
});

it("shows the client name on compact project cards", async () => {
  const w = workspace();
  vi.mocked(request).mockResolvedValue([
    { ...w.project, client_name: "Acme Industries", status: w.status },
  ]);
  render(
    <ProjectHome onOpen={vi.fn()} onSettings={vi.fn()} onLogout={vi.fn()} />,
  );
  expect(
    await screen.findByRole("button", { name: /STO Automation/ }),
  ).toHaveTextContent("Client: Acme Industries");
});
