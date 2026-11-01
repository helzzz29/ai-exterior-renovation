/**
 * Mock implementation of every endpoint in apps/web/openapi.json, with a believable flow:
 * analysis finishes after a few polls, ~12 parts (2 "Please check" + 1 suggested railing), a door
 * based size check, a material catalogue, estimates in the spirit of the real engine, renders
 * that recolour the sample house, and a tiny PDF report.
 *
 * Photo outcomes for trying the different screens: a file name containing "blurry" fails the
 * instant check, "angle" gives a warning, and "cat" or "reject" gives a "can't use this photo".
 */
import { delay, http, HttpResponse, type JsonBodyType } from "msw";
import type {
  AICallOut,
  Assignment,
  DesignOut,
  EstimateOut,
  JobOut,
  Label,
  Measurements,
  ProjectOut,
  ProjectSummary,
  QAResult,
  RegionIn,
  RegionOut,
  RegionsOut,
  RenderOut,
  ReportOut,
  ScaleConfirm,
} from "@/api/types";
import { copy } from "@/copy";
import {
  approvedRegions,
  db,
  DEFAULT_EXTRAS,
  type JobEffect,
  type MDesign,
  type MJob,
  type MProject,
  type MRender,
  nextId,
  now,
  pendingChecks,
  save,
  scaleFor,
} from "./db";
import { bbox, computeEstimate, hash } from "./estimate";
import { adviceFor, MATERIALS, MATERIALS_BY_ID } from "./materials";
import { type Fills, houseSvg, PHOTO_H, PHOTO_W, samplePhotoUrl, sampleRegions, svgDataUrl } from "./sampleHouse";

const isTest = import.meta.env.MODE === "test";
const latency = () => (isTest ? Promise.resolve() : delay(120 + Math.random() * 200));

function err(status: number, code: string, message: string) {
  return HttpResponse.json({ code, message }, { status });
}

const unauthorised = () => err(401, "unauthorised", copy.errors.signedOut);
const notFound = () => err(404, "not_found", copy.errors.notFound);

function json<T extends JsonBodyType>(body: T, status = 200) {
  save();
  return HttpResponse.json(body, { status });
}

function currentUser() {
  return db.users.find((u) => u.id === db.sessionUserId) ?? null;
}

function ownProject(id: string | readonly string[] | undefined): MProject | null {
  const user = currentUser();
  if (!user) return null;
  return db.projects.find((p) => p.id === id && p.ownerId === user.id) ?? null;
}

function ownDesign(id: string | readonly string[] | undefined): { d: MDesign; p: MProject } | null {
  const d = db.designs.find((x) => x.id === id);
  if (!d) return null;
  const p = ownProject(d.projectId);
  return p ? { d, p } : null;
}

// ------------------------------------------------------------------ AI trace

const MOCK_TRACE: Record<string, Pick<AICallOut, "stage" | "title" | "summary">> = {
  C1: {
    stage: "photo",
    title: "Checked your photo",
    summary: "Looks like an independent house with 2 floors, photographed from the front. The main door is visible.",
  },
  C2: {
    stage: "photo",
    title: "Found the parts of your house",
    summary: "Found 4 wall areas, 4 windows, 1 door, 1 balcony, 2 pillars and 1 railing.",
  },
  C3: { stage: "photo", title: "Double-checked each part", summary: "Confirmed 13 parts; 2 marked “Please check” for you." },
  C4: { stage: "materials", title: "Suggested materials", summary: "Top pick: Premium exterior emulsion for the main wall." },
  C5: { stage: "look", title: "Created your new look", summary: "Applied your chosen materials to the photo." },
  C6: { stage: "look", title: "Checked the new look", summary: "Everything looked right." },
};

