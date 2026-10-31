import { describe, expect, it } from "vitest";

import type { ReportOut } from "@/api/types";
import { currentReport } from "@/features/estimate/logic";

const rep = (id: string, version: number, renderId: string, at: string): ReportOut => ({
  id,
  design_id: "d1",
  estimate_version: version,
  render_id: renderId,
  download_url: `/api/reports/${id}/download`,
  created_at: at,
});

describe("currentReport", () => {
  const v1 = rep("old", 1, "look-1", "2026-10-25T13:30:00Z");
  const v2 = rep("new", 2, "look-2", "2026-10-25T14:39:00Z");

  it("picks the report for the current estimate version and accepted look, whatever the list order", () => {
    expect(currentReport([v2, v1], 2, "look-2")?.id).toBe("new"); // API order: newest first
    expect(currentReport([v1, v2], 2, "look-2")?.id).toBe("new");
  });

  it("never offers a report built from an older estimate or an older look", () => {
    expect(currentReport([v1], 2, "look-2")).toBeNull();
    expect(currentReport([v2], 2, "look-1")).toBeNull();
    expect(currentReport([v2], 3, "look-2")).toBeNull();
  });

  it("picks the newest of several matching reports", () => {
    const again = rep("again", 2, "look-2", "2026-10-25T15:00:00Z");
    expect(currentReport([v2, again, v1], 2, "look-2")?.id).toBe("again");
  });

  it("returns null when nothing is finalised or accepted yet", () => {
    expect(currentReport([v2], null, "look-2")).toBeNull();
    expect(currentReport([v2], 2, undefined)).toBeNull();
    expect(currentReport(undefined, 2, "look-2")).toBeNull();
  });
});

describe("reportFileName", () => {
  it("names the PDF after the project and estimate version", async () => {
    const { reportFileName } = await import("@/features/estimate/logic");
    expect(reportFileName("Meher Manzil", 2)).toBe("Meher Manzil - renovation report v2.pdf");
    expect(reportFileName('A/B: "x"?', 1)).toBe("A B x - renovation report v1.pdf");
    expect(reportFileName("  ", null)).toBe("home - renovation report.pdf");
  });
});
