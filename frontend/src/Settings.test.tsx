import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, vi, expect } from "vitest";
import Settings from "./Settings";
import { request } from "./api";
vi.mock("./api", () => ({ request: vi.fn(), post: vi.fn() }));
it("saves provider configuration through the settings endpoint", async () => {
  const settings = { default_provider: "fake", providers: {} };
  vi.mocked(request).mockResolvedValue(settings);
  render(<Settings onClose={vi.fn()} />);
  await screen.findByText("Provider settings");
  await userEvent.click(screen.getByRole("button", { name: "Save provider" }));
  expect(request).toHaveBeenCalledWith(
    "/settings/provider",
    expect.objectContaining({ method: "PUT" }),
  );
  expect(
    await screen.findByText(
      "Provider saved. Test the connection to verify access.",
    ),
  ).toBeVisible();
});