function trace(p: MProject, step: string, provider: string, model: string, extra: Partial<AICallOut> = {}) {
  p.aiCalls.push({
    id: nextId("ai"),
    step,
    ...MOCK_TRACE[step],
    ok: true,
    attention: false,
    new_run: step === "C5",
    provider,
    model,
    latency_ms: Math.round(800 + Math.random() * 4000),
    cost_usd: Math.round(Math.random() * 400) / 100000,
    confidence: Math.round((0.7 + Math.random() * 0.29) * 100) / 100,
    attempts: 1,
    cached: false,
    created_at: now(),
    ...extra,
  });
}

// ------------------------------------------------------------------ jobs

function startJob(p: MProject, kind: JobOut["kind"], steps: string[], effect: JobEffect): MJob {
  const job: MJob = {
    id: nextId("job"),
    kind,
    status: "queued",
    step: steps[0] ?? null,
    error: null,
    steps,
    progress: 0,
    projectId: p.id,
    effect,
  };
  db.jobs.push(job);
  return job;
}

function jobOut(j: MJob): JobOut {
  return { id: j.id, kind: j.kind, status: j.status, step: j.step, error: j.error };
}

/** Move a job one step forward each time someone asks about it. */
function advance(job: MJob): void {
  if (job.status === "done" || job.status === "failed") return;
  job.progress += 1;
  if (job.progress < job.steps.length + 1) {
    job.status = "running";
    job.step = job.steps[Math.min(job.progress - 1, job.steps.length - 1)];
    return;
  }
  job.status = "done";
  job.step = null;
  const p = db.projects.find((x) => x.id === job.projectId);
  if (p) finish(job, p);
}

function finish(job: MJob, p: MProject): void {
  const e = job.effect;
  p.updated_at = now();
  if (e.type === "analysis") {
    p.activeJobId = null;
    trace(p, "C1", "jev", "jev-latest");
    trace(p, "C2", "gemini", "gemini-nano-banana-2.1");
    trace(p, "C3", "jev", "jev-latest");
    if (e.outcome === "reject") {
      p.stage = "photo_rejected";
      p.verdict = {
        status: "reject",
        issues: [
          {
            code: "not_residential",
            severity: "hard",
            message: "This doesn't look like the outside of a house. Please upload a photo of the front of your home.",
          },
        ],
      };
      return;
    }
    p.regions = sampleRegions().map((r) => ({ ...r, checked: false }));
    p.regionsVersion += 1;
    if (e.outcome === "warn") {
      p.stage = "photo_warning";
      p.verdict = {
        status: "warn",
        issues: [
          {
            code: "angled_view",
            severity: "warn",
            message: "The photo is taken at an angle, so sizes may be less accurate. A straight-on photo works best.",
          },
        ],
      };
    } else {
      p.stage = "regions_review";
      p.verdict = { status: "pass", issues: [] };
    }
  } else if (e.type === "advice") {
    p.adviceReady = true;
    trace(p, "C4", "jev", "jev-latest");
  } else if (e.type === "render") {
    const r = db.renders.find((x) => x.id === e.renderId);
    if (!r) return;
    const usesRailing = r.assignments.some((a) => p.regions.find((x) => x.id === a.region_id)?.label === "railing");
    const qa: QAResult = usesRailing
      ? {
          openings_preserved: 0.96,
          structure_preserved: 0.93,
          zones: { red: 0.9, green: 0.55 },
          passed: false,
          failed_checks: ["The railing may look slightly different from the material you chose."],
        }
      : { openings_preserved: 0.97, structure_preserved: 0.95, zones: { red: 0.92 }, passed: true, failed_checks: [] };
    r.status = "ready";
    r.qa = qa;
    r.attempts = usesRailing ? 3 : 1;
    r.image_url = svgDataUrl(houseSvg(fillsFor(p, r.assignments, r.user_note), r.user_note ? "#f59e0b" : "#fde68a"));
    trace(p, "C5", "gemini", "gemini-nano-banana-2.1", { attempts: r.attempts });
    trace(p, "C6", "jev", "jev-latest");
  } else if (e.type === "report") {
    const rep = db.reports.find((x) => x.id === e.reportId);
    if (rep) rep.ready = true;
  }
}

