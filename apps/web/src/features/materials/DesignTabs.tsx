import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";
import { Copy, Pencil, Plus } from "lucide-react";
import type { DesignOut } from "@/api/types";
import { copy } from "@/copy";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export const DESIGN_PANEL_ID = "design-panel";
export const designTabId = (id: string) => `design-tab-${id}`;

const MAX_NAME = 80;

export function DesignTabs({
  designs,
  activeId,
  onSelect,
  onCreate,
  onDuplicate,
  busy,
  onRename,
}: {
  /** Saves the new name (PATCH /api/designs/{id}); rejects if it could not be saved. */
  onRename: (id: string, name: string) => Promise<unknown>;
  designs: DesignOut[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDuplicate: () => void;
  busy: boolean;
}) {
  const [renaming, setRenaming] = useState(false);
  const [saving, setSaving] = useState(false);
  const active = designs.find((d) => d.id === activeId) ?? null;
  const [draft, setDraft] = useState("");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  const startRename = () => {
    if (!active) return;
    setDraft(active.name);
    setRenaming(true);
  };
  const saveRename = async (e: FormEvent) => {
    e.preventDefault();
    if (active && draft.trim()) {
      setSaving(true);
      try {
        await onRename(active.id, draft.trim().slice(0, MAX_NAME));
      } catch {
        return; // the mutation shows a friendly toast; the form stays open
      } finally {
        setSaving(false);
      }
    }
    setRenaming(false);
  };

  // Tabs pattern: arrow keys move between designs, Enter or Space opens one. Opening is not
  // automatic, because switching first saves the current design's choices.
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const last = designs.length - 1;
    const to =
      e.key === "ArrowRight" ? (i === last ? 0 : i + 1) : e.key === "ArrowLeft" ? (i === 0 ? last : i - 1) : e.key === "Home" ? 0 : e.key === "End" ? last : null;
    if (to === null) return;
    e.preventDefault();
    tabs.current[to]?.focus();
  };

  return (
    <div className="space-y-3 rounded-xl border bg-card p-3 shadow-card sm:p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="text-sm font-semibold" id="designs-label">
          {copy.materials.designs}
        </p>
        <div
          role="tablist"
          aria-labelledby="designs-label"
          className="flex min-w-0 max-w-full flex-wrap gap-1 rounded-lg bg-muted p-1"
        >
          {designs.map((d, i) => {
            const selected = d.id === activeId;
            return (
              <button
                key={d.id}
                ref={(el) => {
                  tabs.current[i] = el;
                }}
                id={designTabId(d.id)}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={DESIGN_PANEL_ID}
                tabIndex={selected || (!activeId && i === 0) ? 0 : -1}
                onClick={() => onSelect(d.id)}
                onKeyDown={(e) => onKeyDown(e, i)}
                className={cn(
                  "min-h-10 max-w-60 truncate rounded-md px-3 text-sm font-medium whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-9",
                  selected ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {d.name}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-2 sm:ml-auto">
          <Button variant="outline" size="sm" onClick={onCreate} disabled={busy}>
            <Plus aria-hidden="true" />
            {copy.materials.newDesign}
          </Button>
          <Button variant="outline" size="sm" onClick={onDuplicate} disabled={busy || !active}>
            <Copy aria-hidden="true" />
            {copy.materials.duplicate}
          </Button>
          <Button variant="ghost" size="sm" onClick={startRename} disabled={!active} aria-expanded={renaming}>
            <Pencil aria-hidden="true" />
            {copy.materials.rename}
          </Button>
        </div>
      </div>
      {renaming && (
        <form
          onSubmit={(e) => void saveRename(e)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setRenaming(false);
          }}
          className="flex flex-wrap items-end gap-2 border-t pt-3"
        >
          <div className="w-full space-y-1 sm:w-72">
            <label htmlFor="design-name" className="text-xs font-medium">
              {copy.materials.renameLabel}
            </label>
            <Input
              id="design-name"
              value={draft}
              maxLength={MAX_NAME}
              onChange={(e) => setDraft(e.target.value)}
              aria-describedby="design-name-count"
              autoFocus
            />
            <p id="design-name-count" className="text-xs text-muted-foreground">
              {copy.common.charCount(draft.length, MAX_NAME)}
            </p>
          </div>
          <div className="flex gap-2 pb-6">
            <Button type="submit" size="sm" pending={saving}>
              {copy.materials.renameSave}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setRenaming(false)} disabled={saving}>
              {copy.common.cancel}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
