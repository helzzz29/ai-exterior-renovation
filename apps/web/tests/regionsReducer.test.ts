import { describe, expect, it } from "vitest";
import type { RegionOut } from "@/api/types";
import {
  canContinue,
  continueBlocker,
  editorReducer,
  type EditorState,
  initialEditorState,
  pendingCount,
  selectedPart,
  toRegionsIn,
} from "@/features/regions/reducer";

const sq = (x: number): [number, number][] => [
  [x, 0],
  [x + 10, 0],
  [x + 10, 10],
  [x, 10],
];

function region(id: string, extra: Partial<RegionOut> = {}): RegionOut {
  return {
    id,
    label: "wall",
    friendly_label: "Main wall",
    polygon: sq(0),
    source: "gemini",
    needs_check: false,
    checked: false,
    proposed: false,
    crop_url: null,
    ...extra,
  };
}

function loaded(): EditorState {
  return editorReducer(initialEditorState, {
    type: "load",
    regions: [
      region("wall"),
      region("pillar", { label: "pillar", needs_check: true, polygon: sq(20) }),
      region("balcony", { label: "balcony", needs_check: true, polygon: sq(40) }),
      region("railing", { label: "railing", proposed: true, source: "jev_box", polygon: sq(60) }),
    ],
  });
}