function fillsFor(p: MProject, assignments: Assignment[], note: string | null): Fills {
  const fills: Fills = {};
  for (const a of assignments) {
    const reg = p.regions.find((x) => x.id === a.region_id);
    const mat = MATERIALS_BY_ID[a.material_id];
    if (!reg || !mat) continue;
    let colour = a.color ?? mat.default_color ?? null;
    if (!colour) {
      colour =
        mat.category === "cladding"
          ? mat.id === "stone-slate"
            ? "#5b6270"
            : "#c9a77c"
          : mat.category === "railing"
            ? "#64748b"
            : mat.id === "hpl-wood"
              ? "#a0693f"
              : "#d9d4cc";
    }
    if (note && /warm/i.test(note)) colour = warmer(colour);
    fills[reg.label] = colour;
  }
  return fills;
}

function warmer(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, ((n >> 16) & 255) + 24);
  const g = (n >> 8) & 255;
  const b = Math.max(0, (n & 255) - 18);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

// ------------------------------------------------------------------ shapes

function projectOut(p: MProject): ProjectOut {
  const job = p.activeJobId ? db.jobs.find((j) => j.id === p.activeJobId) : null;
  return {
    id: p.id,
    name: p.name,
    stage: p.stage,
    measurements: p.measurements,
    photo: p.hasPhoto ? { id: `img-${p.id}`, url: samplePhotoUrl(), width: PHOTO_W, height: PHOTO_H } : null,
    verdict: p.verdict,
    verdict_overridden: p.verdict_overridden,
    regions_approved: p.regions_approved,
    scale_confirmed: p.scale_confirmed,
    active_job: job ? jobOut(job) : null,
    created_at: p.created_at,
    updated_at: p.updated_at,
  };
}

function regionsOut(p: MProject): RegionsOut {
  const regions: RegionOut[] = p.regions.map((r) => ({
    id: r.id,
    label: r.label,
    friendly_label: copy.labels[r.label],
    polygon: r.polygon,
    source: r.source,
    needs_check: r.needs_check,
    checked: r.checked,
    proposed: r.proposed,
    crop_url: null,
  }));
  return { regions, approved: p.regions_approved, pending_checks: pendingChecks(p.regions) };
}

function renderFp(p: MProject, assignments: Assignment[]): string {
  return hash(JSON.stringify([assignments, p.regionsVersion]));
}

function renderOut(r: MRender, p: MProject, d: MDesign): RenderOut {
  return {
    id: r.id,
    status: r.status,
    image_url: r.image_url,
    qa: r.qa,
    attempts: r.attempts,
    user_note: r.user_note,
    stale: r.fp !== renderFp(p, d.assignments),
    created_at: r.created_at,
  };
}

function latestRender(d: MDesign): MRender | null {
  const id = d.renderIds[d.renderIds.length - 1];
  return id ? (db.renders.find((r) => r.id === id) ?? null) : null;
}

function estimateFor(p: MProject, d: MDesign) {
  const scale = scaleFor(p);
  return computeEstimate({
    regions: approvedRegions(p),
    scale: {
      ft_per_px: scale.ft_per_px,
      method: scale.method,
      confidence: scale.confidence,
      facade_width_ft: scale.facade_width_ft,
      reference_box_px: scale.reference_box,
      explanation: scale.explanation,
      needs_measurement: scale.needs_measurement,
    },
    assignments: d.assignments,
    materials: MATERIALS_BY_ID,
    overrides: p.overrides,
    extras: p.extras,
    floors: p.measurements.floors ?? 2,
    scaleConfirmed: p.scale_confirmed,
    photoWarned: p.verdict_overridden,
  });
}

