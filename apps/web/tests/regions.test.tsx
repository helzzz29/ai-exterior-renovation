import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { db } from "@/mocks/db";
import { expectPlainLanguage, location, renderApp, seed } from "./helpers";
import { server } from "./server";

describe("Step 2: Parts of your house", () => {
  it("shows the unsure parts, the counter and a locked Continue", async () => {
    const { projectId } = await seed("regions");
    renderApp(`/projects/${projectId}/parts`);
    expect(await screen.findByText("We're not completely sure about 3 parts. Tap each one to confirm.")).toBeInTheDocument();
    expect(screen.getByTestId("check-counter")).toHaveTextContent("3 left to check");
    expect(screen.getByRole("button", { name: "Looks good, continue" })).toBeDisabled();
    expect(screen.getByText("Answer every “Please check” question first.")).toBeInTheDocument();
    // Questions and suggestions are told apart by their words, not only by their colour.
    expect(screen.getAllByText("Please check").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "Railing Suggestion" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Main wall" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Top wall edge (parapet)" })).toBeInTheDocument();
    expectPlainLanguage();
  });

  it("answers every question, saves and moves on to the size check", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);

    await user.click(await screen.findByRole("button", { name: "Pillar Please check" }));
    const card = screen.getByTestId("check-card");
    expect(within(card).getByText("Is this a pillar?")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Yes" }));
    expect(screen.getByTestId("check-counter")).toHaveTextContent("2 left to check");

    await user.click(screen.getByRole("button", { name: "Balcony Please check" }));
    await user.click(within(screen.getByTestId("check-card")).getByRole("button", { name: /No, it's a/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Top wall edge (parapet)" }));
    expect(screen.getByTestId("check-counter")).toHaveTextContent("1 left to check");

    await user.click(screen.getByRole("button", { name: "Railing Suggestion" }));
    expect(screen.getByText("Did we find a railing here?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, keep it" }));
    expect(screen.getByTestId("check-counter")).toHaveTextContent("Everything is checked");
    expect(screen.getByText("Thanks, everything is checked.")).toBeInTheDocument();

    const go = screen.getByRole("button", { name: "Looks good, continue" });
    expect(go).toBeEnabled();
    await user.click(go);
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/size`));
    const p = db.projects[0];
    expect(p.regions_approved).toBe(true);
    expect(p.regions.find((r) => r.id === "p-balcony")?.label).toBe("parapet");
    expect(p.regions.find((r) => r.id === "p-railing")?.proposed).toBe(false);
  });

  it("removes a wrong part and rejects a suggestion", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Pillar Please check" }));
    await user.click(within(screen.getByTestId("check-card")).getByRole("button", { name: "Remove it" }));
    // Removing asks first; keeping it changes nothing.
    const dialog = screen.getByRole("dialog", { name: "Remove this pillar?" });
    await user.click(within(dialog).getByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("check-counter")).toHaveTextContent("3 left to check");
    await user.click(within(screen.getByTestId("check-card")).getByRole("button", { name: "Remove it" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove part" }));
    await user.click(screen.getByRole("button", { name: "Railing Suggestion" }));
    await user.click(within(screen.getByTestId("proposed-card")).getByRole("button", { name: "No" }));
    expect(screen.getByTestId("check-counter")).toHaveTextContent("1 left to check");
    expect(screen.queryByRole("button", { name: "Railing Suggestion" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pillar Please check" })).not.toBeInTheDocument();
    // Saved automatically in the background.
    await waitFor(() => expect(db.projects[0].regions.some((r) => r.id === "p-railing")).toBe(false));
  });

  it("selects a normal part and lets the user remove it with the toolbar", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    const remove = await screen.findByRole("button", { name: "Remove" });
    expect(remove).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Roof edge" }));
    expect(within(screen.getByTestId("selected-card")).getByText("Roof edge")).toBeInTheDocument();
    await user.click(remove);
    await user.click(within(screen.getByRole("dialog", { name: "Remove this roof edge?" })).getByRole("button", { name: "Remove part" }));
    expect(screen.queryByRole("button", { name: "Roof edge" })).not.toBeInTheDocument();
  });

  it("shows the drawing hint when adding a part", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Add a part" }));
    expect(screen.getByText(/Tap the corners of the missing part/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish shape" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Cancel adding" }));
    expect(screen.queryByText(/Tap the corners/)).not.toBeInTheDocument();
  });

  it("groups the list by kind, with “Please check” parts first", async () => {
    const { projectId } = await seed("regions");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    const pending = await screen.findByTestId("pending-parts");
    expect(within(pending).getAllByRole("button")).toHaveLength(3);
    const windows = screen.getByRole("button", { name: "Window · 4" });
    expect(windows).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Window 1" })).not.toBeInTheDocument();
    await user.click(windows);
    expect(windows).toHaveAttribute("aria-expanded", "true");
    for (const n of [1, 2, 3, 4]) expect(screen.getByRole("button", { name: `Window ${n}` })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Window 3" }));
    expect(within(screen.getByTestId("selected-card")).getByText("Window")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Door · 2" })).toBeInTheDocument();
  });

  it("brings the question card into view and focuses it when a part is picked", async () => {
    const { projectId } = await seed("regions");
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    const { user } = renderApp(`/projects/${projectId}/parts`);
    await user.click(await screen.findByRole("button", { name: "Balcony Please check" }));
    const card = screen.getByTestId("part-card");
    expect(spy.mock.contexts).toContain(card);
    expect(card).toHaveFocus();
    expect(within(card).getByText("Is this a balcony?")).toBeInTheDocument();
    spy.mockRestore();
  });

  it("shows a friendly error when the parts can't be loaded", async () => {
    const { projectId } = await seed("regions");
    server.use(http.get("/api/projects/:id/regions", () => HttpResponse.json({}, { status: 503 })));
    renderApp(`/projects/${projectId}/parts`);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
  });
});
