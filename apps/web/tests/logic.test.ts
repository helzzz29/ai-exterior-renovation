import { describe, expect, it } from "vitest";
import { toApiError } from "@/api/client";
import type { DesignOut, EstimateOut, MaterialOut, RegionOut, RenderOut, ScaleOut } from "@/api/types";
import { reportReadiness, toRatesPut, uniqueMaterials } from "@/features/estimate/logic";
import {
  adviceForGroup,
  assignGroup,
  groupChoice,
  groupParts,
  materialsForLabel,
} from "@/features/materials/logic";
import { PREVIEW_OPACITY, previewTileScale } from "@/features/materials/PreviewCanvas";
import { partRows } from "@/features/regions/PartsList";
import { scaleVariant } from "@/features/scale/ScaleStep";
import { needsUpdateMessage } from "@/features/wizard/NeedsUpdateBanner";
import { maxReachableStep, stepForStage } from "@/features/wizard/steps";
import { MATERIALS } from "@/mocks/materials";

describe("wizard steps", () => {
  it("opens only the steps the stage allows", () => {
    expect(maxReachableStep("upload")).toBe(0);
    expect(maxReachableStep("photo_warning")).toBe(0);
    expect(maxReachableStep("regions_review")).toBe(1);
    expect(maxReachableStep("scale_review")).toBe(2);
    expect(maxReachableStep("designing")).toBe(5);
  });
  it("sends each stage to its screen", () => {
    expect(stepForStage("analyzing")).toBe("photo");
    expect(stepForStage("regions_review")).toBe("parts");
    expect(stepForStage("scale_review")).toBe("size");
    expect(stepForStage("designing")).toBe("materials");
  });
});

const scale = (x: Partial<ScaleOut>): ScaleOut => ({
  ft_per_px: 0.015,
  method: "door",
  confidence: "medium",
  facade_width_ft: 23,
  reference_box: null,
  explanation: "",
  needs_measurement: false,
  confirmed: false,
  ...x,
});

describe("size check variants", () => {
  it("picks the right screen", () => {
    expect(scaleVariant(scale({ confidence: "high", method: "user_measurement" }))).toBe("high");
    expect(scaleVariant(scale({ confidence: "medium" }))).toBe("medium");
    expect(scaleVariant(scale({ confidence: "low", needs_measurement: true }))).toBe("low");
    expect(scaleVariant(scale({ confidence: "medium", needs_measurement: true }))).toBe("low");
    expect(scaleVariant(scale({ confirmed: true }))).toBe("confirmed");
  });
});

const render = (x: Partial<RenderOut> = {}): RenderOut => ({
  id: "r",
  status: "accepted",
  attempts: 1,
  stale: false,
  created_at: "",
  ...x,
});
const est = (x: Partial<EstimateOut> = {}) => ({ finalised: true, stale: false, ...x }) as EstimateOut;

describe("report download rules", () => {
  it("needs an accepted look and a finalised estimate, both up to date", () => {
    expect(reportReadiness(render(), est()).canDownload).toBe(true);
    expect(reportReadiness(render({ status: "ready" }), est()).canDownload).toBe(false);
    expect(reportReadiness(render({ stale: true }), est()).canDownload).toBe(false);
    expect(reportReadiness(render(), est({ finalised: false })).canDownload).toBe(false);
    expect(reportReadiness(render(), est({ stale: true })).canDownload).toBe(false);
    expect(reportReadiness(null, est()).canDownload).toBe(false);
    expect(reportReadiness(render(), est({ stale: true }))).toMatchObject({ lookAccepted: true, estimateFinal: false });
  });
});

describe("price editing", () => {
  const base = { scaffolding_rate_per_sqft: 8, scaffolding_min_floors: 2, contingency_pct: 5, tax_pct: 18 };
  it("sends only real changes and keeps blank extras at their usual value", () => {
    const body = toRatesPut(
      { a: { material: "500" }, b: { material: "", labour: "" }, c: { labour: "abc" } },
      { scaffolding: "10", contingency: "", tax: "12" },
      base,
    );
    expect(body.overrides).toEqual([{ material_id: "a", material_rate: 500, labour_rate: null }]);
    expect(body.extras).toEqual({ ...base, scaffolding_rate_per_sqft: 10, tax_pct: 12 });
  });
  it("lists each material once", () => {
    const lines = [{ material_id: "x" }, { material_id: "y" }, { material_id: "x" }] as Parameters<typeof uniqueMaterials>[0];
    expect(uniqueMaterials(lines)).toHaveLength(2);
  });
});

const reg = (id: string, label: RegionOut["label"], proposed = false): RegionOut => ({
  id,
  label,
  friendly_label: "",
  polygon: [
    [0, 0],
    [1, 0],
    [1, 1],
  ],
  source: "gemini",
  needs_check: false,
  checked: false,
  proposed,
});

