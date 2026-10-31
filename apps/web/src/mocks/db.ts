/** In-memory state for the mock API. Persisted to localStorage in the browser demo. */
import type {
  AICallOut,
  Assignment,
  Estimate,
  Extras,
  JobOut,
  Label,
  Measurements,
  PhotoVerdict,
  Point,
  QAResult,
  RateOverride,
  RenderOut,
  ScaleOut,
} from "@/api/types";
import { bbox } from "./estimate";

export interface MUser {
  id: string;
  email: string;
  password: string;
}

export type JobEffect =
  | { type: "analysis"; outcome: "pass" | "warn" | "reject" }
  | { type: "advice" }
  | { type: "render"; renderId: string }
  | { type: "report"; reportId: string };

export interface MJob {
  id: string;
  kind: JobOut["kind"];
  status: JobOut["status"];
  step: string | null;
  error: string | null;
  steps: string[];
  progress: number;
  projectId: string;
  effect: JobEffect;
}

export interface MRegion {
  id: string;
  label: Label;
  polygon: Point[];
  source: "gemini" | "jev_box" | "user";
  needs_check: boolean;
  checked: boolean;
  proposed: boolean;
}

export interface MRender {
  id: string;
  designId: string;
  status: RenderOut["status"];
  image_url: string | null;
  qa: QAResult | null;
  attempts: number;
  user_note: string | null;
  fp: string;
  assignments: Assignment[];
  created_at: string;
}

export interface MDesign {
  id: string;
  projectId: string;
  name: string;
  assignments: Assignment[];
  created_at: string;
  renderIds: string[];
}

export interface MFinal {
  id: string;
  designId: string;
  version: number;
  fingerprint: string;
  estimate: Estimate;
}

export interface MReport {
  id: string;
  designId: string;
  estimate_version: number;
  renderId: string;
  created_at: string;
  ready: boolean;
}

export interface MScale {
  ft_per_px: number;
  method: ScaleOut["method"];
  confidence: ScaleOut["confidence"];
  facade_width_ft: number | null;
}

export interface MProject {
  id: string;
  ownerId: string;
  name: string;
  stage: "upload" | "analyzing" | "photo_rejected" | "photo_warning" | "regions_review" | "scale_review" | "designing";
  measurements: Measurements;
  hasPhoto: boolean;
  verdict: PhotoVerdict | null;
  verdict_overridden: boolean;
  regions_approved: boolean;
  scale_confirmed: boolean;
  activeJobId: string | null;
  created_at: string;
  updated_at: string;
  regions: MRegion[];
  regionsVersion: number;
  scaleSet: MScale | null;
  adviceReady: boolean;
  overrides: RateOverride[];
  extras: Extras;
  aiCalls: AICallOut[];
}

export interface DB {
  users: MUser[];
  sessionUserId: string | null;
  projects: MProject[];
  designs: MDesign[];
  renders: MRender[];
  finals: MFinal[];
  reports: MReport[];
  jobs: MJob[];
  seq: number;
}

const STORAGE_KEY = "home-makeover-mock-db-v1";

export const DEMO_USER = { email: "demo@example.com", password: "password123" };

function fresh(): DB {
  return {
    users: [{ id: "u-demo", ...DEMO_USER }],
    sessionUserId: null,
    projects: [],
    designs: [],
    renders: [],
    finals: [],
    reports: [],
    jobs: [],
    seq: 1,
  };
}

let persist = false;
export let db: DB = fresh();

/** Reset to an empty database (tests). */
export function resetDb(next?: Partial<DB>): void {
  db = { ...fresh(), ...next };
}

/** Browser demo: keep the state across reloads. */
export function enablePersistence(): void {
  persist = true;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) db = { ...fresh(), ...(JSON.parse(raw) as DB) };
  } catch {
    db = fresh();
  }
}

export function save(): void {
  if (!persist) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
  } catch {
    // Storage full or blocked: the demo keeps working in memory.
  }
}

export function nextId(prefix: string): string {
  db.seq += 1;
  return `${prefix}-${db.seq.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export const now = () => new Date().toISOString();

export const DEFAULT_EXTRAS: Extras = {
  scaffolding_rate_per_sqft: 8,
  scaffolding_min_floors: 2,
  contingency_pct: 5,
  tax_pct: 18,
};

/** The part outlines the estimate and size check use: everything except undecided proposals. */
export function approvedRegions(p: MProject): MRegion[] {
  return p.regions.filter((r) => !r.proposed);
}

export function pendingChecks(regions: MRegion[]): number {
  return regions.filter((r) => (r.needs_check && !r.checked) || r.proposed).length;
}

function facadeBox(p: MProject) {
  const walls = approvedRegions(p).filter((r) => r.label === "wall" || r.label === "parapet");
  if (!walls.length) return { x0: 0, y0: 0, x1: 2048, y1: 1536 };
  const pts = walls.flatMap((w) => w.polygon);
  return bbox(pts);
}

/** Work out the size reference the same way the backend does (simplified). */
export function scaleFor(p: MProject): ScaleOut {
  const box = facadeBox(p);
  const widthPx = box.x1 - box.x0;
  const heightPx = box.y1 - box.y0;
  const fmt = (ft: number) => `${Math.round(ft)} ft`;
  if (p.scaleSet) {
    const s = p.scaleSet;
    return {
      ...s,
      reference_box: null,
      explanation: s.facade_width_ft
        ? `We used your measurement. Your house is about ${fmt(s.facade_width_ft)} wide.`
        : "We used your measurement.",
      needs_measurement: false,
      confirmed: p.scale_confirmed,
    };
  }
  const m = p.measurements;
  if (m.facade_width_ft || m.facade_height_ft) {
    const fw = m.facade_width_ft ? m.facade_width_ft / widthPx : null;
    const fh = m.facade_height_ft ? m.facade_height_ft / heightPx : null;
    const f = fw && fh ? Math.sqrt(fw * fh) : (fw ?? fh ?? 0.015);
    return {
      ft_per_px: f,
      method: "user_measurement",
      confidence: "high",
      facade_width_ft: widthPx * f,
      reference_box: null,
      explanation: `We used your measurement. Your house is about ${fmt(widthPx * f)} wide.`,
      needs_measurement: false,
      confirmed: p.scale_confirmed,
    };
  }
  const doors = approvedRegions(p).filter((r) => r.label === "door");
  if (doors.length) {
    const main = doors
      .map((d) => bbox(d.polygon))
      .sort((a, b) => b.y1 - b.y0 - (a.y1 - a.y0))[0];
    const f = 7 / (main.y1 - main.y0);
    const width = widthPx * f;
    return {
      ft_per_px: f,
      method: "door",
      confidence: "medium",
      facade_width_ft: width,
      reference_box: main,
      explanation: `We used your main door as a guide (standard height 7 ft). That makes your house about ${fmt(width)} wide. Does that look right?`,
      needs_measurement: false,
      confirmed: p.scale_confirmed,
    };
  }
  const floors = m.floors ?? 2;
  const f = (floors * 10) / heightPx;
  return {
    ft_per_px: f,
    method: "floors",
    confidence: "low",
    facade_width_ft: widthPx * f,
    reference_box: null,
    explanation: "We couldn't find a clear guide such as a door, so this size is only a rough guess.",
    needs_measurement: true,
    confirmed: false,
  };
}
