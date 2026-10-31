import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "./helpers";

vi.mock("@/lib/config", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/config")>()),
  SIGNUP_OPEN: false,
}));

describe("invite-only build", () => {
  it("has no sign-up page and tells people to use the account they were given", async () => {
    renderApp("/register");
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Create an account/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Accounts are by invitation/)).toBeInTheDocument();
  });
});