describe("materials logic", () => {
  const regions = [reg("w", "wall"), reg("p1", "pillar"), reg("p2", "pillar"), reg("d", "door"), reg("r", "railing", true)];

  it("groups parts by kind and leaves windows, doors and suggestions out", () => {
    expect(groupParts(regions)).toEqual([
      { label: "wall", regionIds: ["w"] },
      { label: "pillar", regionIds: ["p1", "p2"] },
    ]);
  });

  it("assigns one material to every part in a group, and clears it", () => {
    let a = assignGroup([], ["p1", "p2"], "stone-natural");
    a = assignGroup(a, ["w"], "paint-emulsion", "#ffffff");
    expect(a).toHaveLength(3);
    expect(groupChoice(a, ["p1", "p2"])?.material_id).toBe("stone-natural");
    a = assignGroup(a, ["p1", "p2"], "stone-slate");
    expect(a.filter((x) => x.material_id === "stone-slate")).toHaveLength(2);
    a = assignGroup(a, ["p1", "p2"], null);
    expect(a).toEqual([{ region_id: "w", material_id: "paint-emulsion", color: "#ffffff" }]);
  });

  it("puts recommended materials first and not-ideal ones last", () => {
    const advice = adviceForGroup(
      [
        { region_id: "w", recommended: ["stone-natural"], not_ideal: { "paint-emulsion": "fades" }, probabilities: {} },
        { region_id: "other", recommended: ["acp-panel"], not_ideal: {}, probabilities: {} },
      ],
      ["w"],
    );
    expect([...advice.recommended]).toEqual(["stone-natural"]);
    const list = materialsForLabel(MATERIALS as MaterialOut[], "wall", advice).map((m) => m.id);
    expect(list[0]).toBe("stone-natural");
    expect(list[list.length - 1]).toBe("paint-emulsion");
    expect(list).not.toContain("railing-glass");
  });
});

describe("instant preview", () => {
  it("covers parts clearly and tiles textures at a sensible size", () => {
    expect(PREVIEW_OPACITY).toBeGreaterThanOrEqual(0.7);
    expect(previewTileScale(2048, 128)).toBeCloseTo(1.6, 5);
    expect(previewTileScale(4000, 1024)).toBeCloseTo(0.39, 2);
    expect(previewTileScale(2048, 4)).toBe(8);
    expect(previewTileScale(2048, 0)).toBe(1);
  });
});

describe("parts list grouping", () => {
  it("keeps questions first and groups the rest by kind", () => {
    const part = (key: string, label: RegionOut["label"], extra = {}) => ({
      key,
      id: key,
      label,
      polygon: [] as [number, number][],
      source: "gemini" as const,
      needsCheck: false,
      checked: false,
      proposed: false,
      ...extra,
    });
    const { pending, rows } = partRows([
      part("w1", "wall"),
      part("w2", "wall"),
      part("p1", "pillar", { needsCheck: true }),
      part("p2", "pillar"),
      part("r", "railing", { proposed: true }),
    ]);
    expect(pending.map((p) => p.key)).toEqual(["p1", "r"]);
    expect(rows.map((r) => [r.label, r.parts.length])).toEqual([
      ["wall", 2],
      ["pillar", 1],
    ]);
  });
});

describe("needs update banner", () => {
  const design = (x: Partial<DesignOut> = {}): DesignOut => ({
    id: "d",
    name: "Design 1",
    assignments: [],
    render: null,
    estimate_stale: false,
    estimate_finalised: false,
    created_at: "",
    ...x,
  });
  const p = { stage: "designing" as const, regions_approved: true, scale_confirmed: true };

  it("is quiet when nothing changed", () => {
    expect(needsUpdateMessage(p, [design()], design())).toBeNull();
  });
  it("asks to check the parts again first", () => {
    const m = needsUpdateMessage({ ...p, stage: "regions_review", regions_approved: false }, [design()], design());
    expect(m?.step).toBe("parts");
  });
  it("asks for a new look when the materials changed", () => {
    const d = design({ render: render({ stale: true }), estimate_stale: true });
    expect(needsUpdateMessage(p, [d], d)?.step).toBe("materials");
  });
  it("asks to finalise again when prices changed", () => {
    const d = design({ estimate_stale: true, estimate_finalised: true });
    const m = needsUpdateMessage(p, [d], d);
    expect(m?.text).toBe("Your estimate changed after you finalised it. Review it and finalise it again to update the report.");
  });
});

describe("friendly errors", () => {
  it("reads the contract's plain-language error, plain or wrapped", () => {
    expect(toApiError(422, { code: "blurry", message: "Too blurry" }).message).toBe("Too blurry");
    expect(toApiError(409, { detail: { code: "x", message: "Wrapped" } }).message).toBe("Wrapped");
    expect(toApiError(409, { detail: "Plain detail" }).message).toBe("Plain detail");
  });
  it("never shows technical validation details", () => {
    expect(toApiError(422, { detail: [{ loc: ["body"], msg: "field required" }] }).message).toBe(
      "Please check the details you entered.",
    );
    expect(toApiError(500, "Traceback").message).toMatch(/Something went wrong/);
    expect(toApiError(0, null).code).toBe("network");
  });
});
