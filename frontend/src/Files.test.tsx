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

it("warns before editing an approved document and submits the current revision", async () => {
  const w = workspace();
  const artifact = {
    artifact_id: "BRD",
    artifact_type: "BRD",
    artifact_version: "1",
    content: "# Approved scope",
    approval_status: "approved",
    sources: [],
  };
  vi.mocked(request)
    .mockResolvedValueOnce(artifact)
    .mockResolvedValueOnce({
      artifact: {
        ...artifact,
        artifact_version: "2",
        approval_status: "draft",
      },
      workspace: w,
    });
  const changed = vi.fn();
  render(
    <DocumentViewer
      projectId="p"
      artifactId="BRD"
      version="1"
      versions={[]}
      onVersion={vi.fn()}
      onBack={vi.fn()}
      onChange={changed}
      stateRevision={7}
    />,
  );
  await screen.findByText("Approved scope");
  await userEvent.click(screen.getByRole("button", { name: "Edit document" }));
  expect(screen.getByText(/Saving creates a new Draft/)).toBeVisible();
  await userEvent.type(
    screen.getByLabelText("Document content"),
    "\nAdditional scope",
  );
  await userEvent.click(screen.getByRole("button", { name: "Save document" }));
  const options = vi.mocked(request).mock.calls.at(-1)?.[1];
  expect(JSON.parse(String(options?.body))).toMatchObject({
    expected_revision: 7,
    new_version: false,
  });
  expect(changed).toHaveBeenCalledWith(w);
});

it("requires acceptance before adopting a significantly changed upload", async () => {
  const w = workspace();
  vi.mocked(request).mockResolvedValue({
    workspace: w,
    text_extracted: true,
    requires_confirmation: true,
    comparison: { diff: "- old\n+ new" },
  });
  render(<FilesRail workspace={w} onOpen={vi.fn()} onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Upload file" }));
  await userEvent.upload(
    screen.getByLabelText("Choose file"),
    new File(["new"], "changed.docx"),
  );
  await userEvent.selectOptions(screen.getByLabelText("Register as"), "BRD");
  await userEvent.click(screen.getByRole("button", { name: "Add to project" }));
  expect(
    await screen.findByLabelText("Uploaded document comparison"),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Add to project" })).toBeDisabled();
  await userEvent.click(
    screen.getByRole("checkbox", { name: /Accept this uploaded document/ }),
  );
  expect(screen.getByRole("button", { name: "Add to project" })).toBeEnabled();
});

it("shows BRD metadata as a formatted table while preserving the editable source", async () => {
  const content =
    "# Business Requirements Document (BRD)\n\n## Document Information\n\n| Field | Value |\n|---|---|\n| Document Title | STO Outbound Delivery Automation |\n| Client Organization | Example client [SRC-002] |\n\n## Business Rules\n\n- **Validate** the source plant.\n- Retain `STO` references.";
  vi.mocked(request).mockResolvedValue({
    artifact_id: "BRD",
    project_id: "p",
    artifact_type: "BRD",
    artifact_version: "1",
    content,
    approval_status: "draft",
    created_date: "2026-11-03T00:00:00Z",
    last_edited_date: "2026-11-03T00:00:00Z",
    edited_by: "local",
    approved_by: null,
    template_version: "brd.md",
    sources: [],
  });
  render(
    <DocumentViewer
      projectId="p"
      artifactId="BRD"
      version="1"
      versions={[]}
      onVersion={vi.fn()}
      onBack={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(
    await screen.findByRole("heading", {
      name: "Business Requirements Document (BRD)",
      level: 1,
    }),
  ).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "Field" })).toBeVisible();
  expect(
    screen.getByRole("cell", { name: "STO Outbound Delivery Automation" }),
  ).toBeVisible();
  expect(screen.getByText("Validate").tagName).toBe("STRONG");
  expect(
    screen.getByRole("table").closest(".document-table-scroll"),
  ).not.toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Edit document" }));
  expect(screen.getByLabelText("Document content")).toHaveValue(content);
});

it("keeps ABAP code literal instead of interpreting its table or heading characters", async () => {
  const content =
    "# Literal ABAP comment\n| source | target |\n| --- | --- |\nWRITE: / '<script>example</script>'.";
  vi.mocked(request).mockResolvedValue({
    artifact_id: "ABAP",
    artifact_type: "ABAP",
    artifact_version: "1",
    content,
    approval_status: "draft",
    sources: [],
  });
  const view = render(
    <DocumentViewer
      projectId="p"
      artifactId="ABAP"
      versions={[]}
      onVersion={vi.fn()}
      onBack={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  await screen.findByText(/Literal ABAP comment/);
  expect(view.container.querySelector("pre code")?.textContent).toBe(content);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(view.container.querySelector("script")).toBeNull();
});
