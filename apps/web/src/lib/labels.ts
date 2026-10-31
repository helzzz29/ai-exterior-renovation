import {
  Columns3,
  DoorOpen,
  Fence,
  Home,
  LayoutPanelTop,
  type LucideIcon,
  PanelTop,
  RectangleHorizontal,
  Square,
  Warehouse,
} from "lucide-react";
import type { Label } from "@/api/types";
import { copy } from "@/copy";

export const LABELS: Label[] = [
  "wall",
  "window",
  "door",
  "balcony",
  "pillar",
  "parapet",
  "railing",
  "gate",
  "roof_edge",
];

/** Openings are never priced and never restyled. */
export const OPENING_LABELS: ReadonlySet<Label> = new Set<Label>(["window", "door"]);

interface LabelStyle {
  name: string;
  colour: string;
  icon: LucideIcon;
}

export const LABEL_STYLES: Record<Label, LabelStyle> = {
  wall: { name: copy.labels.wall, colour: "#2563eb", icon: Home },
  window: { name: copy.labels.window, colour: "#06b6d4", icon: Square },
  door: { name: copy.labels.door, colour: "#a855f7", icon: DoorOpen },
  balcony: { name: copy.labels.balcony, colour: "#16a34a", icon: LayoutPanelTop },
  pillar: { name: copy.labels.pillar, colour: "#db2777", icon: Columns3 },
  parapet: { name: copy.labels.parapet, colour: "#ea580c", icon: PanelTop },
  railing: { name: copy.labels.railing, colour: "#0d9488", icon: Fence },
  gate: { name: copy.labels.gate, colour: "#4f46e5", icon: Warehouse },
  roof_edge: { name: copy.labels.roof_edge, colour: "#b91c1c", icon: RectangleHorizontal },
};

/** Amber used for every "Please check" outline. */
export const CHECK_COLOUR = "#f59e0b";

export function friendlyName(label: Label): string {
  return LABEL_STYLES[label]?.name ?? label;
}

export function labelColour(label: Label): string {
  return LABEL_STYLES[label]?.colour ?? "#64748b";
}
