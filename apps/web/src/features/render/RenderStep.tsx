import { type FormEvent, type ReactNode, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Loader2,
  Palette,
  PencilLine,
  RefreshCw,
  Sparkles,
  ThumbsUp,
  TriangleAlert,
} from "lucide-react";
import { ReactCompareSlider, ReactCompareSliderImage, useReactCompareSliderRef } from "react-compare-slider";
import { Link } from "react-router";
import { isRenderBusy, useAcceptRender, useRender, useStartRender } from "@/api/hooks";
import type { RenderOut } from "@/api/types";
import { copy } from "@/copy";
import { PageHeader } from "@/components/layout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/states";
import { cn } from "@/lib/utils";
import { BackLink, DesignBar } from "@/features/wizard/DesignBar";
import { useWizard } from "@/features/wizard/context";
import { useActiveDesign } from "@/features/wizard/useActiveDesign";
import {
  LIGHTING_STYLES,
  PhotoLightingControl,
  type LightingMode,
} from "@/components/PhotoLightingControl";

const NOTE_MAX = 500;

/**
 * Progress told only from what the server reports: waiting to start, creating, and (when the
 * automatic check asked for another try) improving. No made-up percentages.
 */
function CreatingPanel({ render, costLink }: { render: RenderOut; costLink: string }) {
  const phase = render.status === "queued" ? 0 : render.attempts > 1 ? 2 : 1;
  const steps = copy.look.progressSteps.filter((_, i) => i < 2 || phase === 2);
  return (
    <Card aria-live="polite" className="overflow-hidden">
      <CardContent className="grid gap-6 pt-6 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center sm:p-8">
        <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-accent text-primary sm:mx-0" aria-hidden="true">
          <Sparkles className="size-8" />
        </span>
        <div className="space-y-4 text-center sm:text-left">
          <div className="space-y-1">
            <p role="status" className="text-lg font-semibold tracking-tight">
              {copy.look.creating}
            </p>
            <p className="text-sm leading-relaxed text-muted-foreground">{copy.look.creatingBody}</p>
          </div>
          <ol className="inline-flex flex-col gap-2 text-left text-sm">
            {steps.map((s, i) => (
              <li key={s} className={cn("flex items-center gap-2.5", i > phase && "text-muted-foreground")}>
                {i < phase ? (
                  <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
                ) : i === phase ? (
                  <Loader2 className="size-4 animate-spin text-primary" aria-hidden="true" />
                ) : (
                  <Circle className="size-4" aria-hidden="true" />
                )}
                <span className={cn(i === phase && "font-medium")}>{s}</span>
              </li>
            ))}
          </ol>
          <div>
            <Button asChild variant="outline">
              <Link to={costLink}>{copy.look.viewCost}</Link>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** Before/after slider with labels on the picture, and buttons that do the same from the keyboard. */
function Compare({ before, after }: { before: string; after: string }) {
  const slider = useReactCompareSliderRef();
  const [view, setView] = useState<"before" | "compare" | "after">("compare");
  const [lighting, setLighting] = useState<LightingMode>("day");
  const lightingStyle = LIGHTING_STYLES[lighting];

  const show = (v: typeof view) => {
    setView(v);
    // The divider position is "how much of the before photo shows".
    slider.current?.setPosition(v === "before" ? 100 : v === "after" ? 0 : 50);
  };
  const options: { v: typeof view; label: string }[] = [
    { v: "before", label: copy.look.before },
    { v: "compare", label: copy.look.compare },
    { v: "after", label: copy.look.after },
  ];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-card/60 px-4 py-2.5 backdrop-blur-sm">
        <div role="group" aria-label={copy.look.viewLabel} className="inline-flex rounded-lg bg-muted p-1">
          {options.map(({ v, label }) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => show(v)}
              className={cn(
                "min-h-9 rounded-md px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                view === v ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <PhotoLightingControl mode={lighting} onChange={setLighting} />
      </div>

      <div
        className="relative overflow-hidden rounded-2xl border border-border/80 bg-muted shadow-card transition-all duration-300"
        style={{ filter: lightingStyle.filter }}
      >
        {lightingStyle.overlayStyle && (
          <div
            className="pointer-events-none absolute inset-0 z-10 transition-opacity duration-300"
            style={lightingStyle.overlayStyle}
          />
        )}
        <ReactCompareSlider
          ref={slider}
          aria-label={copy.look.sliderLabel}
          keyboardIncrement="5%"
          onPositionChange={(p) => setView(p >= 99 ? "before" : p <= 1 ? "after" : "compare")}
          itemOne={<ReactCompareSliderImage src={before} alt={copy.look.before} />}
          itemTwo={<ReactCompareSliderImage src={after} alt={copy.look.after} />}
        />
        <span aria-hidden="true" className="pointer-events-none absolute top-3 left-3 z-20 rounded-full bg-foreground/75 px-3 py-1 text-xs font-semibold text-background backdrop-blur-md">
          {copy.look.before}
        </span>
        <span aria-hidden="true" className="pointer-events-none absolute top-3 right-3 z-20 rounded-full bg-primary px-3 py-1 text-xs font-bold text-primary-foreground shadow-md backdrop-blur-md">
          {copy.look.after}
        </span>
      </div>
    </div>
  );
}

export function RenderStep() {
  const { project } = useWizard();
  const { designs, list, active, setActive } = useActiveDesign(project.id);
  const render = useRender(active?.id);
  const start = useStartRender(project.id);
  const accept = useAcceptRender(project.id, active?.id ?? "");
  const [changing, setChanging] = useState(false);
  const [note, setNote] = useState("");

  const header = (
    <PageHeader id="look-title" eyebrow={copy.stepper.stepOf(5, 6)} title={copy.look.title} />
  );
  const wrap = (body: ReactNode) => (
    <section className="space-y-5" aria-labelledby="look-title">
      {header}
      {active && <DesignBar designs={list} active={active} onSelect={setActive} />}
      <div className="max-w-4xl space-y-4">{body}</div>
      <BackLink projectId={project.id} from="look" />
    </section>
  );

  const search = active ? `?design=${active.id}` : "";
  const materialsLink = `/projects/${project.id}/materials${search}`;
  const costLink = `/projects/${project.id}/cost${search}`;

  if (designs.isPending || (active && render.isPending)) return wrap(<PageSkeleton label={copy.look.loading} />);
  if (designs.isError) return wrap(<ErrorState error={designs.error} onRetry={() => void designs.refetch()} />);
  if (render.isError) return wrap(<ErrorState error={render.error} onRetry={() => void render.refetch()} />);

  const r = render.data ?? null;
  if (!active || !r) {
    return wrap(
      <EmptyState
        icon={<Sparkles />}
        title={copy.look.noneYet}
        action={
          <Button asChild>
            <Link to={materialsLink}>{copy.look.goToMaterials}</Link>
          </Button>
        }
      />,
    );
  }

  if (isRenderBusy(r)) return wrap(<CreatingPanel render={r} costLink={costLink} />);

  if (r.status === "failed" || !r.image_url) {
    return wrap(
      <Alert variant="destructive" className="flex-col sm:flex-row sm:items-center">
        <TriangleAlert aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-1">
          <AlertTitle>{copy.look.failed}</AlertTitle>
          <AlertDescription className="text-foreground/80">
            {r.user_note ? copy.look.retryHintNote(r.user_note) : copy.look.retryHint}
          </AlertDescription>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => start.mutate({ designId: active.id, note: r.user_note })} pending={start.isPending}>
            {copy.common.tryAgain}
          </Button>
          <Button asChild variant="outline">
            <Link to={materialsLink}>{copy.look.changeMaterials}</Link>
          </Button>
        </div>
      </Alert>,
    );
  }

  const issues = r.qa && !r.qa.passed ? r.qa.failed_checks : [];
  const accepted = r.status === "accepted";

  const submitChange = (e: FormEvent) => {
    e.preventDefault();
    start.mutate(
      { designId: active.id, note: note.trim() || null },
      {
        onSuccess: () => {
          setChanging(false);
          setNote("");
        },
      },
    );
  };
  // Cancel throws the note away on purpose, so an old note never comes back by surprise.
  const cancelChange = () => {
    setChanging(false);
    setNote("");
  };

  return wrap(
    <>
      <Compare before={project.photo?.url ?? ""} after={r.image_url} />

      {r.user_note && <p className="text-sm text-muted-foreground">{copy.look.yourNote(r.user_note)}</p>}

      {r.stale && (
        <Alert variant="warning" className="flex-col sm:flex-row sm:items-center" data-testid="look-stale">
          <RefreshCw aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-1">
            <AlertTitle>{copy.look.staleTitle}</AlertTitle>
            <AlertDescription>{copy.look.staleBody}</AlertDescription>
          </div>
          <Button onClick={() => start.mutate({ designId: active.id })} pending={start.isPending}>
            <Sparkles aria-hidden="true" />
            {copy.stale.lookAction}
          </Button>
        </Alert>
      )}

      {issues.length > 0 && (
        <Alert variant="warning">
          <TriangleAlert aria-hidden="true" />
          <div>
            <AlertTitle>{copy.look.issuesTitle}</AlertTitle>
            <AlertDescription>
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </AlertDescription>
          </div>
        </Alert>
      )}

      {accepted && !r.stale && (
        <Alert variant="success" className="flex-col sm:flex-row sm:items-center">
          <CheckCircle2 aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-0.5">
            <p className="font-medium">{copy.look.liked}</p>
            <p className="text-sm text-muted-foreground">{copy.look.acceptedNote}</p>
          </div>
          <Button asChild>
            <Link to={costLink}>
              {copy.look.toCost}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        </Alert>
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {!accepted && !r.stale && (
          <Button size="lg" onClick={() => accept.mutate(r.id)} pending={accept.isPending}>
            <ThumbsUp aria-hidden="true" />
            {copy.look.like}
          </Button>
        )}
        <Button size="lg" variant="outline" onClick={() => (changing ? cancelChange() : setChanging(true))} aria-expanded={changing} aria-controls="change-form">
          <PencilLine aria-hidden="true" />
          {copy.look.change}
        </Button>
        <Button size="lg" variant="outline" asChild>
          <Link to={materialsLink}>
            <Palette aria-hidden="true" />
            {copy.look.changeMaterials}
          </Link>
        </Button>
      </div>

      {changing && (
        <Card id="change-form">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{copy.look.change}</CardTitle>
          </CardHeader>
          <form onSubmit={submitChange}>
            <CardContent className="space-y-1.5">
              <Label htmlFor="change-note">{copy.look.changePrompt}</Label>
              <Textarea
                id="change-note"
                value={note}
                maxLength={NOTE_MAX}
                aria-describedby="change-note-count"
                onChange={(e) => setNote(e.target.value)}
                autoFocus
              />
              <p id="change-note-count" className="text-right text-xs text-muted-foreground">
                {copy.common.charCount(note.length, NOTE_MAX)}
              </p>
            </CardContent>
            <CardFooter>
              <Button type="submit" disabled={!note.trim()} pending={start.isPending}>
                {copy.look.changeSubmit}
              </Button>
              <Button type="button" variant="ghost" onClick={cancelChange}>
                {copy.look.cancelNote}
              </Button>
            </CardFooter>
          </form>
        </Card>
      )}
    </>,
  );
}
