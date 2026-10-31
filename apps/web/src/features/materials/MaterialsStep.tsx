import { type CSSProperties, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Eye, EyeOff, Info, Sparkles, ThumbsUp, TriangleAlert } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import {
  putAssignmentsKeepalive,
  qk,
  useCreateDesign,
  useMaterialAdvice,
  useRenameDesign,
  useMaterials,
  useRegions,
  useSaveAssignments,
  useStartRender,
} from "@/api/hooks";
import type { Assignment, MaterialOut } from "@/api/types";
import { copy } from "@/copy";
import { SaveStatus } from "@/components/feedback";
import { PageHeader, StickyActionBar } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, PageSkeleton, Spinner } from "@/components/states";
import { AUTOSAVE_MS, POLL_MS } from "@/lib/config";
import { friendlyName, LABEL_STYLES } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { BackLink } from "@/features/wizard/DesignBar";
import { useWizard } from "@/features/wizard/context";
import { useActiveDesign } from "@/features/wizard/useActiveDesign";
import { DESIGN_PANEL_ID, DesignTabs, designTabId } from "./DesignTabs";
import {
  adviceForGroup,
  assignGroup,
  COLOUR_PRESETS,
  type GroupAdvice,
  groupChoice,
  groupParts,
  materialsForLabel,
  type PartGroup,
} from "./logic";
import { PreviewCanvas } from "./PreviewCanvas";

interface Draft {
  designId: string;
  list: Assignment[];
  version: number;
}

function colourName(hex: string | null | undefined): string | null {
  if (!hex) return null;
  return COLOUR_PRESETS.find((c) => c.hex === hex.toLowerCase())?.name ?? hex.toUpperCase();
}

function MaterialCard({
  m,
  selected,
  focusable,
  advice,
  onPick,
  onKeyDown,
  refFn,
}: {
  m: MaterialOut;
  selected: boolean;
  focusable: boolean;
  advice: GroupAdvice;
  onPick: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void;
  refFn: (el: HTMLButtonElement | null) => void;
}) {
  const notIdeal = advice.notIdeal[m.id];
  return (
    <button
      ref={refFn}
      type="button"
      role="radio"
      aria-checked={selected}
      tabIndex={focusable ? 0 : -1}
      onClick={onPick}
      onKeyDown={onKeyDown}
      className={cn(
        "relative flex w-full gap-3 rounded-lg border bg-card p-2.5 text-left transition-[border-color,box-shadow,background-color] outline-none hover:border-border-strong hover:bg-paper/60 focus-visible:ring-2 focus-visible:ring-ring",
        selected && "border-primary bg-accent/50 ring-2 ring-primary/30 hover:border-primary hover:bg-accent/50",
      )}
    >
      <img src={m.swatch_url} alt="" className="size-12 shrink-0 rounded-md border object-cover" />
      <span className="min-w-0 flex-1 space-y-1">
        <span className="flex items-start justify-between gap-2">
          <span className="font-medium leading-snug">{m.name}</span>
          {selected && (
            <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
              <Check className="size-3.5" aria-label={copy.materials.selected} />
            </span>
          )}
        </span>
        {(advice.recommended.has(m.id) || notIdeal) && (
          <span className="flex flex-wrap gap-1">
            {advice.recommended.has(m.id) && (
              <Badge variant="success">
                <ThumbsUp aria-hidden="true" />
                {copy.materials.recommended}
              </Badge>
            )}
            {notIdeal && (
              <Badge variant="warning" className="whitespace-normal">
                <TriangleAlert aria-hidden="true" />
                {copy.materials.notIdeal(notIdeal)}
              </Badge>
            )}
          </span>
        )}
        <span className="block text-xs leading-relaxed text-muted-foreground">
          {copy.materials.lasts(m.durability)} · {copy.materials.weather[m.weather_resistance]}
        </span>
        <span className="block text-xs leading-relaxed text-muted-foreground">
          {copy.materials.upkeep}: {m.maintenance}
        </span>
      </span>
    </button>
  );
}

