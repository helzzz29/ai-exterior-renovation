import { describe, expect, it } from "vitest";

import type { AICallOut } from "@/api/types";
import { copy } from "@/copy";
import { groupTrace } from "@/features/trace/TracePanel";

let n = 0;
const call = (step: string, stage: AICallOut["stage"], extra: Partial<AICallOut> = {}): AICallOut => ({
  id: `c${++n}`,
  step,
  stage,
  title: `Title ${step}`,
  summary: `Summary ${step}`,
  ok: true,
  attention: false,
  new_run: false,
  provider: "jev",
  model: "jev-latest",
  latency_ms: 1400,
  cost_usd: null,
  confidence: null,
  attempts: 1,
  cached: false,
  created_at: "2026-10-25T13:00:00Z",
  ...extra,
});

describe("groupTrace", () => {
  it("groups consecutive calls by stage, in order", () => {
    const groups = groupTrace([
      call("C1", "photo"),
      call("C2", "photo"),
      call("C3", "photo"),
      call("C4", "materials"),
      call("C5", "look"),
      call("C6", "look"),
    ]);
    expect(groups.map((g) => g.stage)).toEqual(["photo", "materials", "look"]);
    expect(groups[0].steps.map((s) => s.title)).toEqual(["Title C1", "Title C2", "Title C3"]);
  });

  it("folds failed calls into the next successful call of the same step", () => {
    const groups = groupTrace([
      call("C4", "materials", { ok: false }),
      call("C4", "materials", { ok: false }),
      call("C4", "materials"),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].steps).toHaveLength(1);
    expect(groups[0].steps[0].retries).toBe(2);
  });

  it("keeps the attention flag so problems are not shown with a green tick", () => {
    const [g] = groupTrace([call("C6", "look", { attention: true, summary: "Windows or doors may look different." })]);
    expect(g.steps[0].attention).toBe(true);
  });

  it("splits separate new-look runs and numbers them", () => {
    const groups = groupTrace([
      call("C5", "look", { new_run: true }),
      call("C6", "look"),
      call("C5", "look"),
      call("C6", "look"),
      call("C5", "look", { new_run: true }),
      call("C6", "look"),
    ]);
    expect(groups.map((g) => [g.stage, g.run, g.steps.length])).toEqual([
      ["look", 1, 4],
      ["look", 2, 2],
    ]);
    expect(copy.trace.again(2)).toBe("(2nd time)");
  });

  it("starts a new group when a stage happens again (e.g. a second new look)", () => {
    const groups = groupTrace([call("C5", "look"), call("C4", "materials"), call("C5", "look")]);
    expect(groups.map((g) => g.stage)).toEqual(["look", "materials", "look"]);
  });

  it("never shows internal step codes in the plain-language copy", () => {
    const words = [copy.trace.intro, ...Object.values(copy.trace.stages), copy.trace.retried(2), copy.trace.reused];
    for (const w of words) expect(w).not.toMatch(/\bC[1-6]\b/);
    expect(copy.trace.retried(2)).toBe("worked on the 2nd try");
    expect(copy.trace.retried(3)).toBe("worked on the 3rd try");
  });
});
