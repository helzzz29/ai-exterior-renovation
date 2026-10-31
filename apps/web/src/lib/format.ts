import { copy } from "@/copy";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

const num1 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
const num2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

/** ₹ with Indian digit grouping, no decimals: 141086 -> "₹1,41,086". */
export function formatINR(value: number): string {
  return inr.format(Math.round(value));
}

/** Round a rupee figure to a friendly "about" value: nearest 1,000 from 10,000 up, else 100. */
export function roundFriendly(value: number): number {
  const step = Math.abs(value) >= 10000 ? 1000 : 100;
  return Math.round(value / step) * step;
}

/** "About ₹41,000 (likely between ₹33,000 and ₹49,000)" */
export function formatTotalRange(total: number, low: number, high: number): string {
  return copy.cost.total(
    formatINR(roundFriendly(total)),
    formatINR(roundFriendly(low)),
    formatINR(roundFriendly(high)),
  );
}

export function formatNumber(value: number, decimals: 1 | 2 = 1): string {
  return (decimals === 1 ? num1 : num2).format(value);
}

export function formatFeet(value: number): string {
  return `${formatNumber(value)} ${copy.common.ft}`;
}

const UNIT_WORDS: Record<string, [string, string]> = {
  litre: ["litre", "litres"],
  kg: ["kg", "kg"],
  piece: ["piece", "pieces"],
  sqft: ["sq ft", "sq ft"],
  sheet: ["sheet", "sheets"],
  rft: ["running ft", "running ft"],
  box: ["box", "boxes"],
};

export function unitWord(unit: string, amount = 2): string {
  const w = UNIT_WORDS[unit];
  if (!w) return unit;
  return amount === 1 ? w[0] : w[1];
}

export function formatQuantity(value: number, unit: string): string {
  return `${formatNumber(value, 2)} ${unitWord(unit, value)}`;
}

/** "3 days ago" style relative date, in plain words. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const diffMs = now.getTime() - then.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (Number.isNaN(minutes)) return "";
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} ${days === 1 ? "day" : "days"} ago`;
  return then.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
