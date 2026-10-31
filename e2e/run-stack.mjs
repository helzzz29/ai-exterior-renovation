#!/usr/bin/env node
// Boots the whole app for the end-to-end tests: database prepare + API + worker + web.
// Playwright starts this as its webServer; it can also be run by hand: `pnpm stack`.
//
// Always uses the fake AI provider and a throwaway storage folder: no real AI calls.
// Ports (override with env): API 8010, web 5180. Database: reno_e2e on the dev server (5433).

import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const apiDir = path.join(root, "apps", "api");
const webDir = path.join(root, "apps", "web");

const API_PORT = process.env.E2E_API_PORT ?? "8010";
const WEB_PORT = process.env.E2E_WEB_PORT ?? "5180";
const storage = process.env.E2E_STORAGE_ROOT ?? mkdtempSync(path.join(tmpdir(), "reno-e2e-"));

const env = {
  ...process.env,
  AI_PROVIDER: "fake",
  GEMINI_API_KEY: "",
  JEV_API_KEY: "",
  DATABASE_URL: process.env.E2E_DATABASE_URL ?? "postgresql+asyncpg://reno:reno@localhost:5433/reno_e2e",
  STORAGE_ROOT: storage,
  E2E_API_PORT: API_PORT,
  VITE_API_TARGET: `http://127.0.0.1:${API_PORT}`,
  LOG_JSON: "false",
  LOG_LEVEL: "WARNING",
  PYTHONUNBUFFERED: "1",
};

const children = [];
const isWin = process.platform === "win32";

function run(name, cmd, args, cwd, { wait = false } = {}) {
  const child = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"], shell: isWin });
  const tag = (chunk) =>
    chunk
      .toString()
      .split(/\r?\n/)
      .filter(Boolean)
      .forEach((l) => console.log(`[${name}] ${l}`));
  child.stdout.on("data", tag);
  child.stderr.on("data", tag);
  if (wait) {
    return new Promise((resolve, reject) =>
      child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${name} exited with ${code}`)))),
    );
  }
  children.push(child);
  child.on("exit", (code) => {
    console.log(`[${name}] exited (${code})`);
    shutdown(1);
  });
  return child;
}

let stopping = false;
function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const c of children) {
    if (c.exitCode !== null) continue;
    if (isWin) spawn("taskkill", ["/pid", String(c.pid), "/T", "/F"], { stdio: "ignore" });
    else c.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 500);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

async function waitFor(url, ms = 90_000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`timed out waiting for ${url}`);
}

console.log(`[stack] storage: ${storage}`);
await run("prepare", "uv", ["run", "python", "../../e2e/scripts/stack.py", "prepare"], apiDir, { wait: true });
run("api", "uv", ["run", "python", "../../e2e/scripts/stack.py", "api"], apiDir);
run("worker", "uv", ["run", "python", "-m", "app.jobs.worker"], apiDir);
await waitFor(`http://127.0.0.1:${API_PORT}/api/health`);
console.log("[stack] api ready");
run("web", "pnpm", ["exec", "vite", "--port", WEB_PORT, "--strictPort"], webDir);
await waitFor(`http://localhost:${WEB_PORT}/`);
console.log(`[stack] ready: http://localhost:${WEB_PORT}`);
