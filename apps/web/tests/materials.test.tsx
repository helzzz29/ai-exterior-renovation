import { screen, waitFor, within } from "@testing-library/react";
import { delay, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { expectPlainLanguage, location, renderApp, seed } from "./helpers";
import { server } from "./server";

/** Make saving material choices slow, so the "Saving…" state can be seen. */
function slowSaves(ms = 600) {
  server.use(
    http.put("/api/designs/:designId/assignments", async () => {
      await delay(ms);
      // no response: carry on to the normal mock handler
    }),
  );
}

function wallGroup() {
  return screen.getByRole("radiogroup", { name: /Main wall/ });
}

describe("Step 4: Pick finishes", () => {
  it("shows the one design the project starts with", async () => {
    const { projectId } = await seed("designing");
    renderApp(`/projects/${projectId}/materials`);
    expect(await screen.findByRole("tab", { name: "Design 1" })).toHaveAttribute("aria-selected", "true");
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    expect(db.designs).toHaveLength(1);
  });

  it("never creates a design by itself; waits for the one the server makes", async () => {
    const { projectId } = await seed("designing");
    const made = db.designs[0];
    db.designs = [];
    renderApp(`/projects/${projectId}/materials`);
    expect(await screen.findByText("Loading materials…")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 300));
    expect(db.designs).toHaveLength(0);
    db.designs.push(made);
    expect(await screen.findByRole("tab", { name: "Design 1" })).toBeInTheDocument();
    expect(db.designs).toHaveLength(1);
  });

  it("keeps a choice made just before leaving the screen", async () => {
    const { projectId, designId } = await seed("designing");
    slowSaves();
    const { user } = renderApp(`/projects/${projectId}/materials`);
    await user.click(await within(await screen.findByRole("radiogroup", { name: /Main wall/ })).findByRole("radio", { name: /Weatherproof paint/ }));
    expect(screen.getByText("Saving…")).toBeInTheDocument();
    expect(screen.queryByText("Choices saved")).not.toBeInTheDocument();
    // Leave at once through the stepper, before the automatic save would run.
    await user.click(screen.getByRole("link", { name: /Measure up/ }));
    await waitFor(() =>
      expect(db.designs.find((d) => d.id === designId)?.assignments.map((a) => a.material_id)).toEqual([
        "paint-weathershield",
      ]),
    );
  });

  it("only says “Choices saved” after the save has finished", async () => {
    const { projectId } = await seed("designing");
    slowSaves();
    const { user } = renderApp(`/projects/${projectId}/materials`);
    await user.click(await within(await screen.findByRole("radiogroup", { name: /Main wall/ })).findByRole("radio", { name: /Weatherproof paint/ }));
    expect(screen.getByText("Saving…")).toBeInTheDocument();
    expect(await screen.findByText("Choices saved")).toBeInTheDocument();
    expect(db.designs[0].assignments).toHaveLength(1);
  });

  it("shows advice tags, durability and upkeep in plain words", async () => {
    const { projectId } = await seed("designing");
    renderApp(`/projects/${projectId}/materials`);
    await screen.findByRole("radiogroup", { name: /Main wall/ });
    const wall = wallGroup();
    expect(await within(wall).findAllByText("Recommended")).not.toHaveLength(0);
    expect(within(wall).getByText("Not ideal here: needs frequent maintenance in rain")).toBeInTheDocument();
    expect(within(wall).getAllByText(/Lasts /).length).toBeGreaterThan(3);
    expect(within(wall).getAllByText(/Upkeep:/).length).toBeGreaterThan(3);
    // Windows and doors are never offered.
    expect(screen.queryByRole("radiogroup", { name: /Window/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: /Door/ })).not.toBeInTheDocument();
    expectPlainLanguage();
  });

  it("picks a material and a colour and saves them automatically", async () => {
    const { projectId, designId } = await seed("designing");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    const createLook = await screen.findByRole("button", { name: "Create my new look" });
    expect(createLook).toBeDisabled();
    await user.click(within(wallGroup()).getByRole("radio", { name: /Weatherproof paint/ }));
    expect(within(wallGroup()).getByRole("radio", { name: /Weatherproof paint/ })).toHaveAttribute("aria-checked", "true");
    expect(createLook).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Terracotta" }));
    await waitFor(() =>
      expect(db.designs.find((d) => d.id === designId)?.assignments).toEqual([
        { region_id: "p-wall", material_id: "paint-weathershield", color: "#c97b5a" },
      ]),
    );
  });

  it("applies one choice to every part of the same kind", async () => {
    const { projectId, designId } = await seed("designing");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    // One kind of part is open at a time; the pillars open from their header.
    await screen.findByRole("radiogroup", { name: /Main wall/ });
    expect(screen.queryByRole("radiogroup", { name: /Pillar/ })).not.toBeInTheDocument();
    expect(screen.getByText("2 parts")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Pillar/ }));
    const pillars = screen.getByRole("radiogroup", { name: /Pillar/ });
    expect(screen.getByText(/Your choice applies to all 2 parts of this kind/)).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: /Main wall/ })).not.toBeInTheDocument();
    await user.click(within(pillars).getByRole("radio", { name: /Natural stone cladding/ }));
    await waitFor(() => expect(db.designs.find((d) => d.id === designId)?.assignments).toHaveLength(2));
  });

  it("duplicates and renames a design, then switches back", async () => {
    const { projectId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    await screen.findByRole("tab", { name: "Design 1" });
    await user.click(screen.getByRole("button", { name: "Duplicate" }));
    const copyTab = await screen.findByRole("tab", { name: "Design 1 (copy)" });
    await waitFor(() => expect(copyTab).toHaveAttribute("aria-selected", "true"));
    expect(db.designs).toHaveLength(2);
    expect(db.designs[1].assignments).toEqual(db.designs[0].assignments);

    await user.click(screen.getByRole("button", { name: "Rename" }));
    const input = screen.getByLabelText("Design name");
    await user.clear(input);
    await user.type(input, "Stone look");
    await user.click(screen.getByRole("button", { name: "Save name" }));
    expect(await screen.findByRole("tab", { name: "Stone look" })).toBeInTheDocument();
    // Saved on the server, not just in this browser.
    expect(db.designs[1].name).toBe("Stone look");

    await user.click(screen.getByRole("tab", { name: "Design 1" }));
    await waitFor(() => expect(location()).toContain(`design=${db.designs[0].id}`));
    expect(screen.getByRole("tab", { name: "Design 1" })).toHaveAttribute("aria-selected", "true");
  });

  it("creates a new empty design", async () => {
    const { projectId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    await screen.findByRole("tab", { name: "Design 1" });
    await user.click(screen.getByRole("button", { name: "New design" }));
    const tab = await screen.findByRole("tab", { name: "Design 2" });
    await waitFor(() => expect(tab).toHaveAttribute("aria-selected", "true"));
    expect(db.designs[1].assignments).toEqual([]);
  });

  it("“Create my new look” starts the redesign and opens step 5", async () => {
    const { projectId, designId } = await seed("assigned");
    const { user } = renderApp(`/projects/${projectId}/materials`);
    const btn = await screen.findByRole("button", { name: "Create my new look" });
    await waitFor(() => expect(btn).toBeEnabled());
    await user.click(btn);
    await waitFor(() => expect(location()).toBe(`/projects/${projectId}/look?design=${designId}`));
    expect(db.renders).toHaveLength(1);
  });
});