function latestFinal(d: MDesign) {
  const list = db.finals.filter((f) => f.designId === d.id);
  return list.length ? list[list.length - 1] : null;
}

function estimateOut(p: MProject, d: MDesign): EstimateOut {
  const estimate = estimateFor(p, d);
  const fin = latestFinal(d);
  return {
    id: fin?.id ?? null,
    version: fin?.version ?? null,
    finalised: !!fin,
    stale: fin ? fin.fingerprint !== estimate.fingerprint : false,
    estimate,
  };
}

function designOut(d: MDesign, p: MProject): DesignOut {
  const r = latestRender(d);
  const est = estimateOut(p, d);
  return {
    id: d.id,
    name: d.name,
    assignments: d.assignments,
    render: r ? renderOut(r, p, d) : null,
    estimate_stale: est.stale,
    estimate_finalised: est.finalised,
    created_at: d.created_at,
  };
}

/** Like the real backend: the first design is made when the parts are approved. */
function ensureFirstDesign(p: MProject): void {
  if (db.designs.some((d) => d.projectId === p.id)) return;
  db.designs.push({
    id: nextId("des"),
    projectId: p.id,
    name: copy.materials.defaultDesignName(1),
    assignments: [],
    created_at: now(),
    renderIds: [],
  });
}

function cleanMeasurements(m: Partial<Measurements> | undefined): Measurements {
  return {
    facade_width_ft: m?.facade_width_ft ?? null,
    facade_height_ft: m?.facade_height_ft ?? null,
    floors: m?.floors ?? null,
    reference_line: m?.reference_line ?? null,
  };
}

const PDF = `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 66>>stream
BT /F1 20 Tf 72 760 Td (Your home makeover report - demo) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
%%EOF`;

// ------------------------------------------------------------------ handlers

