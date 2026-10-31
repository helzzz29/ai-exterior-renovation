import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronRight, CircleAlert, Clock, Lock, RefreshCw } from "lucide-react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { isRenderBusy, qk, useProject, useRender } from "@/api/hooks";
import type { DesignOut } from "@/api/types";
import { copy } from "@/copy";
import { ErrorState, PageSkeleton } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { TracePanel } from "@/features/trace/TracePanel";
import type { WizardContext } from "./context";
import { NeedsUpdateBanner, needsUpdateMessage } from "./NeedsUpdateBanner";
import { STATUS_LABEL, type StepStatus, stepStatuses } from "./progress";
import { STEPS, type StepSlug, stepForStage } from "./steps";
import { useActiveDesign } from "./useActiveDesign";

function StepMarker({ index, status, current }: { index: number; status: StepStatus; current: boolean }) {
  const Icon =
    status === "done" ? Check : status === "locked" ? Lock : status === "stale" ? RefreshCw : status === "progress" ? Clock : status === "attention" || status === "ready" ? CircleAlert : null;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-7 shrink-0 place-items-center rounded-full border text-xs font-semibold transition-colors",
        current && "border-primary bg-primary text-primary-foreground",
        !current && status === "done" && "border-success/40 bg-success-soft text-success",
        !current && (status === "attention" || status === "ready" || status === "stale") && "border-warning bg-warning-soft text-warning-foreground",
        !current && status === "progress" && "border-primary/30 bg-accent text-primary",
        !current && status === "todo" && "border-border-strong bg-card text-muted-foreground",
        !current && status === "locked" && "border-border bg-muted text-muted-foreground",
      )}
    >
      {current || !Icon ? index + 1 : <Icon className="size-3.5" />}
    </span>
  );
}

function StepItem({
  step,
  status,
  current,
  projectId,
  search,
  layout,
  onNavigate,
}: {
  step: (typeof STEPS)[number];
  status: StepStatus;
  current: boolean;
  projectId: string;
  search: string;
  layout: "row" | "list";
  onNavigate?: () => void;
}) {
  const statusText = current ? null : STATUS_LABEL[status];
  const inner = (
    <>
      <StepMarker index={step.index} status={status} current={current} />
      <span className="min-w-0">
        <span className={cn("block text-sm leading-tight", current ? "font-semibold text-foreground" : "font-medium")}>
          {step.title}
        </span>
        {statusText && (
          <span className={cn("block text-xs leading-tight text-muted-foreground", layout === "row" && "mt-0.5")}>
            {statusText}
          </span>
        )}
      </span>
      {current && <span className="sr-only">({copy.stepper.current})</span>}
    </>
  );
  const base =
    layout === "row"
      ? "flex h-full items-center gap-2.5 rounded-lg px-2 py-2 xl:px-3"
      : "flex items-center gap-3 rounded-lg px-3 py-2.5";
  if (status === "locked") {
    return (
      <Tooltip content={copy.stepper.locked}>
        <span aria-disabled="true" tabIndex={0} className={cn(base, "cursor-not-allowed text-muted-foreground opacity-75")}>
          {inner}
          <span className="sr-only">{copy.stepper.locked}</span>
        </span>
      </Tooltip>
    );
  }
  return (
    <Link
      to={`/projects/${projectId}/${step.slug}${search}`}
      aria-current={current ? "step" : undefined}
      onClick={onNavigate}
      className={cn(base, current ? "bg-accent" : "text-foreground/85 hover:bg-muted hover:text-foreground")}
    >
      {inner}
    </Link>
  );
}

