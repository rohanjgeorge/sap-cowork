import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, it, expect } from "vitest";
import { Login } from "./App";
import { post } from "./api";
vi.mock("./api", () => ({ post: vi.fn(), request: vi.fn() }));
it("signs into the local session without exposing the code", async () => {
  vi.mocked(post).mockResolvedValue({ user_id: "local" });
  const onLogin = vi.fn();
  render(<Login onLogin={onLogin} />);
  await userEvent.type(screen.getByLabelText("Local access code"), "private");
  await userEvent.click(
    screen.getByRole("button", { name: "Enter workspace" }),
  );
  expect(post).toHaveBeenCalledWith("/session", { access_code: "private" });
  expect(onLogin).toHaveBeenCalled();
  expect(screen.getByLabelText("Local access code")).toHaveAttribute(
    "type",
    "password",
  );
});
