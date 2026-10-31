import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { LineItem } from "@/api/types";
import { db } from "@/mocks/db";
import { renderApp, seed } from "./helpers";

describe("project card", () => {
  it("says the report is ready once a report exists", async () => {
    const { projectId, designId } = await seed("accepted");
    db.reports.push({
      id: "rep-1",
      designId,
      estimate_version: 1,
      renderId: db.renders[db.renders.length - 1].id,
      created_at: new Date().toISOString(),
      ready: true,
    });
    renderApp("/");
    const card = (await screen.findByText("Test house")).closest("[data-slot=card], li, article") as HTMLElement;
    expect(within(card ?? document.body).getByText("Report ready")).toBeInTheDocument();
    expect(screen.queryByText("Choosing materials")).not.toBeInTheDocument();
    expect(projectId).toBeTruthy();
  });

  it("shows the step while there is no report", async () => {
    await seed("accepted");
    renderApp("/");
    expect(await screen.findByText("Choosing materials")).toBeInTheDocument();
    expect(screen.queryByText("Report ready")).not.toBeInTheDocument();
  });
});

describe("mixed pack sizes", () => {
  it("lists each can size on the cost line", async () => {
    const { buyText } = await import("@/features/estimate/logic");
    const line = {
      purchase_quantity: 5,
      purchase_unit: "L",
      packs: 2,
      pack_size: null,
      pack_mix: [
        { size: 4, count: 1 },
        { size: 1, count: 1 },
      ],
    } as unknown as LineItem;
    expect(buyText(line)).toBe("5 L (1 × 4 L + 1 × 1 L)");
  });
});
