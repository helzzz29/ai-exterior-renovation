import type { EstimateOut, Extras, LineItem, RateOverride, RenderOut, ReportOut } from "@/api/types";
import { copy } from "@/copy";
import { formatNumber, unitWord } from "@/lib/format";

/**
 * The report to offer for download: the newest one built from exactly what is on screen now
 * (this finalised estimate version and this accepted new look). Anything older is ignored, so a
 * stale PDF is never offered. Order-independent: picks by creation time.
 */
export function currentReport(
  reports: ReportOut[] | null | undefined,
  estimateVersion: number | null | undefined,
  renderId: string | null | undefined,
): ReportOut | null {
  if (!reports?.length || estimateVersion == null || !renderId) return null;
  const matching = reports.filter((r) => r.estimate_version === estimateVersion && r.render_id === renderId);
  if (!matching.length) return null;
  return matching.reduce((a, b) => (Date.parse(b.created_at) > Date.parse(a.created_at) ? b : a));
}

/** The report needs an accepted, up-to-date design and a finalised, up-to-date estimate (G4 + G5). */
export function reportReadiness(render: RenderOut | null | undefined, estimate: EstimateOut | null | undefined) {
  const lookAccepted = !!render && render.status === "accepted" && !render.stale;
  const estimateFinal = !!estimate && estimate.finalised && !estimate.stale;
  return { lookAccepted, estimateFinal, canDownload: lookAccepted && estimateFinal };
}

/** Price fields being edited, as typed (strings), per material. */
export type RateDrafts = Record<string, { material?: string; labour?: string }>;
export type ExtrasDraft = { scaffolding: string; contingency: string; tax: string };

export function draftsFromOverrides(overrides: RateOverride[]): RateDrafts {
  const out: RateDrafts = {};
  for (const o of overrides) {
    out[o.material_id] = {
      material: o.material_rate != null ? String(o.material_rate) : undefined,
      labour: o.labour_rate != null ? String(o.labour_rate) : undefined,
    };
  }
  return out;
}

export function extrasDraft(e: Extras): ExtrasDraft {
  return {
    scaffolding: String(e.scaffolding_rate_per_sqft),
    contingency: String(e.contingency_pct),
    tax: String(e.tax_pct),
  };
}

function num(v: string | undefined): number | null {
  if (v == null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** A number of zero or more (what every price and percentage field accepts). */
export function isAmount(v: string): boolean {
  if (v.trim() === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0;
}

/**
 * Field ids with a problem, and what to say. A material or labour price may be left empty (it
 * then means "the usual price"); the extra-cost fields always need a number. Nothing is saved
 * while a field has a problem, so a typo never silently turns into another price.
 */
export function rateErrors(drafts: RateDrafts, extras: ExtrasDraft | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [id, d] of Object.entries(drafts)) {
    if (d.material != null && d.material.trim() !== "" && !isAmount(d.material)) out[`mat-${id}`] = copy.cost.badPrice;
    if (d.labour != null && d.labour.trim() !== "" && !isAmount(d.labour)) out[`lab-${id}`] = copy.cost.badPrice;
  }
  if (extras) {
    if (!isAmount(extras.scaffolding)) out["x-scaffolding"] = copy.cost.badNumber;
    if (!isAmount(extras.contingency)) out["x-contingency"] = copy.cost.badNumber;
    if (!isAmount(extras.tax)) out["x-tax"] = copy.cost.badNumber;
  }
  return out;
}

/** Turn the edited fields into the body of `PUT /projects/{id}/rates`. Blank = usual price. */
export function toRatesPut(drafts: RateDrafts, extras: ExtrasDraft, base: Extras) {
  const overrides: RateOverride[] = Object.entries(drafts)
    .map(([material_id, d]) => ({ material_id, material_rate: num(d.material), labour_rate: num(d.labour) }))
    .filter((o) => o.material_rate != null || o.labour_rate != null);
  return {
    overrides,
    extras: {
      ...base,
      scaffolding_rate_per_sqft: num(extras.scaffolding) ?? base.scaffolding_rate_per_sqft,
      contingency_pct: num(extras.contingency) ?? base.contingency_pct,
      tax_pct: num(extras.tax) ?? base.tax_pct,
    },
  };
}

/** One entry per material used, for the price editor. */
export function uniqueMaterials(lines: LineItem[]): LineItem[] {
  const seen = new Set<string>();
  return lines.filter((l) => (seen.has(l.material_id) ? false : (seen.add(l.material_id), true)));
}

/** File name for the downloaded PDF, e.g. "Meher Manzil - renovation report v2.pdf". */
export function reportFileName(projectName: string, version: number | null | undefined): string {
  const safe = projectName.replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim() || "home";
  return `${safe} - renovation report${version ? ` v${version}` : ""}.pdf`;
}

/** What to buy, e.g. "10 L (1 × 10 L)" or, for a mix of can sizes, "5 L (1 × 4 L + 1 × 1 L)". */
export function buyText(l: LineItem): string {
  const mix = l.pack_mix ?? [];
  if (mix.length > 1) {
    const parts = mix.map((p) => copy.cost.packs(p.count, formatNumber(p.size, 2), unitWord(l.purchase_unit, p.size)));
    return `${formatNumber(l.purchase_quantity, 2)} ${unitWord(l.purchase_unit, l.purchase_quantity)} (${parts.join(copy.cost.packJoin)})`;
  }
  if (l.packs && l.pack_size && l.purchase_unit !== "sqft" && l.purchase_unit !== "rft") {
    return `${formatNumber(l.purchase_quantity, 2)} ${unitWord(l.purchase_unit, l.purchase_quantity)} (${copy.cost.packs(
      l.packs,
      formatNumber(l.pack_size, 2),
      unitWord(l.purchase_unit, l.pack_size),
    )})`;
  }
  return `${formatNumber(l.purchase_quantity, 2)} ${unitWord(l.purchase_unit, l.purchase_quantity)}`;
}
