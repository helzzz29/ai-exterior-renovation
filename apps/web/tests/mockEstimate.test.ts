import { describe, expect, it } from "vitest";
import { computeEstimate } from "@/mocks/estimate";
import { MATERIALS_BY_ID } from "@/mocks/materials";
import { sampleRegions } from "@/mocks/sampleHouse";

const scale = {
  ft_per_px: 7 / 461,
  method: "door" as const,
  confidence: "medium" as const,
  explanation: "",
  needs_measurement: false,
};
const extras = { scaffolding_rate_per_sqft: 8, scaffolding_min_floors: 2, contingency_pct: 5, tax_pct: 18 };
const regions = sampleRegions().filter((r) => !r.proposed);

describe("mock estimate (demo numbers follow the real engine)", () => {
  const est = computeEstimate({
    regions,
    scale,
    assignments: [
      { region_id: "p-pillar-l", material_id: "stone-natural" },
      { region_id: "p-pillar-r", material_id: "stone-natural" },
    ],
    materials: MATERIALS_BY_ID,
    overrides: [],
    extras,
    floors: 2,
    scaleConfirmed: true,
    photoWarned: false,
  });

  it("prices two 10 × 1.2 ft pillars like the worked example", () => {
    const line = est.lines[0];
    expect(line.measured_quantity).toBeCloseTo(72, 0);
    expect(line.purchase_quantity).toBe(81);
    expect(line.material_cost).toBe(8910);
    expect(Math.abs(line.labour_cost - 3240)).toBeLessThan(20);
    expect(line.derivation.length).toBeGreaterThan(3);
  });

  it("adds scaffolding, contingency and tax, with a ±20% range", () => {
    expect(est.scaffolding).toBeGreaterThan(0);
    expect(est.grand_total).toBe(est.lines_total + est.scaffolding + est.contingency + est.tax);
    expect(est.range_pct).toBe(20);
    expect(est.range_low).toBeLessThan(est.grand_total);
    expect(est.provisional).toBe(false);
  });

  it("buys paint in whole cans and adds primer", () => {
    const e = computeEstimate({
      regions,
      scale,
      assignments: [{ region_id: "p-wall", material_id: "paint-emulsion" }],
      materials: MATERIALS_BY_ID,
      overrides: [{ material_id: "paint-emulsion", material_rate: 500 }],
      extras,
      floors: 1,
      scaleConfirmed: false,
      photoWarned: false,
    });
    const l = e.lines[0];
    expect(l.purchase_quantity % 4).toBe(0);
    expect(l.companions[0].name).toBe("Exterior primer");
    expect(l.rate_overridden).toBe(true);
    expect(e.scaffolding).toBe(0);
    expect(e.provisional).toBe(true);
  });
});
