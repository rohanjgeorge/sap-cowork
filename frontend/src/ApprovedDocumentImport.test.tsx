import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import ApprovedDocumentImport from "./ApprovedDocumentImport";
import { request } from "./api";
import { workspace } from "./test/fixtures";
vi.mock("./api", () => ({ request: vi.fn() }));
it("imports a selected draft without describing it as approved", async () => {
  const w = workspace();
  w.onboarding = {
    selected_artifacts: ["BRD"],
    pending_artifacts: ["BRD"],
    complete: false,
    artifact_statuses: { BRD: "draft" },
    message: "Please upload your draft BRD document.",
  };
  vi.mocked(request).mockResolvedValue(w);
  render(<ApprovedDocumentImport workspace={w} onChange={vi.fn()} />);
  expect(
    screen.getByRole("heading", { name: "Upload draft BRD" }),
  ).toBeVisible();
  expect(screen.getByText(/imported as a draft for review/)).toBeVisible();
  expect(
    screen.queryByLabelText("Approved BRD document"),
  ).not.toBeInTheDocument();
  await userEvent.upload(
    screen.getByLabelText("Draft BRD document"),
    new File(["Draft requirements"], "brd.md", { type: "text/markdown" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Import draft BRD" }),
  );
  expect(vi.mocked(request).mock.lastCall?.[0]).toBe(
    "/projects/p/onboarding/upload",
  );
});
it("requests only the current document, then moves to the next server-owned step", async () => {
  const w = workspace();
  w.onboarding = {
    selected_artifacts: ["BRD", "FRD"],
    pending_artifacts: ["BRD", "FRD"],
    complete: false,
    message: "Please upload your approved BRD document.",
  };
  const updated = {
    ...w,
    onboarding: {
      ...w.onboarding,
      pending_artifacts: ["FRD"],
      message: "Please upload your approved FRD document.",
    },
  };
  vi.mocked(request).mockResolvedValue(updated);
  const change = vi.fn();
  const view = render(
    <ApprovedDocumentImport workspace={w} onChange={change} />,
  );
  await userEvent.upload(
    screen.getByLabelText("Approved BRD document"),
    new File(["Approved requirements"], "brd.md", { type: "text/markdown" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Import approved BRD" }),
  );
  expect(change).toHaveBeenCalledWith(updated);
  const [url, options] = vi.mocked(request).mock.calls[0];
  expect(url).toBe("/projects/p/onboarding/upload");
  expect((options?.body as FormData).get("artifact_type")).toBe("BRD");
  view.rerender(
    <ApprovedDocumentImport workspace={updated} onChange={change} />,
  );
  expect(screen.getByLabelText("Approved FRD document")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Import approved FRD" }),
  ).toBeDisabled();
});
it("retains the current document and surfaces an upload failure", async () => {
  const w = workspace();
  w.onboarding = {
    selected_artifacts: ["BRD"],
    pending_artifacts: ["BRD"],
    complete: false,
    message: "Please upload BRD",
  };
  vi.mocked(request).mockRejectedValue(new Error("Upload failed"));
  const changed = vi.fn();
  render(<ApprovedDocumentImport workspace={w} onChange={changed} />);
  await userEvent.upload(
    screen.getByLabelText("Approved BRD document"),
    new File(["Text"], "brd.md", { type: "text/markdown" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Import approved BRD" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Upload failed");
  expect(changed).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Approved BRD document")).toBeVisible();
});
