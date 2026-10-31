import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { expect } from "vitest";
import type {
  DesignOut,
  JobOut,
  MaterialAdviceOut,
  Measurements,
  PhotoUploadResult,
  ProjectOut,
  RegionsOut,
  RenderOut,
  RenderStarted,
} from "@/api/types";
import { App } from "@/App";
import { AppProviders, makeQueryClient } from "@/AppProviders";
import { db } from "@/mocks/db";
import { FORBIDDEN } from "./forbidden";

export const BASE = "http://localhost:5173";

export async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${await res.text()}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : null) as T;
}

export function login() {
  db.sessionUserId = "u-demo";
}

async function until<T>(fn: () => Promise<T>, done: (v: T) => boolean): Promise<T> {
  for (let i = 0; i < 30; i++) {
    const v = await fn();
    if (done(v)) return v;
  }
  throw new Error("never finished");
}

export type SeedStage = "upload" | "regions" | "scale" | "designing" | "assigned" | "rendered" | "accepted";
const ORDER: SeedStage[] = ["upload", "regions", "scale", "designing", "assigned", "rendered", "accepted"];

export interface SeedOptions {
  measurements?: Measurements;
  photoName?: string;
  removeDoor?: boolean;
  railing?: boolean;
}

/** Drive the mock API to a given point in the journey and return the ids. */
export async function seed(stage: SeedStage, opts: SeedOptions = {}) {
  login();
  const at = (s: SeedStage) => ORDER.indexOf(stage) >= ORDER.indexOf(s);
  const project = await call<ProjectOut>("POST", "/api/projects", {
    name: "Test house",
    measurements: opts.measurements ?? {},
  });
  const id = project.id;
  let designId = "";
  if (!at("regions")) return { projectId: id, designId };

  const form = new FormData();
  form.append("file", new File(["x"], opts.photoName ?? "house.jpg", { type: "image/jpeg" }));
  const up = await call<PhotoUploadResult>("POST", `/api/projects/${id}/photo`, form);
  await until(() => call<JobOut>("GET", `/api/jobs/${up.job_id}`), (j) => j.status === "done");
  if (!at("scale")) return { projectId: id, designId };

  const regions = await call<RegionsOut>("GET", `/api/projects/${id}/regions`);
  await call("PUT", `/api/projects/${id}/regions`, {
    regions: regions.regions
      .filter((r) => !(opts.removeDoor && r.label === "door"))
      .map((r) => ({ id: r.id, label: r.label, polygon: r.polygon, checked: true, proposed: false })),
  });
  await call("POST", `/api/projects/${id}/regions/approve`);
  if (!at("designing")) return { projectId: id, designId };

  const p = await call<ProjectOut>("GET", `/api/projects/${id}`);
  if (p.stage === "scale_review") await call("POST", `/api/projects/${id}/scale/confirm`, { accept: true });
  await until(() => call<MaterialAdviceOut>("GET", `/api/projects/${id}/material-advice`), (a) => a.ready);
  // The server makes the first design when the parts are approved.
  const designs = await call<DesignOut[]>("GET", `/api/projects/${id}/designs`);
  designId = designs[0].id;
  if (!at("assigned")) return { projectId: id, designId };

  const assignments = regions.regions
    .filter((r) => r.label === "wall" || r.label === "pillar" || (opts.railing && r.label === "railing"))
    .map((r) => ({
      region_id: r.id,
      material_id: r.label === "wall" ? "paint-emulsion" : r.label === "pillar" ? "stone-natural" : "railing-glass",
      color: r.label === "wall" ? "#e9dcc0" : null,
    }));
  await call("PUT", `/api/designs/${designId}/assignments`, { assignments });
  if (!at("rendered")) return { projectId: id, designId };

  const started = await call<RenderStarted>("POST", `/api/designs/${designId}/render`, { note: null });
  await until(() => call<RenderOut>("GET", `/api/designs/${designId}/render`), (r) => r.status === "ready");
  if (!at("accepted")) return { projectId: id, designId };
  await call("POST", `/api/renders/${started.render.id}/accept`);
  return { projectId: id, designId };
}

function LocationProbe() {
  const l = useLocation();
  return <div data-testid="location">{`${l.pathname}${l.search}`}</div>;
}

export function renderApp(path: string) {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false, refetchOnWindowFocus: false } });
  const user = userEvent.setup();
  const utils = render(
    <AppProviders client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </AppProviders>,
  );
  return { ...utils, user, client };
}

export function location(): string {
  return screen.getByTestId("location").textContent ?? "";
}


/** The main interface never shows technical words (the collapsed trace panel is not rendered). */
export function expectPlainLanguage(root: HTMLElement = document.body) {
  const text = root.textContent ?? "";
  expect(text).not.toMatch(FORBIDDEN);
  expect(text).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
}
