import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import { FilesRail, DocumentViewer } from "./Files";
import { request, post } from "./api";
import { workspace } from "./test/fixtures";
vi.mock("./api", () => ({ request: vi.fn(), post: vi.fn() }));
it("renders uploads and version records and opens the selected artifact", async () => {
  const w = workspace();
  w.assets = [{ kind: "upload", name: "CR.txt", file_id: "u" }];
  w.state.artifact_registry = [
    {
      artifact_id: "BRD",
      artifact_type: "BRD",
      version: "1",
      approval_status: "pending_approval",
    },
  ];
  const open = vi.fn();
  render(<FilesRail workspace={w} onOpen={open} onChange={vi.fn()} />);
  expect(screen.getByText("CR.txt")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: /BRD v1/ }));
  expect(open).toHaveBeenCalledWith("BRD", "1");
});
it("reads artifact content, selects versions and approves through the backend", async () => {
  const w = workspace();
  const artifact = {
    artifact_id: "BRD",
    artifact_type: "BRD",
    artifact_version: "2",
    content: "# Business Requirements\n## Scope\nAutomate delivery creation",
    approval_status: "pending_approval",
    created_date: "2026-10-30T00:00:00Z",
    last_edited_date: "2026-10-30T00:00:00Z",
    edited_by: "local",
    approved_by: null,
    template_version: "1.0",
    sources: [],
  };
  vi.mocked(request).mockResolvedValue(artifact);
  vi.mocked(post).mockResolvedValue({
    workspace: w,
    artifact: { ...artifact, approval_status: "approved" },
  });
  const change = vi.fn(),
    version = vi.fn();
  render(
    <DocumentViewer
      projectId="p"
      artifactId="BRD"
      version="2"
      versions={[
        {
          artifact_id: "BRD",
          artifact_type: "BRD",
          version: "2",
          approval_status: "pending_approval",
        },
        {
          artifact_id: "BRD",
          artifact_type: "BRD",
          version: "1",
          approval_status: "rejected",
        },
      ]}
      onVersion={version}
      onBack={vi.fn()}
      onChange={change}
    />,
  );
  expect(await screen.findByText("Automate delivery creation")).toBeVisible();
  expect(screen.getAllByRole("option")).toHaveLength(2);
  await userEvent.selectOptions(screen.getByLabelText("Artifact version"), "1");
  expect(version).toHaveBeenCalledWith("1");
  await userEvent.click(
    screen.getByRole("button", { name: "Approve artifact" }),
  );
  expect(post).toHaveBeenCalledWith("/projects/p/artifacts/BRD/review", {
    action: "approve",
    version: "2",
    feedback: "",
  });
  expect(change).toHaveBeenCalledWith(w);
});
