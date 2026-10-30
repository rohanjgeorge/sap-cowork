import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, vi, expect } from "vitest";
import ProjectHome from "./ProjectHome";
import { post, request } from "./api";
import { workspace } from "./test/fixtures";
vi.mock("./api", () => ({ post: vi.fn(), request: vi.fn() }));
it("creates a project with explicit stage and opens the returned workspace", async () => {
  vi.mocked(request).mockResolvedValue([]);
  vi.mocked(post).mockResolvedValue(workspace());
  const open = vi.fn();
  render(
    <ProjectHome onOpen={open} onSettings={() => {}} onLogout={() => {}} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "New project" }));
  await userEvent.type(screen.getByLabelText("Project name"), "STO Automation");
  await userEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(post).toHaveBeenCalledWith("/projects", {
    project_name: "STO Automation",
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
