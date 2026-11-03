import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, vi, expect } from "vitest";
import Workspace from "./Workspace";
import { streamChat } from "./api";
import { workspace } from "./test/fixtures";
import type { Workspace as WorkspaceData } from "./types";
vi.mock("./api", () => ({ streamChat: vi.fn(), request: vi.fn() }));
vi.mock("./Files", () => ({
  FilesRail: ({ onChange }: { onChange: (w: WorkspaceData) => void }) => (
    <button
      onClick={() =>
        onChange({
          ...workspace(),
          snapshot_at: "2026-11-03T01:00:02+00:00",
          assets: [{ kind: "upload", file_id: "u", name: "sap_context.md" }],
        })
      }
    >
      Complete upload response
    </button>
  ),
  DocumentViewer: () => null,
}));
it("preserves a newer upload snapshot when an older chat result arrives afterward", async () => {
  const initial = { ...workspace(), snapshot_at: "2026-11-03T01:00:00+00:00" };
  const changed = vi.fn();
  let finish!: (v: Awaited<ReturnType<typeof streamChat>>) => void;
  vi.mocked(streamChat).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(
    <Workspace
      workspace={initial}
      onChange={changed}
      onBack={vi.fn()}
      onSettings={vi.fn()}
    />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Work on"), "Design");
  await userEvent.click(screen.getByRole("tab", { name: "Files" }));
  await userEvent.click(
    screen.getByRole("button", { name: "Complete upload response" }),
  );
  await act(async () =>
    finish({
      workspace: { ...initial, snapshot_at: "2026-11-03T01:00:01+00:00" },
      message: "Earlier chat result",
    }),
  );
  expect(changed).toHaveBeenCalledOnce();
  expect(changed.mock.calls[0][0].assets[0].name).toBe("sap_context.md");
});
