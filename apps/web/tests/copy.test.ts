import { describe, expect, it } from "vitest";
import { copy } from "@/copy";
import { FORBIDDEN } from "./forbidden";

/** Collect every user-facing string in the table, calling templates with sample values. */
function strings(value: unknown, path = "copy"): [string, string][] {
  if (typeof value === "string") return [[path, value]];
  if (typeof value === "function") {
    const fn = value as (...args: unknown[]) => unknown;
    const words = Array.from({ length: fn.length }, (_, i) => (i === 0 ? "Pillar" : "sample"));
    const out: [string, string][] = strings(fn(...words), `${path}()`);
    try {
      const numbers = Array.from({ length: fn.length }, (_, i) => i + 1);
      out.push(...strings(fn(...numbers), `${path}(numbers)`));
    } catch {
      // template only takes text
    }
    return out;
  }
  if (Array.isArray(value)) return value.flatMap((v, i) => strings(v, `${path}[${i}]`));
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([k, v]) => strings(v, `${path}.${k}`));
  }
  return [];
}

describe("copy table", () => {
  const all = strings(copy);

  it("has a good number of strings", () => {
    expect(all.length).toBeGreaterThan(200);
  });

  it.each(["region", "confidence", "Gemini", "Jev", "polygon", "job"])("never says “%s”", (word) => {
    const re = new RegExp(`\\b${word}s?\\b`, "i");
    const hits = all.filter(([, s]) => re.test(s)).map(([p]) => p);
    expect(hits).toEqual([]);
  });

  it("matches the shared forbidden-words check", () => {
    expect(all.filter(([, s]) => FORBIDDEN.test(s))).toEqual([]);
  });

  it("shows no percentages outside the trace panel", () => {
    const hits = all.filter(([p, s]) => !p.startsWith("copy.trace") && /\d+\s?%/.test(s));
    expect(hits).toEqual([]);
  });

  it("sets honest waiting times", () => {
    expect(copy.photo.analysingIntro).toContain("This usually takes about half a minute.");
    expect(copy.look.creatingBody).toContain(
      "This can take one to three minutes while we create and double-check your new look.",
    );
    expect(copy.parts.groupRow("Main wall", 11)).toBe("Main wall · 11");
  });

  it("names the next design step for what it does", () => {
    // "Next steps" opens the same design again; it never makes a new one.
    expect(copy.next.anotherDesign).toBe("Change this design");
    expect(copy.stale.estimate).not.toMatch(/Prices or sizes changed/);
  });

  it("uses the plain names for parts", () => {
    expect(copy.labels.parapet).toBe("Top wall edge (parapet)");
    expect(copy.parts.isThisA("Pillar")).toBe("Is this a pillar?");
    expect(copy.parts.proposedQuestion("Railing")).toBe("Did we find a railing here?");
    expect(copy.parts.unsureBanner(2)).toBe("We're not completely sure about 2 parts. Tap each one to confirm.");
    expect(copy.parts.leftToCheck(2)).toBe("2 left to check");
    expect(copy.parts.suggestion).not.toBe(copy.parts.pleaseCheck);
  });
});
