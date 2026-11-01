/**
 * Pure state logic for the "Spot the sections" editor (G2). The canvas and the cards only
 * dispatch actions; every rule (what counts as checked, when Continue unlocks, what is saved)
 * lives here so it can be unit-tested without a canvas.
 */
import type { Label, Point, RegionIn, RegionOut } from "@/api/types";

export type Tool = "select" | "move" | "add";

export interface DraftPart {
  /** Stable key for React and the editor: the saved id, or a temporary one for new parts. */
  key: string;
  id: string | null;
  label: Label;
  polygon: Point[];
  source: RegionOut["source"];
  needsCheck: boolean;
  checked: boolean;
  proposed: boolean;
}

export interface EditorState {
  parts: DraftPart[];
  selectedKey: string | null;
  tool: Tool;
  /** Points of a part being drawn with "Add a part". */
  drawing: Point[];
  /** A finished outline waiting for "What is this part?". */
  pendingShape: Point[] | null;
  /** Increases with every change that must be saved. */
  version: number;
  seq: number;
}

export type EditorAction =
  | { type: "load"; regions: RegionOut[] }
  | { type: "select"; key: string | null }
  | { type: "setTool"; tool: Tool }
  | { type: "confirm"; key: string }
  | { type: "relabel"; key: string; label: Label }
  | { type: "remove"; key: string }
  | { type: "acceptProposed"; key: string }
  | { type: "rejectProposed"; key: string }
  | { type: "movePoint"; key: string; index: number; point: Point }
  | { type: "addPoint"; point: Point; closeTolerance?: number }
  | { type: "addBox"; width: number; height: number }
  | { type: "finishShape" }
  | { type: "cancelShape" }
  | { type: "labelNewPart"; label: Label };

export const initialEditorState: EditorState = {
  parts: [],
  selectedKey: null,
  tool: "select",
  drawing: [],
  pendingShape: null,
  version: 0,
  seq: 0,
};

function fromRegion(r: RegionOut): DraftPart {
  return {
    key: r.id,
    id: r.id,
    label: r.label,
    polygon: r.polygon.map(([x, y]) => [x, y] as Point),
    source: r.source,
    needsCheck: r.needs_check,
    checked: r.checked,
    proposed: r.proposed,
  };
}

/** A part still waiting for an answer. Same rule as the server's `pending_checks`. */
export function isPending(p: DraftPart): boolean {
  return (p.needsCheck && !p.checked) || p.proposed;
}

function update(state: EditorState, key: string, fn: (p: DraftPart) => DraftPart): EditorState {
  let changed = false;
  const parts = state.parts.map((p) => {
    if (p.key !== key) return p;
    changed = true;
    return fn(p);
  });
  return changed ? { ...state, parts, version: state.version + 1 } : state;
}

function samePolygon(a: Point[], b: Point[]): boolean {
  return a.length === b.length && a.every(([x, y], i) => x === b[i][0] && y === b[i][1]);
}