describe("region editor reducer", () => {
  it("counts the questions to answer and blocks Continue", () => {
    const s = loaded();
    expect(pendingCount(s)).toBe(3);
    expect(canContinue(s)).toBe(false);
    expect(continueBlocker(s)).toBe("pending");
  });

  it("confirm marks a part as checked", () => {
    const s = editorReducer(loaded(), { type: "confirm", key: "pillar" });
    expect(s.parts.find((p) => p.key === "pillar")?.checked).toBe(true);
    expect(pendingCount(s)).toBe(2);
    expect(s.version).toBe(1);
  });

  it("relabel changes what the part is and answers the question", () => {
    const s = editorReducer(loaded(), { type: "relabel", key: "pillar", label: "wall" });
    const p = s.parts.find((x) => x.key === "pillar")!;
    expect(p.label).toBe("wall");
    expect(p.checked).toBe(true);
    expect(pendingCount(s)).toBe(2);
  });

  it("remove deletes the part, clears the selection and counts as answered", () => {
    let s = editorReducer(loaded(), { type: "select", key: "balcony" });
    expect(selectedPart(s)?.key).toBe("balcony");
    s = editorReducer(s, { type: "remove", key: "balcony" });
    expect(s.parts.map((p) => p.key)).not.toContain("balcony");
    expect(s.selectedKey).toBeNull();
    expect(pendingCount(s)).toBe(2);
  });

  it("accepting a suggested part keeps it; rejecting removes it", () => {
    const kept = editorReducer(loaded(), { type: "acceptProposed", key: "railing" });
    expect(kept.parts.find((p) => p.key === "railing")?.proposed).toBe(false);
    const rejected = editorReducer(loaded(), { type: "rejectProposed", key: "railing" });
    expect(rejected.parts.find((p) => p.key === "railing")).toBeUndefined();
    expect(pendingCount(kept)).toBe(2);
    expect(pendingCount(rejected)).toBe(2);
  });

  it("enables Continue once every question is answered", () => {
    let s = loaded();
    s = editorReducer(s, { type: "confirm", key: "pillar" });
    s = editorReducer(s, { type: "relabel", key: "balcony", label: "parapet" });
    expect(canContinue(s)).toBe(false);
    s = editorReducer(s, { type: "acceptProposed", key: "railing" });
    expect(canContinue(s)).toBe(true);
    expect(continueBlocker(s)).toBeNull();
  });

  it("moves one corner of a part", () => {
    const s = editorReducer(loaded(), { type: "movePoint", key: "wall", index: 2, point: [15, 18] });
    expect(s.parts[0].polygon[2]).toEqual([15, 18]);
    expect(s.parts[0].polygon[0]).toEqual([0, 0]);
    const same = editorReducer(s, { type: "movePoint", key: "wall", index: 9, point: [1, 1] });
    expect(same.parts[0].polygon).toEqual(s.parts[0].polygon);
  });

  it("adds a part: points, close on the first point, then choose what it is", () => {
    let s = editorReducer(loaded(), { type: "setTool", tool: "add" });
    s = editorReducer(s, { type: "addPoint", point: [100, 100], closeTolerance: 5 });
    s = editorReducer(s, { type: "addPoint", point: [200, 100], closeTolerance: 5 });
    s = editorReducer(s, { type: "addPoint", point: [200, 200], closeTolerance: 5 });
    expect(s.drawing).toHaveLength(3);
    expect(canContinue(s)).toBe(false);
    s = editorReducer(s, { type: "addPoint", point: [102, 101], closeTolerance: 5 });
    expect(s.pendingShape).toHaveLength(3);
    s = editorReducer(s, { type: "labelNewPart", label: "gate" });
    const added = s.parts[s.parts.length - 1];
    expect(added).toMatchObject({ id: null, label: "gate", source: "user" });
    expect(s.tool).toBe("select");
    expect(s.selectedKey).toBe(added.key);
  });

  it("needs three points before a shape can be finished", () => {
    let s = editorReducer(loaded(), { type: "setTool", tool: "add" });
    s = editorReducer(s, { type: "addPoint", point: [1, 1] });
    s = editorReducer(s, { type: "finishShape" });
    expect(s.pendingShape).toBeNull();
    s = editorReducer(s, { type: "cancelShape" });
    expect(s.drawing).toEqual([]);
  });

  it("ignores points when not adding", () => {
    const s = editorReducer(loaded(), { type: "addPoint", point: [1, 1] });
    expect(s.drawing).toEqual([]);
  });

  it("builds the save body, with null ids for new parts", () => {
    let s = editorReducer(loaded(), { type: "acceptProposed", key: "railing" });
    s = editorReducer(s, { type: "setTool", tool: "add" });
    for (const p of [
      [0, 0],
      [5, 0],
      [5, 5],
    ] as [number, number][])
      s = editorReducer(s, { type: "addPoint", point: p });
    s = editorReducer(s, { type: "finishShape" });
    s = editorReducer(s, { type: "labelNewPart", label: "window" });
    const body = toRegionsIn(s);
    expect(body).toHaveLength(5);
    expect(body.find((r) => r.id === "railing")).toMatchObject({ proposed: false, checked: true });
    expect(body[4]).toMatchObject({ id: null, label: "window", checked: false, proposed: false });
  });

  it("counts what is left to check the same way before and after reloading saved parts", () => {
    // Before: the railing suggestion is accepted in this visit.
    let s = editorReducer(loaded(), { type: "acceptProposed", key: "railing" });
    s = editorReducer(s, { type: "confirm", key: "pillar" });
    const before = pendingCount(s);
    // After a reload the server sends the same parts back as saved (accepted suggestion = normal part).
    const reloaded = editorReducer(initialEditorState, {
      type: "load",
      regions: [
        region("wall"),
        region("pillar", { label: "pillar", needs_check: true, checked: true, polygon: sq(20) }),
        region("balcony", { label: "balcony", needs_check: true, polygon: sq(40) }),
        region("railing", { label: "railing", checked: true, polygon: sq(60) }),
      ],
    });
    expect(before).toBe(1);
    expect(pendingCount(reloaded)).toBe(before);
  });

  it("two quick taps far apart never close a shape; a second tap on the last corner does", () => {
    let s = editorReducer(loaded(), { type: "setTool", tool: "add" });
    for (const p of [
      [100, 100],
      [300, 100],
      [300, 300],
      [100, 300],
    ] as [number, number][])
      s = editorReducer(s, { type: "addPoint", point: p, closeTolerance: 6 });
    expect(s.pendingShape).toBeNull();
    expect(s.drawing).toHaveLength(4);
    s = editorReducer(s, { type: "addPoint", point: [102, 301], closeTolerance: 6 });
    expect(s.pendingShape).toHaveLength(4);
  });

  it("ignores a repeated tap while there are fewer than three corners", () => {
    let s = editorReducer(loaded(), { type: "setTool", tool: "add" });
    s = editorReducer(s, { type: "addPoint", point: [10, 10], closeTolerance: 6 });
    s = editorReducer(s, { type: "addPoint", point: [12, 11], closeTolerance: 6 });
    expect(s.drawing).toEqual([[10, 10]]);
    expect(s.pendingShape).toBeNull();
    expect(continueBlocker(s)).toBe("drawing");
  });

  it("offers a box in the middle of the photo as a keyboard way to add a part", () => {
    let s = editorReducer(loaded(), { type: "addBox", width: 1000, height: 800 });
    expect(s.pendingShape).toBeNull(); // only in "Add a part" mode
    s = editorReducer(s, { type: "setTool", tool: "add" });
    s = editorReducer(s, { type: "addBox", width: 1000, height: 800 });
    expect(s.pendingShape).toEqual([
      [350, 280],
      [650, 280],
      [650, 520],
      [350, 520],
    ]);
    expect(continueBlocker(s)).toBe("drawing");
    s = editorReducer(s, { type: "labelNewPart", label: "gate" });
    expect(s.parts[s.parts.length - 1]).toMatchObject({ label: "gate", id: null });
  });
});

describe("after saving a new part", () => {
  it("keeps it selected once the save gives it its id", () => {
    let s = editorReducer(initialEditorState, { type: "load", regions: [] });
    s = editorReducer(s, { type: "setTool", tool: "add" });
    s = editorReducer(s, { type: "addBox", width: 100, height: 100 });
    s = editorReducer(s, { type: "labelNewPart", label: "gate" });
    const poly = s.parts[0].polygon;
    s = editorReducer(s, { type: "load", regions: [{ ...region("srv-1", { label: "gate", source: "user" }), polygon: poly }] });
    expect(s.selectedKey).toBe("srv-1");
  });
});
