import type { Assignment, Label, MaterialAdvice, MaterialOut, RegionOut } from "@/api/types";
import { LABELS, OPENING_LABELS } from "@/lib/labels";

export interface PartGroup {
  label: Label;
  regionIds: string[];
}

/** Parts that can get a new material, grouped by what they are. Windows and doors stay as they are. */
export function groupParts(regions: RegionOut[]): PartGroup[] {
  const groups: PartGroup[] = [];
  for (const label of LABELS) {
    if (OPENING_LABELS.has(label)) continue;
    const ids = regions.filter((r) => r.label === label && !r.proposed).map((r) => r.id);
    if (ids.length) groups.push({ label, regionIds: ids });
  }
  return groups;
}

export interface GroupAdvice {
  recommended: Set<string>;
  notIdeal: Record<string, string>;
}

export function adviceForGroup(advice: MaterialAdvice[], regionIds: string[]): GroupAdvice {
  const recommended = new Set<string>();
  const notIdeal: Record<string, string> = {};
  for (const a of advice) {
    if (!regionIds.includes(a.region_id)) continue;
    a.recommended.forEach((id) => recommended.add(id));
    Object.assign(notIdeal, a.not_ideal);
  }
  for (const id of recommended) delete notIdeal[id];
  return { recommended, notIdeal };
}

/** Materials that suit this kind of part: recommended first, "not ideal" last. */
export function materialsForLabel(materials: MaterialOut[], label: Label, advice: GroupAdvice): MaterialOut[] {
  const rank = (m: MaterialOut) => (advice.recommended.has(m.id) ? 0 : advice.notIdeal[m.id] ? 2 : 1);
  return materials
    .filter((m) => m.applicable_labels.includes(label))
    .map((m, i) => ({ m, i }))
    .sort((a, b) => rank(a.m) - rank(b.m) || a.i - b.i)
    .map(({ m }) => m);
}

/** The material and colour currently chosen for a group (taken from its first part). */
export function groupChoice(assignments: Assignment[], regionIds: string[]): Assignment | null {
  return assignments.find((a) => regionIds.includes(a.region_id)) ?? null;
}

/** Give every part in the group the same material and colour, or clear it (`materialId` null). */
export function assignGroup(
  assignments: Assignment[],
  regionIds: string[],
  materialId: string | null,
  color: string | null = null,
): Assignment[] {
  const rest = assignments.filter((a) => !regionIds.includes(a.region_id));
  if (!materialId) return rest;
  return [...rest, ...regionIds.map((region_id) => ({ region_id, material_id: materialId, color }))];
}

/** Swatches offered for paint and texture. Names match the report (apps/api renocore/exports/palette.py). */
export const COLOUR_PRESETS = [
  { hex: "#f5f0e6", name: "Off-white" },
  { hex: "#e9dcc0", name: "Warm beige" },
  { hex: "#d6e0d8", name: "Pale sage" },
  { hex: "#cdb79e", name: "Sandstone" },
  { hex: "#c97b5a", name: "Terracotta" },
  { hex: "#9ca3af", name: "Light grey" },
  { hex: "#5b6270", name: "Slate grey" },
  { hex: "#1f2937", name: "Charcoal" },
];
