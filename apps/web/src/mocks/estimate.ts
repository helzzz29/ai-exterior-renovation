/**
 * A compact TypeScript version of the backend estimation rules, used only by the
 * mock API so the demo shows believable, internally consistent numbers.
 */
import type {
  Assignment,
  CompanionLine as CompanionLine_,
  Estimate,
  Extras,
  Label,
  LineItem,
  MaterialOut,
  Point,
  RateOverride,
  ScaleResult,
  SurfaceMeasure,
} from "@/api/types";

export interface MockRegion {
  id: string;
  label: Label;
  polygon: Point[];
}

export interface EstimateInput {
  regions: MockRegion[];
  scale: ScaleResult;
  assignments: Assignment[];
  materials: Record<string, MaterialOut>;
  overrides: RateOverride[];
  extras: Extras;
  floors: number;
  scaleConfirmed: boolean;
  photoWarned: boolean;
}

const PRIORITY: Label[] = [
  "window",
  "door",
  "railing",
  "gate",
  "balcony",
  "pillar",
  "parapet",
  "roof_edge",
  "wall",
];
const OPENINGS = new Set<Label>(["window", "door"]);

export function polygonArea(poly: Point[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

export function bbox(poly: Point[]) {
  const xs = poly.map((p) => p[0]);
  const ys = poly.map((p) => p[1]);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
}

function overlap(a: Point[], b: Point[]): number {
  const A = bbox(a);
  const B = bbox(b);
  const w = Math.min(A.x1, B.x1) - Math.max(A.x0, B.x0);
  const h = Math.min(A.y1, B.y1) - Math.max(A.y0, B.y0);
  if (w <= 0 || h <= 0) return 0;
  // Scale the box overlap by how much of the higher-priority box is actually filled.
  const fill = polygonArea(b) / Math.max(1, (B.x1 - B.x0) * (B.y1 - B.y0));
  return w * h * Math.min(1, fill);
}

const r1 = (n: number) => Math.round(n * 10) / 10;
const r2 = (n: number) => Math.round(n * 100) / 100;
const inr = (n: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
    Math.round(n),
  );
const n1 = (n: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(n);
const n2 = (n: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(n);

export function measureSurfaces(regions: MockRegion[], f: number): SurfaceMeasure[] {
  return regions.map((reg) => {
    const pr = PRIORITY.indexOf(reg.label);
    const higher = regions.filter((o) => o.id !== reg.id && PRIORITY.indexOf(o.label) < pr);
    const gross = polygonArea(reg.polygon);
    const net = Math.max(0, gross - higher.reduce((s, o) => s + overlap(reg.polygon, o.polygon), 0));
    const b = bbox(reg.polygon);
    const wFt = (b.x1 - b.x0) * f;
    const hFt = (b.y1 - b.y0) * f;
    const fs = reg.label === "wall" ? 1.05 : 1;
    let area = net * f * f * fs;
    let length: number | null = null;
    if (reg.label === "pillar") area = hFt * 3 * wFt;
    if (reg.label === "gate") area = wFt * hFt;
    if (reg.label === "railing" || reg.label === "roof_edge" || reg.label === "parapet") length = r2(wFt);
    return {
      region_id: reg.id,
      label: reg.label,
      net_px: Math.round(net),
      fs,
      area_sqft: r1(area),
      length_ft: length,
    };
  });
}

const UNIT_WORD: Record<string, string> = {
  litre: "litres",
  kg: "kg",
  piece: "pieces",
  sqft: "sq ft",
  sheet: "sheets",
  rft: "running ft",
};

export function computeEstimate(input: EstimateInput): Estimate {
  const f = input.scale.ft_per_px;
  const measures = measureSurfaces(input.regions, f);
  const byId = Object.fromEntries(measures.map((m) => [m.region_id, m]));
  const surfaces = measures.filter((m) => !OPENINGS.has(m.label));
  const openings = measures.filter((m) => OPENINGS.has(m.label));

  // Group regions of the same label that share a material.
  const groups = new Map<string, { label: Label; material: MaterialOut; regionIds: string[] }>();
  for (const a of input.assignments) {
    const m = byId[a.region_id];
    const mat = input.materials[a.material_id];
    if (!m || !mat || OPENINGS.has(m.label)) continue;
    const key = `${m.label}|${mat.id}`;
    const g = groups.get(key) ?? { label: m.label, material: mat, regionIds: [] };
    g.regionIds.push(a.region_id);
    groups.set(key, g);
  }

  const lines: LineItem[] = [];
  for (const g of groups.values()) {
    const mat = g.material;
    const ov = input.overrides.find((o) => o.material_id === mat.id);
    const materialRate = ov?.material_rate ?? mat.material_rate;
    const labourRate = ov?.labour_rate ?? mat.labour_rate;
    const overridden = ov?.material_rate != null || ov?.labour_rate != null;
    const isLength = mat.measure_basis === "length";
    const measured = r1(
      g.regionIds.reduce((s, id) => {
        const m = byId[id];
        return s + (isLength ? (m.length_ft ?? 0) : m.area_sqft);
      }, 0),
    );
    const unitM = isLength ? "rft" : "sqft";
    const withW = r1(measured * (1 + mat.wastage_pct / 100));
    const der: string[] = [
      `Measured ${isLength ? "length" : "area"}: ${n1(measured)} ${UNIT_WORD[unitM]}`,
      `Plus ${mat.wastage_pct}% for cutting and wastage: ${n1(measured)} × ${n2(1 + mat.wastage_pct / 100)} = ${n1(withW)} ${UNIT_WORD[unitM]}`,
    ];
    let required = withW;
    let purchase = withW;
    let packs: number | null = null;
    let packSize: number | null = mat.pack_size ?? null;
    const unit = mat.pricing_unit;
    switch (mat.category) {
      case "paint": {
        required = (withW * mat.coats) / (mat.coverage_sqft_per_unit ?? 100);
        packs = Math.ceil(required / (mat.pack_size ?? 1));
        purchase = packs * (mat.pack_size ?? 1);
        der.push(
          `Paint: ${n1(withW)} × ${mat.coats} coats ÷ ${mat.coverage_sqft_per_unit} sq ft per litre = ${n2(required)} litres → ${packs} × ${mat.pack_size} litre cans = ${purchase} litres`,
        );
        break;
      }
      case "texture": {
        required = withW / (mat.coverage_sqft_per_unit ?? 10);
        packs = Math.ceil(required / (mat.pack_size ?? 1));
        purchase = packs * (mat.pack_size ?? 1);
        der.push(
          `Texture: ${n1(withW)} ÷ ${mat.coverage_sqft_per_unit} sq ft per kg = ${n2(required)} kg → ${packs} × ${mat.pack_size} kg bags = ${purchase} kg`,
        );
        break;
      }
      case "tiles": {
        const pieces = Math.ceil(withW / (mat.piece_area_sqft ?? 1));
        const per = mat.pieces_per_box ?? 1;
        packs = Math.ceil(pieces / per);
        packSize = per;
        required = pieces;
        purchase = packs * per;
        der.push(
          `Tiles: ${n1(withW)} ÷ ${mat.piece_area_sqft} sq ft per tile = ${pieces} tiles → ${packs} boxes of ${per} = ${purchase} tiles`,
        );
        break;
      }
      case "panel": {
        required = withW / (mat.piece_area_sqft ?? 32);
        purchase = Math.ceil(required);
        der.push(`Panels: ${n1(withW)} ÷ ${mat.piece_area_sqft} sq ft per sheet = ${n2(required)} → ${purchase} sheets`);
        break;
      }
      default: {
        required = withW;
        purchase = mat.category === "gate" ? r1(withW) : Math.ceil(withW);
        der.push(`To buy: ${n1(purchase)} ${UNIT_WORD[unit]}`);
      }
    }
    const companions: CompanionLine_[] = mat.companions.map((c) => {
      const q = withW * c.quantity_per_sqft;
      const p = Math.ceil(q / c.pack_size);
      const buy = p * c.pack_size;
      der.push(`${c.name}: ${n1(withW)} × ${n2(c.quantity_per_sqft)} = ${n2(q)} ${c.unit === "litre" ? "litres" : "kg"} → ${p} × ${c.pack_size} = ${buy}`);
      return { name: c.name, quantity: r2(q), unit: c.unit, packs: p, purchase_quantity: buy, rate: c.rate, cost: buy * c.rate };
    });
    const materialCost = Math.round(purchase * materialRate);
    const compCost = companions.reduce((s, c) => s + c.cost, 0);
    const labourCost = Math.round(measured * labourRate);
    der.push(
      `Material: ${n1(purchase)} ${UNIT_WORD[unit]} × ${inr(materialRate)}${companions.map((c) => ` + ${c.purchase_quantity} × ${inr(c.rate)}`).join("")} = ${inr(materialCost + compCost)}`,
    );
    der.push(`Labour: ${n1(measured)} ${UNIT_WORD[unitM]} × ${inr(labourRate)} = ${inr(labourCost)}`);
    const total = materialCost + compCost + labourCost;
    der.push(`Line total: ${inr(total)}`);
    lines.push({
      material_id: mat.id,
      material_name: mat.name,
      category: mat.category,
      label: g.label,
      region_ids: g.regionIds,
      measured_quantity: measured,
      measured_unit: unitM,
      wastage_pct: mat.wastage_pct,
      with_wastage: withW,
      required_quantity: r2(required),
      purchase_quantity: purchase,
      purchase_unit: unit,
      packs,
      pack_size: packSize,
      pack_mix: [],
      material_rate: materialRate,
      material_cost: materialCost,
      companions,
      labour_rate: labourRate,
      labour_cost: labourCost,
      total,
      rate_overridden: overridden,
      derivation: der,
    });
  }

  const linesTotal = lines.reduce((s, l) => s + l.total, 0);
  const wallArea = r1(surfaces.filter((s) => s.label === "wall").reduce((s, m) => s + m.area_sqft, 0));
  const ex = input.extras;
  const scaffolding = lines.length && input.floors >= ex.scaffolding_min_floors ? Math.round(wallArea * ex.scaffolding_rate_per_sqft) : 0;
  const contingency = Math.round(((linesTotal + scaffolding) * ex.contingency_pct) / 100);
  const tax = Math.round(((linesTotal + scaffolding + contingency) * ex.tax_pct) / 100);
  const grand = linesTotal + scaffolding + contingency + tax;
  let confidence = input.scale.confidence;
  if (input.photoWarned && confidence === "high") confidence = "medium";
  const rangePct = confidence === "high" ? 10 : confidence === "medium" ? 20 : 35;
  const subtotals: Record<string, number> = {};
  for (const l of lines) subtotals[l.category] = (subtotals[l.category] ?? 0) + l.total;

  const fingerprint = hash(
    JSON.stringify([input.regions, f, input.assignments, input.overrides, input.extras, input.floors, input.scaleConfirmed]),
  );
  return {
    lines,
    surfaces,
    openings,
    category_subtotals: subtotals,
    lines_total: linesTotal,
    wall_area_sqft: wallArea,
    scaffolding,
    contingency,
    tax,
    grand_total: grand,
    range_pct: rangePct,
    range_low: Math.round((grand * (100 - rangePct)) / 100),
    range_high: Math.round((grand * (100 + rangePct)) / 100),
    confidence,
    provisional: !input.scaleConfirmed,
    scale: input.scale,
    extras: input.extras,
    assumptions: [
      "Standard main door height of 7 ft used as a size guide unless you entered a measurement.",
      "Pillars are treated as square, with three sides visible.",
      "Only the front of the house is included. Side and back walls are not.",
      "Prices are typical for a large Indian city. Change them to match your quotes.",
    ],
    fingerprint,
  };
}

export function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(16);
}