/**
 * One kind of part (e.g. all pillars) as an accordion section. Closed, it sums up the choice;
 * open, it offers "Keep as it is" and every suitable material as one radio group (arrow keys move
 * between options), plus colours for paints and textures.
 */
function GroupSection({
  group,
  materials,
  advice,
  assignments,
  open,
  onToggle,
  onChange,
}: {
  group: PartGroup;
  materials: MaterialOut[];
  advice: GroupAdvice;
  assignments: Assignment[];
  open: boolean;
  onToggle: () => void;
  onChange: (next: Assignment[]) => void;
}) {
  const choice = groupChoice(assignments, group.regionIds);
  const options = materialsForLabel(materials, group.label, advice);
  const chosen = choice ? materials.find((m) => m.id === choice.material_id) : undefined;
  const name = friendlyName(group.label);
  const colour = choice?.color ?? chosen?.default_color ?? "#ffffff";
  const nameId = `group-${group.label}-name`;
  const panelId = `group-${group.label}-panel`;
  const radios = useRef<(HTMLButtonElement | null)[]>([]);

  // Radio group keyboard pattern: one Tab stop, arrows move and choose.
  const values: (string | null)[] = [null, ...options.map((m) => m.id)];
  const checkedIndex = Math.max(0, values.indexOf(choice?.material_id ?? null));
  const pick = (value: string | null) => {
    if (value === null) return onChange(assignGroup(assignments, group.regionIds, null));
    const m = options.find((o) => o.id === value)!;
    onChange(assignGroup(assignments, group.regionIds, m.id, m.colorable ? (m.default_color ?? null) : null));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const last = values.length - 1;
    const to =
      e.key === "ArrowDown" || e.key === "ArrowRight"
        ? i === last ? 0 : i + 1
        : e.key === "ArrowUp" || e.key === "ArrowLeft"
          ? i === 0 ? last : i - 1
          : e.key === "Home" ? 0 : e.key === "End" ? last : null;
    if (to === null) return;
    e.preventDefault();
    pick(values[to]);
    radios.current[to]?.focus();
  };

  return (
    <section className={cn("rounded-xl border bg-card shadow-card transition-shadow", open && "border-border-strong shadow-raised")}>
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="size-3 shrink-0 rounded-full ring-2 ring-card" style={{ background: LABEL_STYLES[group.label].colour }} aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span id={nameId} className="font-semibold">
                {name}
              </span>
              <span className="text-xs text-muted-foreground">{copy.materials.count(group.regionIds.length)}</span>
            </span>
            <span className="mt-0.5 flex items-center gap-1.5 text-sm text-muted-foreground">
              {chosen ? (
                <>
                  <img src={chosen.swatch_url} alt="" className="size-4 shrink-0 rounded-sm border object-cover" />
                  {chosen.colorable && (
                    <span className="size-3.5 shrink-0 rounded-full border" style={{ background: colour }} aria-hidden="true" />
                  )}
                  <span className="truncate text-foreground">
                    {chosen.name}
                    {chosen.colorable && colourName(colour) ? ` · ${colourName(colour)}` : ""}
                  </span>
                </>
              ) : (
                copy.materials.keptAsIs
              )}
            </span>
          </span>
          <ChevronDown className={cn("size-5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden="true" />
        </button>
      </h3>
      {open && (
        <div id={panelId} className="space-y-3 border-t px-4 pt-3 pb-4">
          <p className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
            <Info className="mt-px size-3.5 shrink-0 text-primary" aria-hidden="true" />
            {copy.materials.appliesTo(group.regionIds.length)}
          </p>
          <div role="radiogroup" aria-labelledby={nameId} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
            <button
              ref={(el) => {
                radios.current[0] = el;
              }}
              type="button"
              role="radio"
              aria-checked={!choice}
              tabIndex={checkedIndex === 0 ? 0 : -1}
              onClick={() => pick(null)}
              onKeyDown={(e) => onKeyDown(e, 0)}
              className={cn(
                "flex min-h-11 w-full items-center justify-between gap-2 rounded-lg border border-dashed px-3 py-2 text-left text-sm outline-none hover:bg-paper/60 focus-visible:ring-2 focus-visible:ring-ring sm:col-span-2 lg:col-span-1",
                !choice && "border-solid border-primary bg-accent/50 ring-2 ring-primary/30",
              )}
            >
              {copy.materials.keepAsIs}
              {!choice && <Check className="size-4 text-primary" aria-hidden="true" />}
            </button>
            {options.length === 0 && <p className="text-sm text-muted-foreground">{copy.materials.noneAvailable}</p>}
            {options.map((m, i) => (
              <MaterialCard
                key={m.id}
                m={m}
                advice={advice}
                selected={choice?.material_id === m.id}
                focusable={checkedIndex === i + 1}
                onPick={() => pick(m.id)}
                onKeyDown={(e) => onKeyDown(e, i + 1)}
                refFn={(el) => {
                  radios.current[i + 1] = el;
                }}
              />
            ))}
          </div>
          {chosen?.colorable && (
            <fieldset className="space-y-2.5 rounded-lg border bg-paper/50 p-3">
              <legend className="px-1 text-sm font-semibold">{copy.materials.colour}</legend>
              <div className="flex flex-wrap items-center gap-2">
                {COLOUR_PRESETS.map(({ hex, name: presetName }) => {
                  const on = colour.toLowerCase() === hex;
                  return (
                    <button
                      key={hex}
                      type="button"
                      aria-label={presetName}
                      title={presetName}
                      aria-pressed={on}
                      onClick={() => onChange(assignGroup(assignments, group.regionIds, chosen.id, hex))}
                      className={cn(
                        "grid size-9 place-items-center rounded-full border-2 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                        on ? "border-primary ring-2 ring-primary/30" : "border-border-strong",
                      )}
                      style={{ background: hex }}
                    >
                      {on && <Check className={cn("size-4", ["#1f2937", "#5b6270", "#c97b5a"].includes(hex) ? "text-white" : "text-foreground")} aria-hidden="true" />}
                    </button>
                  );
                })}
                <label className="ml-1 flex items-center gap-2 text-sm">
                  <input
                    type="color"
                    value={colour}
                    aria-label={copy.materials.colourFor(name)}
                    onChange={(e) => onChange(assignGroup(assignments, group.regionIds, chosen.id, e.target.value))}
                    className="h-9 w-12 cursor-pointer rounded-md border bg-card"
                  />
                  <span aria-hidden="true" className="text-muted-foreground">
                    {copy.materials.ownColour}
                  </span>
                </label>
              </div>
              <p className="text-xs text-muted-foreground" aria-live="polite">
                {copy.materials.colour}: <span className="font-medium text-foreground">{colourName(colour)}</span>
              </p>
            </fieldset>
          )}
        </div>
      )}
    </section>
  );
}

export function MaterialsStep() {
  const { project } = useWizard();
  const navigate = useNavigate();
  const regions = useRegions(project.id);
  const materials = useMaterials();
  const advice = useMaterialAdvice(project.id);
  const { designs, list, active, setActive } = useActiveDesign(project.id);
  const createDesign = useCreateDesign(project.id);
  const save = useSaveAssignments(project.id);
  const startRender = useStartRender(project.id);
  const rename = useRenameDesign(project.id);
  const qc = useQueryClient();

  const [draft, setDraft] = useState<Draft | null>(null);
  const draftRef = useRef<Draft | null>(null);
  draftRef.current = draft;
  const saved = useRef<{ designId: string; version: number }>({ designId: "", version: 0 });
  // Re-render when a save lands, so "Saving…" turns into "Choices saved".
  const [, bumpSaved] = useState(0);
  const isDirty = (d: Draft | null) =>
    !!d && !(saved.current.designId === d.designId && saved.current.version === d.version);
  const [openGroup, setOpenGroup] = useState<string | null | undefined>(undefined);
  const [previewOpen, setPreviewOpen] = useState(true);

  // The first design is made by the server when the parts and size are confirmed; the screen never
  // creates one by itself. If the list is still empty, look again shortly.
  const designCount = designs.data?.length;
  useEffect(() => {
    if (designCount !== 0) return;
    const t = setTimeout(() => void designs.refetch(), POLL_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [designCount, designs.dataUpdatedAt]);

  // Leaving the screen (stepper, links, closing the tab) never loses a choice: send what is unsaved.
  useEffect(() => {
    const flushNow = () => {
      const d = draftRef.current;
      if (!d || !isDirty(d)) return;
      saved.current = { designId: d.designId, version: d.version };
      void putAssignmentsKeepalive(d.designId, d.list).finally(() => {
        void qc.invalidateQueries({ queryKey: qk.designs(project.id) });
        void qc.invalidateQueries({ queryKey: qk.estimate(d.designId) });
        void qc.invalidateQueries({ queryKey: qk.render(d.designId) });
      });
    };
    window.addEventListener("beforeunload", flushNow);
    return () => {
      window.removeEventListener("beforeunload", flushNow);
      flushNow();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load the choices of the design being shown.
  useEffect(() => {
    if (active && draft?.designId !== active.id) {
      setDraft({ designId: active.id, list: active.assignments, version: 0 });
      saved.current = { designId: active.id, version: 0 };
    }
  }, [active, draft?.designId]);

  // Save choices automatically.
  useEffect(() => {
    if (!draft || !isDirty(draft)) return;
    const snapshot = draft;
    const t = setTimeout(() => {
      save.mutate(
        { designId: snapshot.designId, assignments: snapshot.list },
        {
          onSuccess: () => {
            saved.current = { designId: snapshot.designId, version: snapshot.version };
            bumpSaved((n) => n + 1);
          },
        },
      );
    }, AUTOSAVE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const flush = async () => {
    if (!draft || !isDirty(draft)) return;
    await save.mutateAsync({ designId: draft.designId, assignments: draft.list });
    saved.current = { designId: draft.designId, version: draft.version };
    bumpSaved((n) => n + 1);
  };

  if (regions.isPending || materials.isPending || designs.isPending || designCount === 0) {
    return <PageSkeleton label={copy.materials.loading} />;
  }
  const error = regions.error ?? materials.error ?? designs.error;
  if (error || !regions.data || !materials.data) {
    return <ErrorState error={error} onRetry={() => void Promise.all([regions.refetch(), materials.refetch(), designs.refetch()])} />;
  }

  const groups = groupParts(regions.data.regions);
  const assignments = draft?.list ?? [];
  const byId = Object.fromEntries(materials.data.map((m) => [m.id, m]));
  const adviceList = advice.data?.advice ?? [];
  const photo = project.photo!;
  // One part group open at a time; the first one starts open.
  const openLabel = openGroup === undefined ? (groups[0]?.label ?? null) : openGroup;

  const change = (next: Assignment[]) =>
    setDraft((d) => (d ? { ...d, list: next, version: d.version + 1 } : d));

  const switchTo = async (id: string) => {
    try {
      await flush();
    } catch {
      return;
    }
    setActive(id);
  };

  const onCreate = async () => {
    try {
      await flush();
      const d = await createDesign.mutateAsync({ name: copy.materials.defaultDesignName(list.length + 1) });
      setActive(d.id);
      toast.success(copy.materials.created);
    } catch {
      // toast shown by the mutation
    }
  };

  const onDuplicate = async () => {
    if (!active) return;
    try {
      await flush();
      const d = await createDesign.mutateAsync({ name: copy.materials.copyName(active.name), copy_from: active.id });
      setActive(d.id);
      toast.success(copy.materials.duplicated);
    } catch {
      // toast shown by the mutation
    }
  };

  const onCreateLook = async () => {
    if (!active) return;
    try {
      await flush();
      await startRender.mutateAsync({ designId: active.id });
      navigate(`/projects/${project.id}/look?design=${active.id}`);
    } catch {
      // toast shown by the mutation
    }
  };

  const busy = createDesign.isPending || startRender.isPending;
  const saveState = save.isPending || isDirty(draft) ? "saving" : draft && saved.current.version > 0 ? "saved" : "idle";

  return (
    <section className="space-y-5" aria-labelledby="materials-title">
      <PageHeader
        id="materials-title"
        eyebrow={copy.stepper.stepOf(4, 6)}
        title={copy.materials.title}
        description={copy.materials.intro}
      />

      <DesignTabs
        designs={list}
        activeId={active?.id ?? null}
        onSelect={(id) => void switchTo(id)}
        onCreate={() => void onCreate()}
        onDuplicate={() => void onDuplicate()}
        busy={busy}
        onRename={(designId, name) => rename.mutateAsync({ designId, name })}
      />

      <div
        id={DESIGN_PANEL_ID}
        role="tabpanel"
        aria-labelledby={active ? designTabId(active.id) : undefined}
        className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_26rem]"
      >
        {/* Preview: pinned under the header on phones (and can be folded away), sticky on desktop. */}
        <div className="sticky top-14 z-10 -mx-4 space-y-2 border-b bg-background/95 px-4 pt-2 pb-3 backdrop-blur sm:-mx-6 sm:px-6 lg:top-20 lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold tracking-tight">{copy.materials.preview}</h2>
            <div className="flex items-center gap-2">
              <SaveStatus state={saveState} savingLabel={copy.materials.saving} savedLabel={copy.materials.saved} />
              <Button
                variant="ghost"
                size="sm"
                className="lg:hidden"
                aria-expanded={previewOpen}
                aria-controls="preview-box"
                onClick={() => setPreviewOpen((v) => !v)}
              >
                {previewOpen ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                {previewOpen ? copy.materials.hidePreview : copy.materials.showPreview}
              </Button>
            </div>
          </div>
          <div id="preview-box" className={cn(!previewOpen && "hidden lg:block")}>
            <div
              // On phones keep the picture to about a third of the screen height, so the choices stay in view.
              className="mx-auto max-w-[min(100%,calc(34vh*var(--photo-ratio)))] lg:max-w-none"
              style={{ "--photo-ratio": photo.width / photo.height } as CSSProperties}
            >
              <PreviewCanvas
                photoUrl={photo.url}
                width={photo.width}
                height={photo.height}
                regions={regions.data.regions}
                assignments={assignments}
                materials={byId}
              />
            </div>
            <p className="mt-2 hidden text-xs text-muted-foreground lg:block">
              {copy.materials.previewNote} {copy.materials.windowsUntouched}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold tracking-tight">{copy.materials.parts}</h2>
            {!advice.data?.ready && <Spinner label={copy.materials.choosing} />}
          </div>
          <p className="text-sm text-muted-foreground lg:hidden">
            {copy.materials.previewNote} {copy.materials.windowsUntouched}
          </p>
          {groups.map((g) => (
            <GroupSection
              key={g.label}
              group={g}
              materials={materials.data}
              advice={adviceForGroup(adviceList, g.regionIds)}
              assignments={assignments}
              open={openLabel === g.label}
              onToggle={() => setOpenGroup(openLabel === g.label ? null : g.label)}
              onChange={change}
            />
          ))}
        </div>
      </div>

      <StickyActionBar>
        <div className="mr-auto">
          <BackLink projectId={project.id} from="materials" />
        </div>
        {assignments.length === 0 && (
          <span className="text-xs text-muted-foreground" id="create-look-blocked">
            {copy.materials.createLookDisabled}
          </span>
        )}
        <Button
          size="lg"
          disabled={!active || assignments.length === 0 || busy}
          aria-describedby={assignments.length === 0 ? "create-look-blocked" : undefined}
          onClick={() => void onCreateLook()}
        >
          {startRender.isPending ? <Spinner className="text-primary-foreground" /> : <Sparkles aria-hidden="true" />}
          {copy.materials.createLook}
        </Button>
      </StickyActionBar>
    </section>
  );
}
