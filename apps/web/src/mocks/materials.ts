/** Mock material catalogue (shape of seed/materials.json + swatch_url) with generated swatches. */
import type { Label, MaterialAdvice, MaterialOut } from "@/api/types";
import { svgDataUrl } from "./sampleHouse";

const S = 128;

function swatchSvg(body: string, bg: string): string {
  return svgDataUrl(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}"><rect width="${S}" height="${S}" fill="${bg}"/>${body}</svg>`,
  );
}

const plain = (bg: string) =>
  swatchSvg(
    `<filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.06 0"/></filter><rect width="${S}" height="${S}" filter="url(#n)"/>`,
    bg,
  );

const texture = (bg: string) =>
  swatchSvg(
    `<filter id="t"><feTurbulence type="turbulence" baseFrequency="0.18" numOctaves="3"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.22 0"/></filter><rect width="${S}" height="${S}" filter="url(#t)"/>`,
    bg,
  );

function stone(bg: string, joint: string, rows: number): string {
  const h = S / rows;
  let body = "";
  for (let i = 0; i < rows; i++) {
    const y = i * h;
    const offset = i % 2 ? h * 0.9 : 0;
    body += `<line x1="0" y1="${y}" x2="${S}" y2="${y}" stroke="${joint}" stroke-width="3"/>`;
    for (let x = offset; x < S; x += h * 1.8) {
      body += `<line x1="${x}" y1="${y}" x2="${x}" y2="${y + h}" stroke="${joint}" stroke-width="3"/>`;
      const shade = ((i * 7 + x) % 5) / 30;
      body += `<rect x="${x + 2}" y="${y + 2}" width="${h * 1.8 - 4}" height="${h - 4}" fill="#000" fill-opacity="${shade.toFixed(2)}"/>`;
    }
  }
  return swatchSvg(body, bg);
}

function grid(bg: string, line: string, cols: number, rows: number): string {
  let body = "";
  for (let i = 1; i < cols; i++) body += `<line x1="${(i * S) / cols}" y1="0" x2="${(i * S) / cols}" y2="${S}" stroke="${line}" stroke-width="2"/>`;
  for (let i = 1; i < rows; i++) body += `<line x1="0" y1="${(i * S) / rows}" x2="${S}" y2="${(i * S) / rows}" stroke="${line}" stroke-width="2"/>`;
  return swatchSvg(body, bg);
}

function wood(bg: string): string {
  let body = "";
  for (let i = 0; i < 8; i++) {
    const y = i * 16;
    body += `<rect x="0" y="${y}" width="${S}" height="15" fill="#000" fill-opacity="${(i % 3) * 0.05}"/>`;
    body += `<path d="M0 ${y + 8} Q 32 ${y + 3} 64 ${y + 8} T ${S} ${y + 8}" stroke="#3b2414" stroke-opacity="0.25" fill="none"/>`;
  }
  return swatchSvg(body, bg);
}

function bars(bg: string, bar: string, glass = false): string {
  let body = glass
    ? `<rect x="0" y="20" width="${S}" height="${S - 30}" fill="#bfe3f2" fill-opacity="0.6"/><line x1="10" y1="30" x2="40" y2="100" stroke="#fff" stroke-width="4" stroke-opacity="0.7"/>`
    : "";
  body += `<rect x="0" y="12" width="${S}" height="10" fill="${bar}"/>`;
  if (!glass) for (let x = 8; x < S; x += 20) body += `<rect x="${x}" y="12" width="6" height="${S}" fill="${bar}"/>`;
  return swatchSvg(body, bg);
}

const primer = {
  kind: "primer" as const,
  name: "Exterior primer",
  unit: "litre" as const,
  quantity_per_sqft: 1 / 120,
  pack_size: 4,
  rate: 250,
};

const adhesive = {
  kind: "adhesive" as const,
  name: "Tile adhesive",
  unit: "kg" as const,
  quantity_per_sqft: 0.4,
  pack_size: 20,
  rate: 22,
};

type M = Omit<MaterialOut, "swatch" | "coats" | "companions" | "colorable" | "pack_sizes"> &
  Partial<Pick<MaterialOut, "coats" | "companions" | "colorable" | "pack_sizes">>;

