import { useEffect, useReducer, useRef, useState } from "react";
import { CheckCircle2, Info, MousePointer2, Move, PenLine, SquareDashed, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useApproveRegions, useRegions, useSaveRegions } from "@/api/hooks";
import type { Label } from "@/api/types";
import { copy } from "@/copy";
import { SaveStatus } from "@/components/feedback";
import { PageHeader, StickyActionBar } from "@/components/layout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { ErrorState, PageSkeleton } from "@/components/states";
import { AUTOSAVE_MS } from "@/lib/config";
import { elementRequirementBadge, friendlyName, LABEL_STYLES, LABELS } from "@/lib/labels";
import { DESKTOP } from "@/lib/useMediaQuery";
import { cn } from "@/lib/utils";
import { BackLink } from "@/features/wizard/DesignBar";
import { useWizard } from "@/features/wizard/context";
import { CheckCard, ProposedCard, SelectedCard } from "./PartCards";
import { PartsList } from "./PartsList";
import { RegionCanvas } from "./RegionCanvas";
import {
  continueBlocker,
  type DraftPart,
  editorReducer,
  type EditorState,
  initialEditorState,
  pendingParts,
  selectedPart,
  type Tool,
  toRegionsIn,
} from "./reducer";

export function RegionsStep() {
  const { project } = useWizard();
  const navigate = useNavigate();
  const regions = useRegions(project.id);
  const save = useSaveRegions(project.id);
  const approve = useApproveRegions(project.id);
  const [state, dispatch] = useReducer(editorReducer, initialEditorState);
  const loaded = useRef(false);
  const savedVersion = useRef(0);
  const inFlightVersion = useRef<number | null>(null);
  const latest = useRef<EditorState>(state);
  latest.current = state;
  const saveRef = useRef(save.mutate);
  saveRef.current = save.mutate;
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [toRemove, setToRemove] = useState<DraftPart | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);

  // Bring the question card into view (and focus) when a part is picked. On phones, first bring
  // the photo back to the top, so the photo and the card are on screen together.
  useEffect(() => {
    const el = cardRef.current;
    if (!state.selectedKey || !el) return;
    const desktop = typeof window !== "undefined" && window.matchMedia?.(DESKTOP).matches;
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    // Runs last on purpose: a later smooth scroll replaces an earlier one.
    if (!desktop) editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    el.focus({ preventScroll: true });
  }, [state.selectedKey]);

  useEffect(() => {
    if (regions.data && !loaded.current) {
      loaded.current = true;
      dispatch({ type: "load", regions: regions.data.regions });
    }
  }, [regions.data]);

  // Save edits automatically, then take the saved version (with new ids) if nothing changed since.
  useEffect(() => {
    if (state.version === savedVersion.current) return;
    const sent = state.version;
    const body = toRegionsIn(state);
    const t = setTimeout(() => {
      setSaveState("saving");
      inFlightVersion.current = sent;
      save.mutate(body, {
        onSuccess: (out) => {
          savedVersion.current = Math.max(savedVersion.current, sent);
          setSaveState("saved");
          if (latest.current.version === sent) dispatch({ type: "load", regions: out.regions });
        },
        onError: () => setSaveState("idle"),
        onSettled: () => {
          if (inFlightVersion.current === sent) inFlightVersion.current = null;
        },
      });
    }, AUTOSAVE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.version]);

  // Leaving the screen before the automatic save ran: send the last edit now, once.
  useEffect(
    () => () => {
      const s = latest.current;
      if (s.version !== savedVersion.current && inFlightVersion.current !== s.version) {
        saveRef.current(toRegionsIn(s));
      }
    },
    [],
  );

  if (regions.isPending) return <PageSkeleton label={copy.parts.loadingPhoto} />;
  if (regions.isError) return <ErrorState error={regions.error} onRetry={() => void regions.refetch()} />;
  const photo = project.photo;
  if (!photo) return <ErrorState error={null} />;

  const pending = pendingParts(state);
  const blocker = continueBlocker(state);
  const sel = selectedPart(state);
  const busy = save.isPending || approve.isPending;

  const onContinue = async () => {
    try {
      if (state.version !== savedVersion.current) {
        const sent = state.version;
        inFlightVersion.current = sent;
        const out = await save.mutateAsync(toRegionsIn(state));
        savedVersion.current = sent;
        dispatch({ type: "load", regions: out.regions });
      }
      const p = await approve.mutateAsync();
      toast.success(copy.parts.savedOnContinue);
      navigate(`/projects/${project.id}/${p.stage === "designing" ? "materials" : "size"}`);
    } catch {
      // The toast from the mutation already explains what went wrong.
    }
  };

  const tools: { tool: Tool; label: string; tip: string; icon: typeof Move }[] = [
    { tool: "select", label: copy.parts.tools.select, tip: copy.parts.tools.selectTip, icon: MousePointer2 },
    { tool: "move", label: copy.parts.tools.move, tip: copy.parts.tools.moveTip, icon: Move },
    { tool: "add", label: copy.parts.tools.add, tip: copy.parts.tools.addTip, icon: PenLine },
  ];

  const cardProps = { dispatch, photoUrl: photo.url, imgW: photo.width, imgH: photo.height, onRemove: setToRemove };

  return (
    <section className="space-y-5" aria-labelledby="parts-title">
      <PageHeader
        id="parts-title"
        eyebrow={copy.stepper.stepOf(2, 6)}
        title={copy.parts.title}
        description={copy.parts.intro}
      />

      {/* One summary instead of a stack of alerts. */}
      {state.parts.length > 0 &&
        (pending.length > 0 ? (
          <Alert variant="warning" data-testid="unsure-banner">
            <Info aria-hidden="true" />
            <div className="space-y-1">
              <p className="font-medium">{copy.parts.unsureBanner(pending.length)}</p>
              {project.regions_approved && <p>{copy.parts.changedAfterApproval}</p>}
            </div>
          </Alert>
        ) : (
          <Alert variant="success">
            <CheckCircle2 aria-hidden="true" />
            <div className="space-y-1">
              <p className="font-medium">{copy.parts.allChecked}</p>
              {project.regions_approved && <p>{copy.parts.changedAfterApproval}</p>}
            </div>
          </Alert>
        ))}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_22.5rem]">
        <div className="min-w-0 space-y-3">
          {/* Architectural Guide Banner */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-blue-100 bg-blue-50/60 px-3.5 py-2.5 text-xs text-slate-700">
            <span className="flex items-center gap-1.5 font-semibold text-blue-950">
              <Info className="h-3.5 w-3.5 text-blue-600" aria-hidden="true" />
              Section Guide:
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center rounded-md bg-blue-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                Mandatory
              </span>
              <span className="text-slate-600">Main Wall</span>
              <span className="text-slate-300" aria-hidden="true">•</span>
              <span className="inline-flex items-center rounded-md border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-700">
                Openings
              </span>
              <span className="text-slate-600">Windows & Doors (deducted)</span>
              <span className="text-slate-300" aria-hidden="true">•</span>
              <span className="inline-flex items-center rounded-md bg-slate-200/80 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                Optional
              </span>
              <span className="text-slate-600">Balcony, Canopy, Louvers, Compound Wall</span>
            </div>
          </div>

          <div
            role="toolbar"
            aria-label={copy.parts.toolbar}
            className="flex flex-wrap items-center gap-1.5 rounded-xl border bg-card p-1.5 shadow-card"
          >
            {tools.map(({ tool, label, tip, icon: Icon }) => (
              <Tooltip key={tool} content={tip}>
                <Button
                  variant={state.tool === tool ? "default" : "ghost"}
                  size="sm"
                  aria-pressed={state.tool === tool}
                  onClick={() => dispatch({ type: "setTool", tool })}
                >
                  <Icon aria-hidden="true" />
                  {label}
                </Button>
              </Tooltip>
            ))}
            <span className="mx-1 hidden h-6 w-px bg-border sm:block" aria-hidden="true" />
            <Tooltip content={copy.parts.tools.removeTip}>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:bg-destructive-soft hover:text-destructive"
                disabled={!sel}
                onClick={() => sel && setToRemove(sel)}
              >
                <Trash2 aria-hidden="true" />
                {copy.parts.tools.remove}
              </Button>
            </Tooltip>
            <SaveStatus
              className="ml-auto px-2"
              state={saveState}
              savingLabel={copy.parts.saving}
              savedLabel={copy.parts.saved}
            />
          </div>

          {state.tool === "move" && !sel && (
            <p className="rounded-lg bg-accent px-3 py-2 text-sm text-accent-foreground" role="status">
              {copy.parts.moveHint}
            </p>
          )}

          {state.tool === "add" && !state.pendingShape && (
            <Alert variant="info" className="flex-col sm:flex-row sm:items-center">
              <PenLine aria-hidden="true" className="hidden sm:block" />
              <div className="min-w-0 flex-1 space-y-0.5">
                <p>{copy.parts.addHint}</p>
                <p className="text-xs font-medium" aria-live="polite">
                  {copy.parts.cornersSoFar(state.drawing.length)}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={state.drawing.length < 3} onClick={() => dispatch({ type: "finishShape" })}>
                  {copy.parts.addFinish}
                </Button>
                {state.drawing.length === 0 && (
                  <Tooltip content={copy.parts.addBoxHint}>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => dispatch({ type: "addBox", width: photo.width, height: photo.height })}
                    >
                      <SquareDashed aria-hidden="true" />
                      {copy.parts.addBox}
                    </Button>
                  </Tooltip>
                )}
                <Button size="sm" variant="ghost" onClick={() => dispatch({ type: "setTool", tool: "select" })}>
                  {copy.parts.addCancel}
                </Button>
              </div>
            </Alert>
          )}

          {state.pendingShape && (
            <Card className="border-primary shadow-raised" data-testid="type-picker">
              <CardHeader className="pb-2 sm:pb-3">
                <CardTitle className="text-base">{copy.parts.whatIsIt}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {LABELS.map((l: Label) => {
                    const Icon = LABEL_STYLES[l].icon;
                    const req = elementRequirementBadge(l);
                    return (
                      <Button
                        key={l}
                        variant="outline"
                        className="h-auto min-h-12 flex-col items-start gap-1 p-2.5 text-left whitespace-normal hover:border-blue-300 hover:bg-blue-50/30"
                        onClick={() => dispatch({ type: "labelNewPart", label: l })}
                      >
                        <div className="flex w-full items-center gap-2">
                          <Icon style={{ color: LABEL_STYLES[l].colour }} className="h-4 w-4 shrink-0" aria-hidden="true" />
                          <span className="flex-1 text-xs font-medium leading-tight">{friendlyName(l)}</span>
                        </div>
                        <span aria-hidden="true" className={cn("inline-block rounded px-1.5 py-0.5 text-[9px] leading-none", req.className)}>
                          {req.label}
                        </span>
                      </Button>
                    );
                  })}
                </div>
                <Button variant="ghost" size="sm" onClick={() => dispatch({ type: "cancelShape" })}>
                  {copy.parts.addCancel}
                </Button>
              </CardContent>
            </Card>
          )}

          <div ref={editorRef} style={{ scrollMarginTop: "4.25rem" }}>
            <RegionCanvas imageUrl={photo.url} width={photo.width} height={photo.height} state={state} dispatch={dispatch} />
          </div>
          {state.parts.length === 0 && <p className="text-sm text-muted-foreground">{copy.parts.noParts}</p>}
        </div>

        <aside className="space-y-4">
          <div
            ref={cardRef}
            tabIndex={-1}
            data-testid="part-card"
            className="scroll-mt-20 scroll-mb-28 rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {sel ? (
              sel.proposed ? (
                <ProposedCard part={sel} dispatch={dispatch} photoUrl={photo.url} imgW={photo.width} imgH={photo.height} />
              ) : sel.needsCheck && !sel.checked ? (
                <CheckCard part={sel} {...cardProps} />
              ) : (
                <SelectedCard part={sel} {...cardProps} />
              )
            ) : (
              <p className="rounded-xl border border-dashed border-border-strong bg-card p-4 text-sm text-muted-foreground">
                {copy.parts.tapToSelect}
              </p>
            )}
          </div>

          <Card>
            <CardHeader className="pb-2 sm:pb-3">
              <CardTitle className="text-base">{copy.parts.allParts}</CardTitle>
            </CardHeader>
            <CardContent>
              <PartsList parts={state.parts} selectedKey={state.selectedKey} dispatch={dispatch} />
            </CardContent>
          </Card>
        </aside>
      </div>

      <StickyActionBar>
        <div className="hidden sm:block">
          <BackLink projectId={project.id} from="parts" />
        </div>
        {/* counter and the reason Continue is blocked, stacked, so the bar stays one row on phones */}
        <div className="mr-auto min-w-0 flex-1 basis-40">
          {state.parts.length > 0 && (
            <p
              className={cn("text-sm font-medium", pending.length === 0 && "text-success")}
              aria-live="polite"
              data-testid="check-counter"
            >
              {pending.length > 0 ? copy.parts.leftToCheck(pending.length) : copy.parts.nothingLeft}
            </p>
          )}
          {blocker && (
            <p className="text-xs leading-snug text-muted-foreground" id="continue-blocked">
              {blocker === "drawing" ? copy.parts.drawingBlocks : copy.parts.continueDisabled}
            </p>
          )}
        </div>
        <Button
          className="h-11 sm:h-12"
          size="lg"
          disabled={!!blocker}
          pending={busy}
          aria-describedby={blocker ? "continue-blocked" : undefined}
          onClick={() => void onContinue()}
        >
          {copy.parts.continue}
        </Button>
      </StickyActionBar>

      <ConfirmDialog
        open={!!toRemove}
        title={toRemove ? copy.parts.removeTitle(friendlyName(toRemove.label)) : ""}
        body={copy.parts.removeBody}
        confirmLabel={copy.parts.removeConfirm}
        cancelLabel={copy.parts.keepIt}
        onConfirm={() => {
          if (toRemove) dispatch({ type: "remove", key: toRemove.key });
          setToRemove(null);
        }}
        onCancel={() => setToRemove(null)}
      />
    </section>
  );
}
