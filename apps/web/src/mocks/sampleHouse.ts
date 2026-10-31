/**
 * A procedurally drawn two-storey house used by the mock API as the "uploaded" photo.
 * Geometry follows the estimation worked example: 2048 × 1536 px working image, a main door
 * 461 px tall (7 ft -> 0.015184 ft/px), two pillars 10 ft × 1.2 ft and a 480 px wide balcony railing.
 */
import type { Label, Point } from "@/api/types";

export const PHOTO_W = 2048;
export const PHOTO_H = 1536;

type Rect = [number, number, number, number];

function rect([x0, y0, x1, y1]: Rect): Point[] {
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

export interface SampleRegion {
  id: string;
  label: Label;
  polygon: Point[];
  source: "gemini" | "jev_box" | "user";
  needs_check: boolean;
  proposed: boolean;
}

const R = {
  wall: [274, 380, 1774, 1380] as Rect,
  parapet: [254, 300, 1794, 380] as Rect,
  roofEdge: [234, 280, 1814, 300] as Rect,
  pillarL: [274, 720, 353, 1380] as Rect,
  pillarR: [1695, 720, 1774, 1380] as Rect,
  balcony: [700, 640, 1180, 760] as Rect,
  railing: [700, 560, 1180, 640] as Rect,
  door: [894, 919, 1154, 1380] as Rect,
  win1: [450, 1000, 670, 1264] as Rect,
  win2: [1380, 1000, 1600, 1264] as Rect,
  win3: [450, 440, 670, 704] as Rect,
  win4: [1380, 440, 1600, 704] as Rect,
  balconyDoor: [820, 420, 1060, 640] as Rect,
};

export function sampleRegions(): SampleRegion[] {
  const g = (id: string, label: Label, r: Rect, extra: Partial<SampleRegion> = {}): SampleRegion => ({
    id,
    label,
    polygon: rect(r),
    source: "gemini",
    needs_check: false,
    proposed: false,
    ...extra,
  });
  return [
    g("p-wall", "wall", R.wall),
    g("p-parapet", "parapet", R.parapet),
    g("p-roof", "roof_edge", R.roofEdge),
    g("p-pillar-l", "pillar", R.pillarL),
    g("p-pillar-r", "pillar", R.pillarR, { needs_check: true }),
    g("p-balcony", "balcony", R.balcony, { needs_check: true }),
    g("p-door", "door", R.door),
    g("p-door-2", "door", R.balconyDoor),
    g("p-win-1", "window", R.win1),
    g("p-win-2", "window", R.win2),
    g("p-win-3", "window", R.win3),
    g("p-win-4", "window", R.win4),
    g("p-railing", "railing", R.railing, { source: "jev_box", proposed: true }),
  ];
}

/** Optional fill colours per part, used to draw the "after" picture. */
export type Fills = Partial<Record<Label, string>>;

const BASE: Required<Pick<Fills, "wall" | "parapet" | "roof_edge" | "pillar" | "balcony" | "railing">> = {
  wall: "#e7d8bd",
  parapet: "#d9c7a6",
  roof_edge: "#6b4f3a",
  pillar: "#d2bf9e",
  balcony: "#cfc6b8",
  railing: "#3f3f46",
};

function r(rc: Rect, fill: string, extra = ""): string {
  const [x0, y0, x1, y1] = rc;
  return `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="${fill}" ${extra}/>`;
}

function windowSvg([x0, y0, x1, y1]: Rect): string {
  const w = x1 - x0;
  const h = y1 - y0;
  const bars = Array.from({ length: 5 }, (_, i) => {
    const x = x0 + ((i + 1) * w) / 6;
    return `<line x1="${x}" y1="${y0 + 10}" x2="${x}" y2="${y1 - 10}" stroke="#334155" stroke-width="5"/>`;
  }).join("");
  return [
    r([x0 - 14, y0 - 14, x1 + 14, y1 + 14], "#f8fafc"),
    `<rect x="${x0}" y="${y0}" width="${w}" height="${h}" fill="url(#glass)"/>`,
    `<line x1="${x0 + w / 2}" y1="${y0}" x2="${x0 + w / 2}" y2="${y1}" stroke="#f8fafc" stroke-width="10"/>`,
    bars,
    r([x0 - 24, y1 + 14, x1 + 24, y1 + 30], "#cbd5e1"),
  ].join("");
}

/** Build the SVG markup. `fills` recolours parts; `tint` lays a soft colour wash over the picture. */
export function houseSvg(fills: Fills = {}, tint?: string): string {
  const f = { ...BASE, ...fills };
  const [dx0, dy0, dx1, dy1] = R.door;
  const railBars = Array.from({ length: 17 }, (_, i) => {
    const x = R.railing[0] + 12 + i * 28;
    return `<line x1="${x}" y1="${R.railing[1] + 8}" x2="${x}" y2="${R.railing[3]}" stroke="${f.railing}" stroke-width="7"/>`;
  }).join("");
  const blocks = Array.from({ length: 14 }, (_, row) => {
    const y = R.wall[1] + row * 72;
    return `<line x1="${R.wall[0]}" y1="${y}" x2="${R.wall[2]}" y2="${y}" stroke="#000" stroke-opacity="0.035" stroke-width="3"/>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${PHOTO_W}" height="${PHOTO_H}" viewBox="0 0 ${PHOTO_W} ${PHOTO_H}">
<defs>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9cc9ef"/><stop offset="1" stop-color="#e3f0fb"/></linearGradient>
<linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7aa7c7"/><stop offset="1" stop-color="#2f5d7c"/></linearGradient>
<linearGradient id="shade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000" stop-opacity="0.08"/><stop offset="0.5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.1"/></linearGradient>
</defs>
<rect width="${PHOTO_W}" height="${PHOTO_H}" fill="url(#sky)"/>
<circle cx="1820" cy="160" r="70" fill="#fff7d6" opacity="0.9"/>
<ellipse cx="160" cy="1240" rx="190" ry="260" fill="#5d8a4e"/>
<ellipse cx="1930" cy="1220" rx="170" ry="280" fill="#4f7d43"/>
<rect x="0" y="1380" width="${PHOTO_W}" height="156" fill="#a3a091"/>
<rect x="0" y="1380" width="${PHOTO_W}" height="18" fill="#8a877a"/>
<polygon points="894,1536 1154,1536 1104,1380 944,1380" fill="#c9c3b3"/>
${r(R.roofEdge, f.roof_edge)}
${r(R.parapet, f.parapet)}
${r(R.wall, f.wall)}
${blocks}
<rect x="${R.wall[0]}" y="${R.wall[1]}" width="${R.wall[2] - R.wall[0]}" height="${R.wall[3] - R.wall[1]}" fill="url(#shade)"/>
${r([R.wall[0], 700, R.wall[2], 720], "#000", 'fill-opacity="0.08"')}
${r(R.pillarL, f.pillar)}${r(R.pillarR, f.pillar)}
${r([R.pillarL[0] - 8, 700, R.pillarL[2] + 8, 724], "#bfae8e")}${r([R.pillarR[0] - 8, 700, R.pillarR[2] + 8, 724], "#bfae8e")}
${r(R.balconyDoor, "#5b3b25")}${r([R.balconyDoor[0] + 20, R.balconyDoor[1] + 20, R.balconyDoor[2] - 20, R.balconyDoor[3]], "url(#glass)")}
${r(R.balcony, f.balcony)}
${r([R.balcony[0] - 10, R.balcony[1] - 6, R.balcony[2] + 10, R.balcony[1] + 10], "#9b9488")}
<line x1="${R.railing[0]}" y1="${R.railing[1] + 6}" x2="${R.railing[2]}" y2="${R.railing[1] + 6}" stroke="${f.railing}" stroke-width="12"/>
${railBars}
${windowSvg(R.win1)}${windowSvg(R.win2)}${windowSvg(R.win3)}${windowSvg(R.win4)}
${r([dx0 - 18, dy0 - 18, dx1 + 18, dy1], "#efe7da")}
${r(R.door, "#7a4a2a")}
${r([dx0 + 24, dy0 + 24, dx0 + 116, dy0 + 200], "#6a3f23")}${r([dx0 + 144, dy0 + 24, dx1 - 24, dy0 + 200], "#6a3f23")}
${r([dx0 + 24, dy0 + 240, dx0 + 116, dy1 - 30], "#6a3f23")}${r([dx0 + 144, dy0 + 240, dx1 - 24, dy1 - 30], "#6a3f23")}
<circle cx="${dx1 - 40}" cy="${dy0 + 230}" r="9" fill="#e5c07b"/>
<rect x="560" y="1300" width="70" height="80" rx="10" fill="#9a5b3c"/><ellipse cx="595" cy="1290" rx="60" ry="40" fill="#5f8f4f"/>
<rect x="1420" y="1300" width="70" height="80" rx="10" fill="#9a5b3c"/><ellipse cx="1455" cy="1290" rx="60" ry="40" fill="#5f8f4f"/>
${tint ? `<rect width="${PHOTO_W}" height="${PHOTO_H}" fill="${tint}" opacity="0.08"/>` : ""}
</svg>`;
}

export function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function samplePhotoUrl(): string {
  return svgDataUrl(houseSvg());
}
