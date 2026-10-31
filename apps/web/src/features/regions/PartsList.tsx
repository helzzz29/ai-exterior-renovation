import { type Dispatch, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Label } from "@/api/types";
import { copy } from "@/copy";
import { Badge } from "@/components/ui/badge";
import { friendlyName, LABEL_STYLES, LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { type DraftPart, type EditorAction, isPending } from "./reducer";


export interface PartRow {
  label: Label;
  parts: DraftPart[];
}

/**
 * The side list: parts still waiting for an answer first, one by one; then one row per kind of
 * part ("Main wall · 11") that opens to the individual parts.
 */
export function partRows(parts: DraftPart[]): { pending: DraftPart[]; rows: PartRow[] } {
  const pending = parts.filter(isPending);
  const rows = LABELS.map((label) => ({
    label,
    parts: parts.filter((p) => p.label === label && !isPending(p)),
  })).filter((r) => r.parts.length > 0);
  return { pending, rows };
}

function Chip({
  part,
  name,
  selected,
  onSelect,
}: {
  part: DraftPart;
  name: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const Icon = LABEL_STYLES[part.label].icon;
  // A "Please check" question and a suggestion look different: amber and solid vs teal and dashed, each with its own word.
  const question = part.needsCheck && !part.checked && !part.proposed;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex min-h-10 items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-sm transition-colors hover:bg-muted sm:min-h-8",
        question && "border-warning bg-warning-soft/40",
        part.proposed && "border-2 border-dashed border-primary/60",
        selected && "border-primary bg-accent ring-2 ring-primary/25",
      )}
    >
      <Icon className="size-3.5 shrink-0" style={{ color: LABEL_STYLES[part.label].colour }} aria-hidden="true" />
      {name}
      {question && (
        <Badge variant="warning" className="ml-0.5 px-1.5 py-0 text-[11px]">
          {copy.parts.pleaseCheck}
        </Badge>
      )}
      {part.proposed && (
        <Badge variant="info" className="ml-0.5 px-1.5 py-0 text-[11px]">
          {copy.parts.suggestion}
        </Badge>
      )}
    </button>
  );
}

export function PartsList({
  parts,
  selectedKey,
  dispatch,
}: {
  parts: DraftPart[];
  selectedKey: string | null;
  dispatch: Dispatch<EditorAction>;
}) {
  const { pending, rows } = partRows(parts);
  const [open, setOpen] = useState<Set<Label>>(new Set());
  const select = (key: string) => dispatch({ type: "select", key });
  const toggle = (l: Label) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(l)) n.delete(l);
      else n.add(l);
      return n;
    });

  return (
    <div className="space-y-3">
      {pending.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label={copy.parts.pleaseCheck} data-testid="pending-parts">
          {pending.map((p) => (
            <li key={p.key}>
              <Chip part={p} name={friendlyName(p.label)} selected={selectedKey === p.key} onSelect={() => select(p.key)} />
            </li>
          ))}
        </ul>
      )}
      <ul className="space-y-1.5">
        {rows.map((row) => {
          const Icon = LABEL_STYLES[row.label].icon;
          const name = friendlyName(row.label);
          if (row.parts.length === 1) {
            const p = row.parts[0];
            return (
              <li key={row.label}>
                <Chip part={p} name={name} selected={selectedKey === p.key} onSelect={() => select(p.key)} />
              </li>
            );
          }
          const expanded = open.has(row.label) || row.parts.some((p) => p.key === selectedKey);
          return (
            <li key={row.label} className="space-y-1.5">
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => toggle(row.label)}
                className="flex min-h-10 w-full items-center gap-2 rounded-lg border bg-card px-3 py-1.5 text-left text-sm hover:bg-muted sm:min-h-9"
              >
                <Icon className="size-3.5" style={{ color: LABEL_STYLES[row.label].colour }} aria-hidden="true" />
                <span className="flex-1">{copy.parts.groupRow(name, row.parts.length)}</span>
                <ChevronDown className={cn("size-4 transition-transform", expanded && "rotate-180")} aria-hidden="true" />
              </button>
              {expanded && (
                <ul className="flex flex-wrap gap-1.5 pl-3">
                  {row.parts.map((p, i) => (
                    <li key={p.key}>
                      <Chip
                        part={p}
                        name={copy.parts.numbered(name, i + 1)}
                        selected={selectedKey === p.key}
                        onSelect={() => select(p.key)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
