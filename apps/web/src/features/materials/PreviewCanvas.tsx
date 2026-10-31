import type { Context } from "konva/lib/Context";
import { Group, Image as KImage, Layer, Rect, Stage } from "react-konva";
import type { Assignment, MaterialOut, Point, RegionOut } from "@/api/types";
import { copy } from "@/copy";
import { OPENING_LABELS } from "@/lib/labels";
import { useElementWidth, useImage, useImages } from "@/lib/useImage";

function clipTo(poly: Point[]) {
  return (ctx: Context) => {
    ctx.beginPath();
    poly.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.closePath();
  };
}

const LAYER: RegionOut["label"][] = ["wall", "roof_edge", "parapet", "pillar", "balcony", "gate", "railing"];

/** How strongly a chosen material covers the photo in the instant preview. */
export const PREVIEW_OPACITY = 0.75;

/** Scale a swatch so one tile covers about a tenth of the photo's width (a few feet). */
export function previewTileScale(photoWidth: number, swatchWidth: number): number {
  if (!swatchWidth || !photoWidth) return 1;
  return Math.max(0.2, Math.min(8, photoWidth / 10 / swatchWidth));
}

/**
 * Instant preview: each chosen material is laid over its part with a multiply blend (so the
 * photo's light and shadow show through), clipped to the part's outline. Windows and doors are
 * drawn again from the original photo on top so they never change.
 */
export function PreviewCanvas({
  photoUrl,
  width: imgW,
  height: imgH,
  regions,
  assignments,
  materials,
}: {
  photoUrl: string;
  width: number;
  height: number;
  regions: RegionOut[];
  assignments: Assignment[];
  materials: Record<string, MaterialOut>;
}) {
  const [ref, boxWidth] = useElementWidth<HTMLDivElement>();
  const photo = useImage(photoUrl);
  const swatchUrls = Array.from(
    new Set(assignments.map((a) => materials[a.material_id]?.swatch_url).filter((u): u is string => !!u)),
  );
  const swatches = useImages(swatchUrls);
  const scale = boxWidth > 0 ? boxWidth / imgW : 0;
  const assigned = new Map(assignments.map((a) => [a.region_id, a]));
  const openings = regions.filter((r) => OPENING_LABELS.has(r.label));
  // Back to front: walls first, parts in front of them later, windows and doors last.
  const layered = regions
    .filter((r) => !OPENING_LABELS.has(r.label) && !r.proposed)
    .sort((x, y) => LAYER.indexOf(x.label) - LAYER.indexOf(y.label));

  return (
    <div
      ref={ref}
      role="img"
      aria-label={copy.materials.previewAlt}
      className="w-full overflow-hidden rounded-lg border bg-muted"
      style={{ aspectRatio: `${imgW} / ${imgH}` }}
    >
      {scale > 0 && (
        <Stage width={boxWidth} height={imgH * scale} scaleX={scale} scaleY={scale} listening={false}>
          <Layer listening={false}>
            {photo && <KImage image={photo} width={imgW} height={imgH} />}
            {layered.map((region) => {
              const a = assigned.get(region.id);
              const mat = a ? materials[a.material_id] : undefined;
              if (!a || !mat) {
                // A part kept as it is stays as in the photo, even where a wall behind it changes.
                return region.label !== "wall" && photo ? (
                  <Group key={region.id} clipFunc={clipTo(region.polygon)}>
                    <KImage image={photo} width={imgW} height={imgH} />
                  </Group>
                ) : null;
              }
              const colour = mat.colorable ? (a.color ?? mat.default_color ?? null) : null;
              const swatch = swatches[mat.swatch_url];
              const tile = swatch ? previewTileScale(imgW, swatch.width) : 1;
              return (
                <Group key={region.id} clipFunc={clipTo(region.polygon)}>
                  {colour ? (
                    <>
                      {/* The new colour, keeping the photo's light and shadow… */}
                      <Rect width={imgW} height={imgH} fill={colour} globalCompositeOperation="color" opacity={PREVIEW_OPACITY} />
                      {/* …and a soft multiply so dark or light colours read clearly too. */}
                      <Rect width={imgW} height={imgH} fill={colour} globalCompositeOperation="multiply" opacity={0.35} />
                    </>
                  ) : swatch ? (
                    <>
                      <Rect
                        width={imgW}
                        height={imgH}
                        fillPatternImage={swatch}
                        fillPatternRepeat="repeat"
                        fillPatternScale={{ x: tile, y: tile }}
                        opacity={PREVIEW_OPACITY}
                      />
                      {/* Lay the photo's shading back over the texture. */}
                      {photo && (
                        <KImage image={photo} width={imgW} height={imgH} globalCompositeOperation="multiply" opacity={0.55} />
                      )}
                    </>
                  ) : null}
                </Group>
              );
            })}
            {photo &&
              openings.map((o) => (
                <Group key={o.id} clipFunc={clipTo(o.polygon)}>
                  <KImage image={photo} width={imgW} height={imgH} />
                </Group>
              ))}
          </Layer>
        </Stage>
      )}
    </div>
  );
}