export const handlers = [
  http.get("/api/health", () => HttpResponse.json({ status: "ok" })),

  // auth
  http.post("/api/auth/register", async ({ request }) => {
    await latency();
    const body = (await request.json()) as { email?: string; password?: string };
    const email = (body.email ?? "").trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(email) || (body.password ?? "").length < 8) {
      return err(422, "invalid", copy.errors.invalidInput);
    }
    if (db.users.some((u) => u.email === email)) {
      return err(409, "email_taken", "An account with this email already exists. Try logging in instead.");
    }
    const user = { id: nextId("u"), email, password: body.password ?? "" };
    db.users.push(user);
    db.sessionUserId = user.id;
    return json({ id: user.id, email: user.email });
  }),
  http.post("/api/auth/login", async ({ request }) => {
    await latency();
    const body = (await request.json()) as { email?: string; password?: string };
    const email = (body.email ?? "").trim().toLowerCase();
    const user = db.users.find((u) => u.email === email && u.password === body.password);
    if (!user) return err(401, "bad_credentials", "That email and password don't match. Please try again.");
    db.sessionUserId = user.id;
    return json({ id: user.id, email: user.email });
  }),
  http.post("/api/auth/logout", () => {
    db.sessionUserId = null;
    save();
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("/api/auth/me", () => {
    const user = currentUser();
    return user ? HttpResponse.json({ id: user.id, email: user.email }) : unauthorised();
  }),

  // projects
  http.get("/api/projects", async () => {
    await latency();
    const user = currentUser();
    if (!user) return unauthorised();
    const list: ProjectSummary[] = db.projects
      .filter((p) => p.ownerId === user.id)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map((p) => ({
        id: p.id,
        name: p.name,
        stage: p.stage,
        thumbnail_url: p.hasPhoto ? samplePhotoUrl() : null,
        updated_at: p.updated_at,
        // mock simplification: any finished report counts as current
        report_ready: db.reports.some((r) => r.ready && db.designs.some((d) => d.id === r.designId && d.projectId === p.id)),
      }));
    return HttpResponse.json(list);
  }),
  http.post("/api/projects", async ({ request }) => {
    await latency();
    const user = currentUser();
    if (!user) return unauthorised();
    const body = (await request.json()) as { name?: string; measurements?: Measurements };
    if (!body.name?.trim()) return err(422, "invalid", copy.create.nameRequired);
    const p: MProject = {
      id: nextId("prj"),
      ownerId: user.id,
      name: body.name.trim(),
      stage: "upload",
      measurements: cleanMeasurements(body.measurements),
      hasPhoto: false,
      verdict: null,
      verdict_overridden: false,
      regions_approved: false,
      scale_confirmed: false,
      activeJobId: null,
      created_at: now(),
      updated_at: now(),
      regions: [],
      regionsVersion: 0,
      scaleSet: null,
      adviceReady: false,
      overrides: [],
      extras: { ...DEFAULT_EXTRAS },
      aiCalls: [],
    };
    db.projects.push(p);
    return json(projectOut(p), 201);
  }),
  http.get("/api/projects/:projectId", async ({ params }) => {
    await latency();
    if (!currentUser()) return unauthorised();
    const p = ownProject(params.projectId);
    return p ? HttpResponse.json(projectOut(p)) : notFound();
  }),
  http.patch("/api/projects/:projectId", async ({ params, request }) => {
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as { name?: string | null; measurements?: Measurements | null };
    if (body.name) p.name = body.name;
    if (body.measurements) p.measurements = cleanMeasurements(body.measurements);
    p.updated_at = now();
    return json(projectOut(p));
  }),
  http.delete("/api/projects/:projectId", ({ params }) => {
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    db.projects = db.projects.filter((x) => x.id !== p.id);
    db.designs = db.designs.filter((d) => d.projectId !== p.id);
    save();
    return new HttpResponse(null, { status: 204 });
  }),

  // photo
  http.post("/api/projects/:projectId/photo", async ({ params, request }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    let name = "photo.jpg";
    let type = "image/jpeg";
    try {
      const form = await Promise.race([
        request.formData(),
        new Promise<null>((resolve) => setTimeout(() => resolve(null), 100)),
      ]);
      const file = form?.get("file");
      if (file && typeof file === "object" && "name" in file) {
        name = (file as File).name || name;
        type = (file as File).type || type;
      }
    } catch {
      // Some test environments can't parse multipart bodies; use the defaults.
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(type)) {
      return err(422, "unsupported_type", "Please upload a JPEG, PNG or WebP photo.");
    }
    if (/blurry/i.test(name)) {
      return err(422, "blurry", "This photo is too blurry to measure. Hold the phone steady and try again in daylight.");
    }
    if (/tiny/i.test(name)) {
      return err(422, "too_small", "This photo is too small. Please use the original photo from your phone's camera.");
    }
    const outcome = /cat|reject/i.test(name) ? "reject" : /angle/i.test(name) ? "warn" : "pass";
    const job = startJob(p, "analyze_photo", [...copy.photo.progressSteps], { type: "analysis", outcome });
    // A new photo starts again from the parts of the house.
    p.hasPhoto = true;
    p.stage = "analyzing";
    p.activeJobId = job.id;
    p.verdict = null;
    p.verdict_overridden = false;
    p.regions = [];
    p.regions_approved = false;
    p.scale_confirmed = false;
    p.scaleSet = null;
    p.adviceReady = false;
    p.updated_at = now();
    return json({ project: projectOut(p), job_id: job.id }, 202);
  }),
  http.post("/api/projects/:projectId/photo/continue", ({ params }) => {
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    if (p.stage !== "photo_warning") return err(409, "not_waiting", "There is no photo warning to answer.");
    p.verdict_overridden = true;
    p.stage = "regions_review";
    p.updated_at = now();
    return json(projectOut(p));
  }),

  // regions
  http.get("/api/projects/:projectId/regions", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    return HttpResponse.json(regionsOut(p));
  }),
  http.put("/api/projects/:projectId/regions", async ({ params, request }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as { regions: RegionIn[] };
    const before = JSON.stringify(p.regions.map((r) => [r.id, r.label, r.polygon, r.proposed]));
    p.regions = body.regions.map((rin) => {
      const old = rin.id ? p.regions.find((r) => r.id === rin.id) : undefined;
      return {
        id: old?.id ?? nextId("part"),
        label: rin.label,
        polygon: rin.polygon,
        source: old?.source ?? "user",
        needs_check: old?.needs_check ?? false,
        checked: rin.checked,
        proposed: rin.proposed,
      };
    });
    const changed = before !== JSON.stringify(p.regions.map((r) => [r.id, r.label, r.polygon, r.proposed]));
    if (changed) {
      p.regionsVersion += 1;
      if (p.regions_approved) {
        p.regions_approved = false;
        p.stage = "regions_review";
      }
    }
    p.updated_at = now();
    return json(regionsOut(p));
  }),
  http.post("/api/projects/:projectId/regions/approve", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    if (pendingChecks(p.regions) > 0) {
      return err(409, "checks_pending", "Please answer every “Please check” question first.");
    }
    p.regions_approved = true;
    if (!p.adviceReady) startJob(p, "material_advice", ["Suggesting materials"], { type: "advice" });
    const scale = scaleFor(p);
    if (scale.confidence === "low") p.scale_confirmed = false;
    // A measurement typed in at the start is all we need: the size check is skipped.
    if (scale.confidence === "high") p.scale_confirmed = true;
    p.stage = p.scale_confirmed ? "designing" : "scale_review";
    ensureFirstDesign(p);
    p.updated_at = now();
    return json(projectOut(p));
  }),

  // scale
  http.get("/api/projects/:projectId/scale", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    if (!p.regions_approved) return err(409, "parts_not_confirmed", "Please confirm the parts of your house first.");
    return HttpResponse.json(scaleFor(p));
  }),
  http.post("/api/projects/:projectId/scale/confirm", async ({ params, request }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as ScaleConfirm;
    const current = scaleFor(p);
    const regs = approvedRegions(p).filter((r) => r.label === "wall" || r.label === "parapet");
    const box = regs.length ? bbox(regs.flatMap((r) => r.polygon)) : { x0: 0, y0: 0, x1: PHOTO_W, y1: PHOTO_H };
    const factors: number[] = [];
    if (body.facade_width_ft) factors.push(body.facade_width_ft / (box.x1 - box.x0));
    if (body.facade_height_ft) factors.push(body.facade_height_ft / (box.y1 - box.y0));
    if (body.reference_line) {
      const l = body.reference_line;
      const px = Math.hypot(l.x2 - l.x1, l.y2 - l.y1);
      if (px < 5) return err(422, "line_too_short", "The line is too short. Draw it along a longer edge.");
      factors.push(l.length_ft / px);
    }
    if (factors.length) {
      const f = Math.exp(factors.reduce((s, x) => s + Math.log(x), 0) / factors.length);
      p.scaleSet = { ft_per_px: f, method: "user_measurement", confidence: "high", facade_width_ft: (box.x1 - box.x0) * f };
      p.scale_confirmed = true;
    } else if (body.accept) {
      if (current.needs_measurement) {
        return err(409, "measurement_needed", "We need one measurement before we can continue.");
      }
      p.scale_confirmed = true;
    } else {
      return err(422, "invalid", copy.errors.invalidInput);
    }
    if (p.regions_approved) {
      p.stage = "designing";
      ensureFirstDesign(p);
    }
    p.updated_at = now();
    save();
    return HttpResponse.json(scaleFor(p));
  }),

  // materials
  http.get("/api/materials", async () => {
    await latency();
    return HttpResponse.json(MATERIALS);
  }),
  http.get("/api/projects/:projectId/material-advice", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    const job = [...db.jobs].reverse().find((j) => j.projectId === p.id && j.kind === "material_advice");
    if (job) advance(job);
    save();
    if (!p.adviceReady) return HttpResponse.json({ ready: false, advice: [] });
    return HttpResponse.json({
      ready: true,
      advice: approvedRegions(p)
        .filter((r) => r.label !== "window" && r.label !== "door")
        .map((r) => adviceFor(r.id, r.label as Label)),
    });
  }),

  // designs
  http.get("/api/projects/:projectId/designs", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    return HttpResponse.json(db.designs.filter((d) => d.projectId === p.id).map((d) => designOut(d, p)));
  }),
  http.post("/api/projects/:projectId/designs", async ({ params, request }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as { name: string; copy_from?: string | null };
    const source = body.copy_from ? db.designs.find((d) => d.id === body.copy_from) : undefined;
    const d: MDesign = {
      id: nextId("des"),
      projectId: p.id,
      name: body.name,
      assignments: source ? source.assignments.map((a) => ({ ...a })) : [],
      created_at: now(),
      renderIds: [],
    };
    db.designs.push(d);
    return json(designOut(d, p), 201);
  }),
  http.put("/api/designs/:designId/assignments", async ({ params, request }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as { assignments: Assignment[] };
    found.d.assignments = body.assignments;
    return json(designOut(found.d, found.p));
  }),
  http.patch("/api/designs/:designId", async ({ params, request }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as { name?: string };
    const name = (body.name ?? "").trim();
    if (!name || name.length > 80) return err(422, "invalid", copy.errors.invalidInput);
    found.d.name = name;
    return json(designOut(found.d, found.p));
  }),
  http.delete("/api/designs/:designId", ({ params }) => {
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    db.designs = db.designs.filter((d) => d.id !== found.d.id);
    save();
    return new HttpResponse(null, { status: 204 });
  }),

  // renders
  http.post("/api/designs/:designId/render", async ({ params, request }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    const { d, p } = found;
    const body = ((await request.json().catch(() => ({}))) ?? {}) as { note?: string | null };
    if (!d.assignments.length) return err(409, "no_materials", copy.materials.createLookDisabled);
    const r: MRender = {
      id: nextId("rnd"),
      designId: d.id,
      status: "queued",
      image_url: null,
      qa: null,
      attempts: 0,
      user_note: body.note?.trim() || null,
      fp: renderFp(p, d.assignments),
      assignments: d.assignments.map((a) => ({ ...a })),
      created_at: now(),
    };
    db.renders.push(r);
    d.renderIds.push(r.id);
    const job = startJob(p, "render", ["Creating your new look", "Double-checking your new look"], { type: "render", renderId: r.id });
    return json({ render: renderOut(r, p, d), job_id: job.id }, 202);
  }),
  http.get("/api/designs/:designId/render", async ({ params }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    const r = latestRender(found.d);
    if (!r) return HttpResponse.json(null);
    const job = db.jobs.find((j) => j.effect.type === "render" && j.effect.renderId === r.id);
    if (job) {
      advance(job);
      if (job.status === "running" && r.status === "queued") r.status = "running";
    }
    save();
    return HttpResponse.json(renderOut(r, found.p, found.d));
  }),
  http.post("/api/renders/:renderId/accept", async ({ params }) => {
    await latency();
    const r = db.renders.find((x) => x.id === params.renderId);
    const found = r ? ownDesign(r.designId) : null;
    if (!r || !found) return currentUser() ? notFound() : unauthorised();
    if (r.status !== "ready" && r.status !== "accepted") {
      return err(409, "not_ready", "Your makeover isn't ready yet.");
    }
    for (const other of db.renders.filter((x) => x.designId === r.designId && x.status === "accepted")) {
      other.status = "ready";
    }
    r.status = "accepted";
    return json(renderOut(r, found.p, found.d));
  }),

  // estimates
  http.get("/api/designs/:designId/estimate", async ({ params }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    return HttpResponse.json(estimateOut(found.p, found.d));
  }),
  http.post("/api/designs/:designId/estimate/finalise", async ({ params }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    const { d, p } = found;
    const estimate = estimateFor(p, d);
    if (estimate.provisional) {
      return err(409, "size_check_needed", "Please finish the size check before finalising your estimate.");
    }
    if (!estimate.lines.length) return err(409, "no_materials", copy.cost.noLines);
    const prev = latestFinal(d);
    if (!prev || prev.fingerprint !== estimate.fingerprint) {
      db.finals.push({
        id: nextId("est"),
        designId: d.id,
        version: (prev?.version ?? 0) + 1,
        fingerprint: estimate.fingerprint,
        estimate,
      });
    }
    return json(estimateOut(p, d));
  }),
  http.get("/api/projects/:projectId/rates", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    return HttpResponse.json({ overrides: p.overrides, extras: p.extras });
  }),
  http.put("/api/projects/:projectId/rates", async ({ params, request }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    const body = (await request.json()) as { overrides?: typeof p.overrides; extras?: typeof p.extras };
    p.overrides = (body.overrides ?? []).filter((o) => o.material_rate != null || o.labour_rate != null);
    p.extras = { ...DEFAULT_EXTRAS, ...(body.extras ?? {}) };
    p.updated_at = now();
    return json({ overrides: p.overrides, extras: p.extras });
  }),

  // reports
  http.post("/api/designs/:designId/report", async ({ params }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    const { d, p } = found;
    const r = latestRender(d);
    const est = estimateOut(p, d);
    if (!r || r.status !== "accepted" || r.fp !== renderFp(p, d.assignments) || !est.finalised || est.stale) {
      return err(409, "not_ready", "Accept your new look and finalise your estimate first.");
    }
    const rep = { id: nextId("rep"), designId: d.id, estimate_version: est.version ?? 1, renderId: r.id, created_at: now(), ready: false };
    db.reports.push(rep);
    const job = startJob(p, "report", ["Putting your report together"], { type: "report", reportId: rep.id });
    return json({ job_id: job.id }, 202);
  }),
  http.get("/api/designs/:designId/reports", async ({ params }) => {
    await latency();
    const found = ownDesign(params.designId);
    if (!found) return currentUser() ? notFound() : unauthorised();
    // newest first, like the real API
    const list: ReportOut[] = db.reports
      .filter((r) => r.designId === found.d.id && r.ready)
      .slice()
      .reverse()
      .map((r) => ({
        id: r.id,
        design_id: r.designId,
        estimate_version: r.estimate_version,
        render_id: r.renderId,
        download_url: `/api/reports/${r.id}/download`,
        created_at: r.created_at,
      }));
    return HttpResponse.json(list);
  }),
  http.get("/api/reports/:reportId/download", ({ params }) => {
    const rep = db.reports.find((r) => r.id === params.reportId);
    if (!rep || !ownDesign(rep.designId)) return notFound();
    return new HttpResponse(PDF, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="home-makeover-report.pdf"`,
      },
    });
  }),

  // jobs, images, trace
  http.get("/api/jobs/:jobId", async ({ params }) => {
    await latency();
    if (!currentUser()) return unauthorised();
    const job = db.jobs.find((j) => j.id === params.jobId);
    if (!job || !ownProject(job.projectId)) return notFound();
    advance(job);
    return json(jobOut(job));
  }),
  http.get("/api/images/:imageId", () =>
    new HttpResponse(houseSvg(), { headers: { "Content-Type": "image/svg+xml" } }),
  ),
  http.get("/api/projects/:projectId/ai-calls", async ({ params }) => {
    await latency();
    const p = ownProject(params.projectId);
    if (!p) return currentUser() ? notFound() : unauthorised();
    return HttpResponse.json(p.aiCalls);
  }),
];
