import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import ContextEvidence from "./ContextEvidence";
import { request, post } from "./api";
vi.mock("./api", () => ({ request: vi.fn(), post: vi.fn() }));
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(request).mockImplementation(async (url) => {
    if (url.endsWith("/sources"))
      return [
        {
          category: "SRC-08",
          name: "Customer systems",
          configured_adapters: [],
          reference_urls: [],
          local_project_sources: false,
        },
      ] as never;
    if (url.endsWith("/updates"))
      return [
        {
          record_id: "change",
          source: "org:policy",
          source_version: "2",
          domain: "STANDARDS_GOVERNANCE",
        },
      ] as never;
    if (url.endsWith("/updates/change"))
      return {
        diff: "-Old policy\n+New policy",
        metadata: {},
        current_fingerprint: "compared-version",
      } as never;
    return {
      plan: {
        artifact_type: "TDD",
        profile_version: "1.0",
        outcome: "qualified",
      },
      gap_report: [
        {
          requirement_id: "sap.release",
          gap_type: "uncertain",
          reason: "Release not verified",
          qualification: "Confirm before deployment",
        },
      ],
      package: {
        sap_technical_context: [
          {
            original_uri: "org:policy",
            source_id: "policy",
            source_version: "1",
            scope: "organization",
            domain: "SAP_TECHNICAL",
            evidence_status: "unknown",
          },
        ],
      },
    } as never;
  });
  vi.mocked(post).mockResolvedValue({});
});
it("shows qualifications and requires comparison before accepting a source change", async () => {
  render(<ContextEvidence projectId="p" planRef="plan" />);
  expect(
    await screen.findByText("Release not verified", { exact: false }),
  ).toBeVisible();
  expect(screen.getByText("No adapter configured", { exact: false })).toBeInTheDocument();
  const accept = screen.getByRole("button", { name: "Accept source update" });
  expect(accept).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Compare source changes" }),
  );
  expect(await screen.findByText(/New policy/)).toBeVisible();
  await userEvent.click(accept);
  expect(post).toHaveBeenCalledWith(
    "/projects/p/context/updates/change/review",
    { approved: true, expected_fingerprint: "compared-version" },
  );
});
it("keeps source review actions disabled for completed projects", async () => {
  render(<ContextEvidence projectId="p" planRef="plan" readOnly />);
  expect(
    await screen.findByRole("button", { name: "Keep current source copy" }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Compare source changes" }),
  );
  expect(
    await screen.findByRole("button", { name: "Accept source update" }),
  ).toBeDisabled();
});