/** The six steps. Wide screens: one row. Phones: "Step 4 of 6 · Choose materials" that opens the list. */
function Stepper({ projectId, current, statuses }: { projectId: string; current: number; statuses: StepStatus[] }) {
  const { search } = useLocation();
  const [open, setOpen] = useState(false);
  const currentStep = STEPS[current];
  return (
    <nav aria-label={copy.stepper.label}>
      {/* compact, below 1024 px (six full labels don't fit comfortably on tablets) */}
      <div className="lg:hidden">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="step-menu"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center gap-3 rounded-xl border bg-card px-3 py-2.5 text-left shadow-card"
        >
          <StepMarker index={current} status={statuses[current]} current />
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-medium text-muted-foreground">
              {copy.stepper.stepOf(current + 1, STEPS.length)}
            </span>
            <span className="block truncate text-sm font-semibold">{currentStep.title}</span>
          </span>
          <span className="text-xs font-medium text-primary">{copy.stepper.menuLabel}</span>
          <ChevronDown className={cn("size-4 text-primary transition-transform", open && "rotate-180")} aria-hidden="true" />
        </button>
        <div className="mt-2 flex gap-1" aria-hidden="true">
          {statuses.map((s, i) => (
            <span
              key={STEPS[i].slug}
              className={cn(
                "h-1 flex-1 rounded-full",
                i === current ? "bg-primary" : s === "done" ? "bg-success/60" : s === "stale" || s === "attention" || s === "ready" ? "bg-warning" : "bg-border",
              )}
            />
          ))}
        </div>
        {open && (
          <ol id="step-menu" className="mt-2 space-y-0.5 rounded-xl border bg-card p-1.5 shadow-raised">
            {STEPS.map((s) => (
              <li key={s.slug}>
                <StepItem
                  step={s}
                  status={statuses[s.index]}
                  current={s.index === current}
                  projectId={projectId}
                  search={search}
                  layout="list"
                  onNavigate={() => setOpen(false)}
                />
              </li>
            ))}
          </ol>
        )}
      </div>
      {/* full row, from 1024 px */}
      <ol className="hidden grid-cols-6 gap-1 rounded-xl border bg-card p-1.5 shadow-card lg:grid">
        {STEPS.map((s) => (
          <li key={s.slug} className="min-w-0">
            <StepItem
              step={s}
              status={statuses[s.index]}
              current={s.index === current}
              projectId={projectId}
              search={search}
              layout="row"
            />
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * A new look takes minutes. While the active design's look is being made, keep an eye on it from
 * any step, refresh the step statuses when it finishes, and say so if the user is elsewhere.
 */
function useLookWatcher(projectId: string, active: DesignOut | null, onLookStep: boolean) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const watching = active && isRenderBusy(active.render) ? active.id : null;
  const render = useRender(watching);
  const lastStatus = useRef<string | null>(null);
  const status = render.data?.status ?? null;
  useEffect(() => {
    const before = lastStatus.current;
    lastStatus.current = status;
    if (!watching || !before || before === status) return;
    if ((before === "queued" || before === "running") && status && status !== "queued" && status !== "running") {
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
      if (onLookStep) return;
      const to = `/projects/${projectId}/look?design=${watching}`;
      if (status === "failed") toast.error(copy.look.failedToast);
      else toast.success(copy.look.ready, { action: { label: copy.look.readyAction, onClick: () => navigate(to) } });
    }
  }, [status, watching, onLookStep, projectId, qc, navigate]);
}

function WizardSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true">
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-14 w-full rounded-xl" />
      <PageSkeleton />
    </div>
  );
}

export function WizardLayout() {
  const { projectId = "" } = useParams();
  const location = useLocation();
  const project = useProject(projectId);
  const stage = project.data?.stage;
  const designsEnabled = stage === "designing" || stage === "regions_review" || stage === "scale_review";
  const { list, active } = useActiveDesign(projectId, !!project.data && designsEnabled);
  const slug = location.pathname.split("/").filter(Boolean)[2] ?? "";
  const currentSlug = (STEPS.find((s) => s.slug === slug)?.slug ?? null) as StepSlug | null;
  useLookWatcher(projectId, stage === "designing" ? active : null, currentSlug === "look");

  if (project.isPending) return <WizardSkeleton />;
  if (project.isError) return <ErrorState error={project.error} onRetry={() => void project.refetch()} />;

  const p = project.data;
  const current = Math.max(0, STEPS.findIndex((s) => s.slug === slug));
  const ctx: WizardContext = { project: p };
  const message = needsUpdateMessage(p, list, active);
  const statuses = stepStatuses(p, stage === "designing" ? active : null);

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <nav aria-label="Breadcrumb" className="min-w-0">
            <ol className="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground">
              <li>
                <Link to="/" className="rounded-sm hover:text-foreground hover:underline">
                  {copy.nav.myProjects}
                </Link>
              </li>
              <li aria-hidden="true">
                <ChevronRight className="size-3.5" />
              </li>
              <li className="min-w-0 truncate font-medium text-foreground" aria-current="page">
                {p.name}
              </li>
            </ol>
          </nav>
          <p className="text-xs text-muted-foreground">{copy.stepper.autosave}</p>
        </div>
        <Stepper projectId={p.id} current={current} statuses={statuses} />
      </div>
      <NeedsUpdateBanner message={message} projectId={p.id} current={currentSlug} />
      <Outlet context={ctx} />
      <TracePanel projectId={p.id} refreshKey={`${p.updated_at}|${p.stage}|${active?.render?.id ?? ""}|${active?.render?.status ?? ""}`} />
    </div>
  );
}

/** `/projects/:id` opens the step that matches where the project is, keeping the chosen design. */
export function WizardIndex() {
  const { projectId = "" } = useParams();
  const { search } = useLocation();
  const project = useProject(projectId);
  if (!project.data) return null;
  return <Navigate to={`/projects/${projectId}/${stepForStage(project.data.stage)}${search}`} replace />;
}
