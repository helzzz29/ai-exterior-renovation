import { type Dispatch, useId, useState } from "react";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, ChevronDown, CircleHelp, Trash2, X } from "lucide-react";
import type { Label, Point } from "@/api/types";
import { copy } from "@/copy";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CHECK_COLOUR, friendlyName, LABEL_STYLES, LABELS, labelColour } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { DraftPart, EditorAction } from "./reducer";

/**
 * Close-up of one part, cut from the photo with an SVG view box: the whole part always fits
 * (tall, narrow pillars included) and its outline is drawn on top. No extra download.
 */
export function CropPreview({
  photoUrl,
  polygon,
  imgW,
  imgH,
  colour,
}: {
  photoUrl: string;
  polygon: Point[];
  imgW: number;
  imgH: number;
  colour: string;
}) {
  const xs = polygon.map((p) => p[0]);
  const ys = polygon.map((p) => p[1]);
  const pad = Math.max(24, Math.round(Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 0.12));
  const x0 = Math.max(0, Math.min(...xs) - pad);
  const y0 = Math.max(0, Math.min(...ys) - pad);
  const x1 = Math.min(imgW, Math.max(...xs) + pad);
  const y1 = Math.min(imgH, Math.max(...ys) + pad);
  const w = Math.max(1, x1 - x0);
  const h = Math.max(1, y1 - y0);
  return (
    <svg
      aria-hidden="true"
      data-testid="crop-preview"
      viewBox={`${x0} ${y0} ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      className="h-24 w-full rounded-lg border bg-muted sm:h-40"
    >
      <image href={photoUrl} x={0} y={0} width={imgW} height={imgH} preserveAspectRatio="none" />
      <polygon
        points={polygon.map(([x, y]) => `${x},${y}`).join(" ")}
        fill="none"
        stroke={colour}
        strokeWidth={2.5}
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function LabelPicker({
  trigger,
  current,
  onPick,
}: {
  trigger: string;
  current?: Label;
  onPick: (label: Label) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          {trigger}
          <ChevronDown aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {LABELS.filter((l) => l !== current).map((l) => {
          const Icon = LABEL_STYLES[l].icon;
          return (
            <DropdownMenuItem key={l} onSelect={() => onPick(l)}>
              <Icon style={{ color: LABEL_STYLES[l].colour }} aria-hidden="true" />
              {friendlyName(l)}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

interface CardProps {
  part: DraftPart;
  dispatch: Dispatch<EditorAction>;
  photoUrl: string;
  imgW: number;
  imgH: number;
  /** Removing a part asks first (see RegionsStep). */
  onRemove: (part: DraftPart) => void;
}

/** "Is this a pillar?" [Yes] [No, it's a… ▾] [Remove it] */
export function CheckCard({ part, dispatch, photoUrl, imgW, imgH, onRemove }: CardProps) {
  const name = friendlyName(part.label);
  return (
    <Card className="border-warning shadow-raised" data-testid="check-card">
      <CardHeader className="pb-2 sm:pb-3">
        <Badge variant="warning" className="w-fit">
          <CircleHelp aria-hidden="true" />
          {copy.parts.pleaseCheck}
        </Badge>
        <CardTitle>{copy.parts.isThisA(name)}</CardTitle>
      </CardHeader>
      <CardContent>
        <CropPreview photoUrl={photoUrl} polygon={part.polygon} imgW={imgW} imgH={imgH} colour={CHECK_COLOUR} />
      </CardContent>
      <CardFooter>
        <Button onClick={() => dispatch({ type: "confirm", key: part.key })}>
          <Check aria-hidden="true" />
          {copy.parts.yes}
        </Button>
        <LabelPicker
          trigger={copy.parts.noItsA}
          current={part.label}
          onPick={(label) => dispatch({ type: "relabel", key: part.key, label })}
        />
        <Button variant="ghost" className="text-destructive hover:bg-destructive-soft hover:text-destructive" onClick={() => onRemove(part)}>
          <Trash2 aria-hidden="true" />
          {copy.parts.removeIt}
        </Button>
      </CardFooter>
    </Card>
  );
}

/** Dashed suggestion: "Did we find a railing here?" [Yes, keep it] [No] */
export function ProposedCard({ part, dispatch, photoUrl, imgW, imgH }: Omit<CardProps, "onRemove">) {
  return (
    <Card className="border-2 border-dashed border-primary/60 shadow-raised" data-testid="proposed-card">
      <CardHeader className="pb-2 sm:pb-3">
        <Badge variant="info" className="w-fit">
          <CircleHelp aria-hidden="true" />
          {copy.parts.suggestion}
        </Badge>
        <CardTitle>{copy.parts.proposedQuestion(friendlyName(part.label))}</CardTitle>
      </CardHeader>
      <CardContent>
        <CropPreview photoUrl={photoUrl} polygon={part.polygon} imgW={imgW} imgH={imgH} colour={labelColour(part.label)} />
      </CardContent>
      <CardFooter>
        <Button onClick={() => dispatch({ type: "acceptProposed", key: part.key })}>
          <Check aria-hidden="true" />
          {copy.parts.yesKeep}
        </Button>
        <Button variant="outline" onClick={() => dispatch({ type: "rejectProposed", key: part.key })}>
          <X aria-hidden="true" />
          {copy.parts.no}
        </Button>
      </CardFooter>
    </Card>
  );
}

/**
 * Keyboard route for "Move points": pick a corner and nudge it. Moves are kept inside the photo
 * and saved like a drag on the photo.
 */
export function CornerNudge({
  part,
  dispatch,
  imgW,
  imgH,
}: {
  part: DraftPart;
  dispatch: Dispatch<EditorAction>;
  imgW: number;
  imgH: number;
}) {
  const [corner, setCorner] = useState(0);
  const [big, setBig] = useState(false);
  const id = useId();
  const n = part.polygon.length;
  const index = Math.min(corner, n - 1);
  const step = Math.max(1, Math.round((big ? 0.04 : 0.008) * Math.max(imgW, imgH)));
  const move = (dx: number, dy: number) => {
    const [x, y] = part.polygon[index];
    const point: Point = [Math.max(0, Math.min(imgW, x + dx)), Math.max(0, Math.min(imgH, y + dy))];
    dispatch({ type: "movePoint", key: part.key, index, point });
  };
  const arrows = [
    { label: copy.parts.nudge.up, icon: ArrowUp, dx: 0, dy: -step, cls: "col-start-2" },
    { label: copy.parts.nudge.left, icon: ArrowLeft, dx: -step, dy: 0, cls: "col-start-1 row-start-2" },
    { label: copy.parts.nudge.right, icon: ArrowRight, dx: step, dy: 0, cls: "col-start-3 row-start-2" },
    { label: copy.parts.nudge.down, icon: ArrowDown, dx: 0, dy: step, cls: "col-start-2 row-start-2" },
  ];
  return (
    <details className="group rounded-lg border bg-paper/60" data-testid="corner-nudge">
      <summary className="flex items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm font-medium">
        {copy.parts.fineTune}
        <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="space-y-3 px-3 pb-3">
        <p className="text-xs text-muted-foreground">{copy.parts.fineTuneHint}</p>
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1">
            <label htmlFor={id} className="text-xs font-medium">
              {copy.parts.corner}
            </label>
            <select
              id={id}
              value={index}
              onChange={(e) => setCorner(Number(e.target.value))}
              className="block h-10 rounded-md border border-input bg-card px-2 text-sm"
            >
              {part.polygon.map((_, i) => (
                <option key={i} value={i}>
                  {copy.parts.cornerOf(i + 1, n)}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-3 grid-rows-2 gap-1" role="group" aria-label={copy.parts.fineTune}>
            {arrows.map(({ label, icon: Icon, dx, dy, cls }) => (
              <Button key={label} type="button" variant="outline" size="icon" className={cn("size-10 sm:size-9", cls)} aria-label={label} onClick={() => move(dx, dy)}>
                <Icon aria-hidden="true" />
              </Button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={big} onChange={(e) => setBig(e.target.checked)} className="size-4 accent-[var(--primary)]" />
            {copy.parts.bigSteps}
          </label>
        </div>
      </div>
    </details>
  );
}

/** A part that needs no answer: show what it is, let the user change, adjust or remove it. */
export function SelectedCard({ part, dispatch, photoUrl, imgW, imgH, onRemove }: CardProps) {
  const Icon = LABEL_STYLES[part.label].icon;
  return (
    <Card data-testid="selected-card" className="shadow-raised">
      <CardHeader className="pb-2 sm:pb-3">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{copy.parts.selectedPart}</p>
        <CardTitle className="flex items-center gap-2">
          <Icon className="size-5" style={{ color: LABEL_STYLES[part.label].colour }} aria-hidden="true" />
          {friendlyName(part.label)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <CropPreview photoUrl={photoUrl} polygon={part.polygon} imgW={imgW} imgH={imgH} colour={labelColour(part.label)} />
        <CornerNudge part={part} dispatch={dispatch} imgW={imgW} imgH={imgH} />
      </CardContent>
      <CardFooter>
        <LabelPicker
          trigger={copy.parts.changeType}
          current={part.label}
          onPick={(label) => dispatch({ type: "relabel", key: part.key, label })}
        />
        <Button variant="ghost" className="text-destructive hover:bg-destructive-soft hover:text-destructive" onClick={() => onRemove(part)}>
          <Trash2 aria-hidden="true" />
          {copy.parts.removeIt}
        </Button>
      </CardFooter>
    </Card>
  );
}
