import type { MouseEvent } from "react";
import type { Point } from "@/api/types";
import { copy } from "@/copy";

/** Tap two points on the photo to draw the reference line. Coordinates are photo pixels. */
export function LineDrawer({
  photoUrl,
  width,
  height,
  points,
  onChange,
}: {
  photoUrl: string;
  width: number;
  height: number;
  points: Point[];
  onChange: (points: Point[]) => void;
}) {
  const onClick = (e: MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.round(((e.clientX - rect.left) / rect.width) * width);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * height);
    const p: Point = [Math.max(0, Math.min(width, x)), Math.max(0, Math.min(height, y))];
    onChange(points.length >= 2 ? [p] : [...points, p]);
  };
  const r = width / 140;
  return (
    <div className="relative w-full overflow-hidden rounded-lg border bg-muted" style={{ aspectRatio: `${width} / ${height}` }}>
      <img src={photoUrl} alt={copy.size.photoAlt} className="absolute inset-0 size-full object-fill" draggable={false} />
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="absolute inset-0 size-full cursor-crosshair touch-none"
        onClick={onClick}
        data-testid="line-drawer"
        aria-hidden="true"
      >
        {points.length === 2 && (
          <line
            x1={points[0][0]}
            y1={points[0][1]}
            x2={points[1][0]}
            y2={points[1][1]}
            stroke="#f59e0b"
            strokeWidth={r / 1.5}
            strokeLinecap="round"
          />
        )}
        {points.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={r} fill="#fff" stroke="#f59e0b" strokeWidth={r / 3} />
        ))}
      </svg>
    </div>
  );
}
