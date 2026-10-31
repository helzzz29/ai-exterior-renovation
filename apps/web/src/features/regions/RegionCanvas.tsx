import type { Dispatch } from "react";
import type Konva from "konva";
import { Circle, Group, Image as KImage, Layer, Line, Rect, Stage, Text } from "react-konva";
import type { Point } from "@/api/types";
import { copy } from "@/copy";
import { CHECK_COLOUR, labelColour } from "@/lib/labels";
import { useElementWidth, useImage } from "@/lib/useImage";
import { type DraftPart, type EditorAction, type EditorState, isPending } from "./reducer";

const flat = (pts: Point[]) => pts.flatMap(([x, y]) => [x, y]);

function topLeft(poly: Point[]): Point {
  return [Math.min(...poly.map((p) => p[0])), Math.min(...poly.map((p) => p[1]))];
}

function PartShape({
  part,
  selected,
  scale,
  interactive,
  onSelect,
}: {
  part: DraftPart;
  selected: boolean;
  scale: number;
  interactive: boolean;
  onSelect: () => void;
}) {
  const colour = labelColour(part.label);
  const pending = isPending(part);
  const amber = part.needsCheck && !part.checked;
  const [bx, by] = topLeft(part.polygon);
  const badge = amber ? copy.parts.pleaseCheck : part.proposed ? copy.parts.suggestion : null;
  const badgeW = badge ? Math.ceil(badge.length * 7.6 + 18) : 0;
  return (
    <Group>
      <Line
        points={flat(part.polygon)}
        closed
        // Translucent fill, stronger when selected; suggestions are only outlined lightly.
        fill={hexToRgba(colour, part.proposed ? 0.12 : selected ? 0.45 : pending ? 0.3 : 0.22)}
        stroke={amber ? CHECK_COLOUR : colour}
        strokeWidth={selected ? 4 : amber ? 3.5 : 2}
        strokeScaleEnabled={false}
        dash={part.proposed ? [12, 8] : undefined}
        listening={interactive}
        onClick={onSelect}
        onTap={onSelect}
        perfectDrawEnabled={false}
      />
      {badge && (
        <Group x={bx} y={by} scaleX={1 / scale} scaleY={1 / scale} listening={interactive} onClick={onSelect} onTap={onSelect}>
          <Rect x={4} y={4} width={badgeW} height={24} cornerRadius={12} fill={amber ? CHECK_COLOUR : "#0f766e"} />
          <Text x={4} y={9} width={badgeW} align="center" text={badge} fontSize={13} fontStyle="bold" fill="#fff" />
        </Group>
      )}
    </Group>
  );
}

export function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export function RegionCanvas({
  imageUrl,
  width: imgW,
  height: imgH,
  state,
  dispatch,
}: {
  imageUrl: string;
  width: number;
  height: number;
  state: EditorState;
  dispatch: Dispatch<EditorAction>;
}) {
  const [ref, boxWidth] = useElementWidth<HTMLDivElement>();
  const img = useImage(imageUrl);
  const scale = boxWidth > 0 ? boxWidth / imgW : 0;
  const clamp = (x: number, y: number): Point => [
    Math.max(0, Math.min(imgW, Math.round(x))),
    Math.max(0, Math.min(imgH, Math.round(y))),
  ];

  const pointer = (e: Konva.KonvaEventObject<Event>): Point | null => {
    const stage = e.target.getStage();
    const pos = stage?.getPointerPosition();
    if (!pos || !scale) return null;
    return clamp(pos.x / scale, pos.y / scale);
  };

  const onStageClick = (e: Konva.KonvaEventObject<Event>) => {
    if (state.tool === "add") {
      const p = pointer(e);
      if (p) dispatch({ type: "addPoint", point: p, closeTolerance: 18 / scale });
      return;
    }
    if (e.target === e.target.getStage() || e.target.name() === "photo") {
      dispatch({ type: "select", key: null });
    }
  };

  const selected = state.parts.find((p) => p.key === state.selectedKey) ?? null;
  const interactive = state.tool !== "add";
  // Draw large parts first so small ones on top stay clickable.
  const ordered = [...state.parts].sort((a, b) => area(b.polygon) - area(a.polygon));

  return (
    <div
      ref={ref}
      role="img"
      aria-label={copy.parts.photoAlt}
      className="w-full overflow-hidden rounded-xl border bg-muted shadow-card"
      style={{ aspectRatio: `${imgW} / ${imgH}` }}
    >
      {scale > 0 && (
        <Stage
          width={boxWidth}
          height={imgH * scale}
          scaleX={scale}
          scaleY={scale}
          onClick={onStageClick}
          onTap={onStageClick}
          style={{ cursor: state.tool === "add" ? "crosshair" : "default", touchAction: state.tool === "select" ? "auto" : "none" }}
        >
          <Layer>
            {img ? (
              <KImage image={img} width={imgW} height={imgH} name="photo" />
            ) : (
              <Rect width={imgW} height={imgH} fill="#e5e7eb" name="photo" />
            )}
            {ordered.map((p) => (
              <PartShape
                key={p.key}
                part={p}
                selected={p.key === state.selectedKey}
                scale={scale}
                interactive={interactive}
                onSelect={() => dispatch({ type: "select", key: p.key })}
              />
            ))}
            {state.tool === "move" &&
              selected?.polygon.map(([x, y], i) => (
                <Circle
                  key={`${selected.key}-${i}`}
                  x={x}
                  y={y}
                  radius={9 / scale}
                  fill="#fff"
                  stroke={labelColour(selected.label)}
                  strokeWidth={3}
                  strokeScaleEnabled={false}
                  draggable
                  onDragMove={(e) => {
                    const pt = clamp(e.target.x(), e.target.y());
                    e.target.position({ x: pt[0], y: pt[1] });
                    dispatch({ type: "movePoint", key: selected.key, index: i, point: pt });
                  }}
                  onMouseEnter={(e) => {
                    const c = e.target.getStage()?.container();
                    if (c) c.style.cursor = "grab";
                  }}
                  onMouseLeave={(e) => {
                    const c = e.target.getStage()?.container();
                    if (c) c.style.cursor = "default";
                  }}
                />
              ))}
            {(state.drawing.length > 0 || state.pendingShape) && (
              <Group listening={false}>
                <Line
                  points={flat(state.pendingShape ?? state.drawing)}
                  closed={!!state.pendingShape}
                  stroke="#0f766e"
                  strokeWidth={3}
                  strokeScaleEnabled={false}
                  fill={state.pendingShape ? "rgba(15,118,110,0.25)" : undefined}
                />
                {(state.pendingShape ?? state.drawing).map(([x, y], i) => (
                  <Circle key={i} x={x} y={y} radius={(i === 0 ? 8 : 6) / scale} fill={i === 0 ? "#0f766e" : "#fff"} stroke="#0f766e" strokeWidth={2} strokeScaleEnabled={false} />
                ))}
              </Group>
            )}
          </Layer>
        </Stage>
      )}
    </div>
  );
}

function area(poly: Point[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}
