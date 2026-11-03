import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi, beforeEach } from "vitest";
import ProjectHome from "./ProjectHome";
import Workspace from "./Workspace";
import { request, post, streamChat } from "./api";
import { workspace } from "./test/fixtures";
vi.mock("./api", () => ({
  request: vi.fn(),
  post: vi.fn(),
  streamChat: vi.fn(),
}));
beforeEach(() => vi.resetAllMocks());
it("does not reopen a workspace when an operation finishes after navigating back", async () => {
  const w = workspace(),
    changed = vi.fn(),
    back = vi.fn();
  let finish!: (value: Awaited<ReturnType<typeof streamChat>>) => void;
  vi.mocked(streamChat).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(
    <Workspace
      workspace={w}
      onChange={changed}
      onBack={back}
      onSettings={vi.fn()}
    />,
  );
  expect(screen.getByText("Current Stage: Planning")).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText("Work on"), "Design");
  await userEvent.click(screen.getByRole("button", { name: "All projects" }));
  await act(async () => finish({ workspace: w, message: "Stage changed" }));
  expect(back).toHaveBeenCalledOnce();
  expect(changed).not.toHaveBeenCalled();
});
it("creates a project with optional organization, program and SAP metadata", async () => {
  vi.mocked(request).mockResolvedValue([]);
  vi.mocked(post).mockResolvedValue(workspace());
  render(
    <ProjectHome onOpen={vi.fn()} onSettings={vi.fn()} onLogout={vi.fn()} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "New project" }));
  await userEvent.click(
    screen.getByRole("button", {
      name: /Start from scratch with the client requirement/,
    }),
  );
  await userEvent.type(
    screen.getByLabelText("Project name"),
    "Metadata project",
  );
  await userEvent.click(screen.getByText("Optional project metadata"));
  await userEvent.type(screen.getByLabelText("Organization ID"), "ABC");
  await userEvent.type(screen.getByLabelText("Program ID"), "P1");
  await userEvent.type(screen.getByLabelText("SAP product"), "S/4HANA");
  await userEvent.type(screen.getByLabelText("SAP release/version"), "2023");
  await userEvent.click(screen.getByRole("button", { name: "Create project" }));
  expect(post).toHaveBeenCalledWith(
    "/projects",
    expect.objectContaining({
      organization_id: "ABC",
      program_id: "P1",
      sap_applicability: { product: "S/4HANA", release: "2023" },
    }),
  );
});
it("edits metadata using the shared revision checked endpoint", async () => {
  const w = workspace();
  vi.mocked(request).mockResolvedValue(w);
  render(
    <Workspace
      workspace={w}
      onChange={vi.fn()}
      onBack={vi.fn()}
      onSettings={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByLabelText("Project actions"));
  await userEvent.click(
    screen.getByRole("button", { name: "Project metadata" }),
  );
  await userEvent.click(screen.getByText("Optional project metadata"));
  await userEvent.type(screen.getByLabelText("SAP system"), "S4P");
  await userEvent.click(
    screen.getByRole("button", { name: "Save project metadata" }),
  );
  expect(request).toHaveBeenCalledWith(
    "/projects/p/metadata",
    expect.objectContaining({ method: "PUT" }),
  );
  const call = vi
    .mocked(request)
    .mock.calls.find((c) => c[0].endsWith("/metadata"));
  expect(JSON.parse(call![1]!.body as string)).toMatchObject({
    sap_applicability: { system: "S4P" },
    request_id: expect.any(String),
  });
});
