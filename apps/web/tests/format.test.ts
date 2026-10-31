import { describe, expect, it } from "vitest";
import { formatINR, formatQuantity, formatRelative, formatTotalRange, roundFriendly, unitWord } from "@/lib/format";

describe("money formatting", () => {
  it("uses Indian digit grouping", () => {
    expect(formatINR(41086)).toBe("₹41,086");
    expect(formatINR(141086)).toBe("₹1,41,086");
    expect(formatINR(12345678.4)).toBe("₹1,23,45,678");
  });

  it("rounds to friendly figures", () => {
    expect(roundFriendly(41086)).toBe(41000);
    expect(roundFriendly(32869)).toBe(33000);
    expect(roundFriendly(9849)).toBe(9800);
  });

  it("writes the total with its likely range (worked example)", () => {
    expect(formatTotalRange(41086, 32900, 49300)).toBe("About ₹41,000 (likely between ₹33,000 and ₹49,000)");
  });
});

describe("units and dates", () => {
  it("uses plain unit words", () => {
    expect(unitWord("rft")).toBe("running ft");
    expect(unitWord("litre", 1)).toBe("litre");
    expect(formatQuantity(8, "litre")).toBe("8 litres");
  });

  it("describes time in words", () => {
    const now = new Date("2026-01-10T12:00:00Z");
    expect(formatRelative("2026-01-10T11:59:40Z", now)).toBe("just now");
    expect(formatRelative("2026-01-10T09:00:00Z", now)).toBe("3 hours ago");
    expect(formatRelative("2026-01-08T12:00:00Z", now)).toBe("2 days ago");
  });
});
