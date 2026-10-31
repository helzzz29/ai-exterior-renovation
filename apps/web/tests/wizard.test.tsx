import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { call, expectPlainLanguage, renderApp, seed } from "./helpers";

describe("wizard shell", () => {
  it("locks steps that aren't ready and marks the current one", async () => {
    const { projectId } = await seed("regions");
    renderApp(`/projects/${projectId}/parts`);
    const nav = await screen.findByRole("navigation", { name: "Your progress" });
    expect(nav).toHaveTextContent("Finish the earlier steps first");
    expect(screen.getByRole("link", { name: /Parts of your house/ })).toHaveAttribute("aria-current", "step");
    expect(screen.queryByRole("link", { name: /Cost & report/ })).not.toBeInTheDocument();
  });

  it("keeps the AI trace in a closed panel, in friendly words", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    const toggle = await screen.findByRole("button", { name: "How we worked this out" });
    expectPlainLanguage();
    await user.click(toggle);
    expect(await screen.findByText("Found the parts of your house")).toBeInTheDocument();
    expect(screen.getByText("Looking at your photo")).toBeInTheDocument();
    expect(screen.getAllByText("Checked your photo").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^C[1-6]$/)).not.toBeInTheDocument();
    // Technical names only appear here, in small print.
    expect(screen.getAllByText(/Gemini image model/)[0].closest("p")).toHaveClass("text-[11px]");
  });

  it("shows one “Needs update” banner after the parts change", async () => {
    const { projectId, designId } = await seed("assigned");
    const regions = await call<{ regions: { id: string; label: string; polygon: [number, number][] }[] }>(
      "GET",
      `/api/projects/${projectId}/regions`,
    );
    await call("PUT", `/api/projects/${projectId}/regions`, {
      regions: regions.regions
        .filter((r) => r.label !== "roof_edge")
        .map((r) => ({ id: r.id, label: r.label, polygon: r.polygon, checked: true, proposed: false })),
    });
    expect(db.projects[0].stage).toBe("regions_review");
    renderApp(`/projects/${projectId}/photo?design=${designId}`);
    const banner = await screen.findByTestId("needs-update");
    expect(banner).toHaveTextContent("You changed the parts of your house.");
    expect(screen.getByRole("link", { name: "Check the parts" })).toBeInTheDocument();
    expect(screen.getAllByTestId("needs-update")).toHaveLength(1);
  });

  it("logs out", async () => {
    await seed("upload");
    const { user } = renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Log out" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument());
    expect(db.sessionUserId).toBeNull();
  });
});