function m(x: M): MaterialOut {
  return { coats: 1, companions: [], colorable: false, pack_sizes: [], swatch: `${x.id}.png`, ...x };
}

const SURFACES: Label[] = ["wall", "parapet", "pillar", "balcony"];

export const MATERIALS: MaterialOut[] = [
  m({
    id: "paint-emulsion",
    name: "Exterior emulsion paint",
    category: "paint",
    description: "Smooth, washable paint for outside walls. The most affordable option.",
    applicable_labels: [...SURFACES, "roof_edge"],
    pricing_unit: "litre",
    measure_basis: "area",
    coverage_sqft_per_unit: 110,
    coats: 2,
    pack_size: 4,
    wastage_pct: 5,
    material_rate: 420,
    labour_rate: 14,
    companions: [primer],
    colorable: true,
    default_color: "#e9dcc0",
    swatch_url: plain("#e9dcc0"),
    weather_resistance: "medium",
    durability: "5–7 years",
    maintenance: "Wash once a year. Repaint when it starts to fade.",
  }),
  m({
    id: "paint-weathershield",
    name: "Weatherproof paint",
    category: "paint",
    description: "A thick, stretchy paint that keeps out damp and covers fine cracks.",
    applicable_labels: [...SURFACES, "roof_edge"],
    pricing_unit: "litre",
    measure_basis: "area",
    coverage_sqft_per_unit: 90,
    coats: 2,
    pack_size: 4,
    wastage_pct: 5,
    material_rate: 650,
    labour_rate: 16,
    companions: [primer],
    colorable: true,
    default_color: "#d6e0d8",
    swatch_url: plain("#d6e0d8"),
    weather_resistance: "high",
    durability: "8–10 years",
    maintenance: "Rarely needs touch-ups.",
  }),
  m({
    id: "texture-rustic",
    name: "Textured finish",
    category: "texture",
    description: "A sand-textured coating that hides small cracks and uneven plaster.",
    applicable_labels: ["wall", "parapet", "pillar"],
    pricing_unit: "kg",
    measure_basis: "area",
    coverage_sqft_per_unit: 9,
    pack_size: 25,
    wastage_pct: 10,
    material_rate: 38,
    labour_rate: 24,
    colorable: true,
    default_color: "#cdb79e",
    swatch_url: texture("#cdb79e"),
    weather_resistance: "high",
    durability: "10–12 years",
    maintenance: "Clean with water once a year.",
  }),
  m({
    id: "stone-natural",
    name: "Natural stone cladding",
    category: "cladding",
    description: "Thin slices of real sandstone fixed to the wall. Warm and very long lasting.",
    applicable_labels: ["wall", "pillar", "parapet", "balcony"],
    pricing_unit: "sqft",
    measure_basis: "area",
    wastage_pct: 12,
    material_rate: 110,
    labour_rate: 45,
    swatch_url: stone("#c9a77c", "#8b6f4e", 6),
    weather_resistance: "high",
    durability: "25 years or more",
    maintenance: "Almost none. Seal every few years to keep the colour.",
  }),
  m({
    id: "stone-slate",
    name: "Slate stone cladding",
    category: "cladding",
    description: "Dark grey layered stone for a modern look.",
    applicable_labels: ["wall", "pillar", "parapet"],
    pricing_unit: "sqft",
    measure_basis: "area",
    wastage_pct: 12,
    material_rate: 160,
    labour_rate: 50,
    swatch_url: stone("#5b6270", "#2f343c", 8),
    weather_resistance: "high",
    durability: "20 years or more",
    maintenance: "Seal every 3 to 4 years.",
  }),
  m({
    id: "tiles-ceramic",
    name: "Ceramic wall tiles (1 × 2 ft)",
    category: "tiles",
    description: "Glazed outdoor tiles that are easy to wipe clean.",
    applicable_labels: ["wall", "pillar", "balcony", "parapet"],
    pricing_unit: "piece",
    measure_basis: "area",
    piece_area_sqft: 2,
    pieces_per_box: 6,
    wastage_pct: 10,
    material_rate: 55,
    labour_rate: 35,
    companions: [adhesive],
    swatch_url: grid("#d9d4cc", "#a8a29e", 2, 4),
    weather_resistance: "medium",
    durability: "15–20 years",
    maintenance: "Wipe clean. The joints may need redoing after some years.",
  }),
  m({
    id: "acp-panel",
    name: "Aluminium panels (ACP)",
    category: "panel",
    description: "Flat metal-faced sheets for a clean, modern front.",
    applicable_labels: ["wall", "balcony", "parapet", "roof_edge"],
    pricing_unit: "sheet",
    measure_basis: "area",
    piece_area_sqft: 32,
    wastage_pct: 10,
    material_rate: 3400,
    labour_rate: 65,
    colorable: true,
    default_color: "#9ca3af",
    swatch_url: grid("#9ca3af", "#6b7280", 2, 2),
    weather_resistance: "high",
    durability: "15–20 years",
    maintenance: "Wipe down twice a year.",
  }),
  m({
    id: "hpl-wood",
    name: "Wood-look panels (HPL)",
    category: "panel",
    description: "Panels with a wood finish for a warm accent.",
    applicable_labels: ["wall", "balcony", "pillar"],
    pricing_unit: "sheet",
    measure_basis: "area",
    piece_area_sqft: 32,
    wastage_pct: 10,
    material_rate: 5200,
    labour_rate: 75,
    swatch_url: wood("#a0693f"),
    weather_resistance: "medium",
    durability: "10–15 years",
    maintenance: "Clean and check every few months in rainy areas.",
  }),
  m({
    id: "railing-glass",
    name: "Toughened glass railing",
    category: "railing",
    description: "Clear safety glass with a steel top rail. Keeps the view open.",
    applicable_labels: ["railing"],
    pricing_unit: "rft",
    measure_basis: "length",
    wastage_pct: 5,
    material_rate: 1200,
    labour_rate: 200,
    swatch_url: bars("#e2e8f0", "#64748b", true),
    weather_resistance: "high",
    durability: "20 years or more",
    maintenance: "Clean the glass regularly.",
  }),
  m({
    id: "railing-ms",
    name: "Steel railing",
    category: "railing",
    description: "Painted mild steel bars. Strong and affordable.",
    applicable_labels: ["railing"],
    pricing_unit: "rft",
    measure_basis: "length",
    wastage_pct: 5,
    material_rate: 650,
    labour_rate: 120,
    colorable: true,
    default_color: "#1f2937",
    swatch_url: bars("#f1f5f9", "#1f2937"),
    weather_resistance: "medium",
    durability: "10–15 years",
    maintenance: "Repaint every 2 to 3 years to stop rust.",
  }),
  m({
    id: "gate-ms",
    name: "Steel gate",
    category: "gate",
    description: "A painted steel gate made to size.",
    applicable_labels: ["gate"],
    pricing_unit: "sqft",
    measure_basis: "area",
    wastage_pct: 5,
    material_rate: 900,
    labour_rate: 150,
    colorable: true,
    default_color: "#334155",
    swatch_url: bars("#e2e8f0", "#334155"),
    weather_resistance: "medium",
    durability: "15 years",
    maintenance: "Oil the hinges and repaint every few years.",
  }),
];

export const MATERIALS_BY_ID: Record<string, MaterialOut> = Object.fromEntries(
  MATERIALS.map((x) => [x.id, x]),
);

const RECOMMENDED: Partial<Record<Label, string[]>> = {
  wall: ["paint-weathershield", "stone-natural"],
  parapet: ["paint-weathershield"],
  pillar: ["stone-natural"],
  balcony: ["acp-panel"],
  roof_edge: ["paint-emulsion"],
  railing: ["railing-glass"],
  gate: ["gate-ms"],
};

const NOT_IDEAL: Partial<Record<Label, Record<string, string>>> = {
  wall: { "hpl-wood": "needs frequent maintenance in rain" },
  pillar: { "hpl-wood": "needs frequent maintenance in rain" },
  balcony: { "hpl-wood": "needs frequent maintenance in rain" },
  railing: { "railing-ms": "can rust quickly in heavy rain unless painted often" },
};

export function adviceFor(regionId: string, label: Label): MaterialAdvice {
  return {
    region_id: regionId,
    recommended: RECOMMENDED[label] ?? [],
    not_ideal: NOT_IDEAL[label] ?? {},
    exposed: label === "wall" || label === "parapet" ? 0.9 : 0.6,
    probabilities: {},
  };
}