function dist(a: Point, b: Point): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function finish(state: EditorState): EditorState {
  if (state.drawing.length < 3) return state;
  return { ...state, pendingShape: state.drawing, drawing: [] };
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "load": {
      const parts = action.regions.map(fromRegion);
      let selectedKey = parts.some((p) => p.key === state.selectedKey) ? state.selectedKey : null;
      // A part added on this screen comes back from the save with its new id: keep it selected.
      const before = state.parts.find((p) => p.key === state.selectedKey);
      if (!selectedKey && before && before.id === null) {
        const same = parts.find((p) => p.label === before.label && samePolygon(p.polygon, before.polygon));
        selectedKey = same?.key ?? null;
      }
      return { ...state, parts, selectedKey };
    }
    case "select":
      return { ...state, selectedKey: action.key };
    case "setTool":
      return { ...state, tool: action.tool, drawing: [], pendingShape: null };
    case "confirm":
      return update(state, action.key, (p) => ({ ...p, checked: true, proposed: false }));
    case "relabel":
      return update(state, action.key, (p) => ({
        ...p,
        label: action.label,
        checked: true,
        proposed: false,
      }));
    case "acceptProposed":
      return update(state, action.key, (p) => ({ ...p, proposed: false, checked: true }));
    case "remove":
    case "rejectProposed": {
      if (!state.parts.some((p) => p.key === action.key)) return state;
      return {
        ...state,
        parts: state.parts.filter((p) => p.key !== action.key),
        selectedKey: state.selectedKey === action.key ? null : state.selectedKey,
        version: state.version + 1,
      };
    }
    case "movePoint":
      return update(state, action.key, (p) => {
        if (action.index < 0 || action.index >= p.polygon.length) return p;
        const polygon = p.polygon.slice();
        polygon[action.index] = action.point;
        return { ...p, polygon };
      });
    case "addPoint": {
      if (state.tool !== "add" || state.pendingShape) return state;
      const tol = action.closeTolerance ?? 0;
      const n = state.drawing.length;
      if (n >= 3 && tol > 0 && dist(action.point, state.drawing[0]) <= tol) {
        return finish(state);
      }
      // A second tap on the corner just placed finishes the shape (a "double tap" judged by
      // place, not by time, so two quick taps far apart never close it by accident). With fewer
      // than three corners it is just ignored, so no corner is placed twice.
      if (n >= 1 && tol > 0 && dist(action.point, state.drawing[n - 1]) <= tol) {
        return n >= 3 ? finish(state) : state;
      }
      return { ...state, drawing: [...state.drawing, action.point] };
    }
    case "addBox": {
      // Keyboard route for "Add a part": a box in the middle of the photo, adjusted afterwards.
      if (state.tool !== "add" || state.pendingShape) return state;
      const w = Math.round(action.width * 0.3);
      const h = Math.round(action.height * 0.3);
      const x0 = Math.round((action.width - w) / 2);
      const y0 = Math.round((action.height - h) / 2);
      const box: Point[] = [
        [x0, y0],
        [x0 + w, y0],
        [x0 + w, y0 + h],
        [x0, y0 + h],
      ];
      return { ...state, drawing: [], pendingShape: box };
    }
    case "finishShape":
      return finish(state);
    case "cancelShape":
      return { ...state, drawing: [], pendingShape: null };
    case "labelNewPart": {
      if (!state.pendingShape) return state;
      const seq = state.seq + 1;
      const part: DraftPart = {
        key: `new-${seq}`,
        id: null,
        label: action.label,
        polygon: state.pendingShape,
        source: "user",
        needsCheck: false,
        checked: false,
        proposed: false,
      };
      return {
        ...state,
        parts: [...state.parts, part],
        pendingShape: null,
        drawing: [],
        tool: "select",
        selectedKey: part.key,
        seq,
        version: state.version + 1,
      };
    }
  }
}

// ------------------------------------------------------------------ selectors

export function pendingCount(state: EditorState): number {
  return state.parts.filter(isPending).length;
}

export function canContinue(state: EditorState): boolean {
  return continueBlocker(state) === null;
}

/** Why "Looks good, continue" is not available yet: a part being drawn, or unanswered questions. */
export function continueBlocker(state: EditorState): "drawing" | "pending" | null {
  if (state.pendingShape !== null || state.drawing.length > 0) return "drawing";
  if (pendingCount(state) > 0) return "pending";
  return null;
}

export function pendingParts(state: EditorState): DraftPart[] {
  return state.parts.filter(isPending);
}

export function selectedPart(state: EditorState): DraftPart | null {
  return state.parts.find((p) => p.key === state.selectedKey) ?? null;
}

/** Body for `PUT /projects/{id}/regions`. */
export function toRegionsIn(state: EditorState): RegionIn[] {
  return state.parts.map((p) => ({
    id: p.id,
    label: p.label,
    polygon: p.polygon,
    checked: p.checked,
    proposed: p.proposed,
  }));
}
