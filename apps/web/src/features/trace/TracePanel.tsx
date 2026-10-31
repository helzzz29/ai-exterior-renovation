import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Camera, CheckCircle2, ChevronDown, Info, Palette, RotateCcw, Sparkles } from "lucide-react";
import { useAiCalls } from "@/api/hooks";
import type { AICallOut } from "@/api/types";
import { copy } from "@/copy";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Spinner } from "@/components/states";
import { cn } from "@/lib/utils";

type Stage = AICallOut["stage"];

export interface TraceStep {
  id: string;
  /** which automatic step this was (internal code, never shown) */
  step: string;
  title: string;
  summary: string;
  seconds: number;
  reused: boolean;
  /** failed calls of this step folded into this (successful) row */
  retries: number;
  /** the step found something worth looking at */
  attention: boolean;
  provider: string;
  model: string;
}

export interface TraceGroup {
  key: string;
  stage: Stage;
  /** 1 for the first time this stage ran, 2 for the second, ... */
  run: number;
  steps: TraceStep[];
}

/**
 * Turn the raw call list into what a homeowner can read: consecutive calls of the same stage
 * become one group (in the order they happened), and failed calls are folded into the next
 * successful call of the same step as "worked on the 2nd try" instead of separate rows.
 * A stage that starts again is a new, numbered group: a new look starts with `new_run`; a photo
 * or materials step that shows up a second time in a row means that work was done again.
 */
export function groupTrace(calls: AICallOut[]): TraceGroup[] {
  const groups: TraceGroup[] = [];
  const pendingFailures: Record<string, number> = {};
  for (const call of calls) {
    if (!call.ok) {
      pendingFailures[call.step] = (pendingFailures[call.step] ?? 0) + 1;
      continue;
    }
    let group = groups[groups.length - 1];
    const sameStage = !!group && group.stage === call.stage && group.steps.length > 0;
    const newLookRun = sameStage && call.stage === "look" && call.new_run;
    // Inside a new look, the same steps repeat on purpose (automatic redo), so only `new_run` counts there.
    const repeatedStep = sameStage && call.stage !== "look" && group.steps.some((s) => s.step === call.step);
    if (!group || group.stage !== call.stage || newLookRun || repeatedStep) {
      const run = groups.filter((g) => g.stage === call.stage).length + 1;
      group = { key: `${call.stage}-${groups.length}`, stage: call.stage, run, steps: [] };
      groups.push(group);
    }
    group.steps.push({
      id: call.id,
      step: call.step,
      title: call.title,
      summary: call.summary,
      seconds: call.latency_ms / 1000,
      reused: call.cached,
      retries: pendingFailures[call.step] ?? 0,
      attention: !!call.attention,
      provider: call.provider,
      model: call.model,
    });
    pendingFailures[call.step] = 0;
  }
  return groups;
}

const STAGE_ICON: Record<Stage, typeof Camera> = { photo: Camera, materials: Palette, look: Sparkles };

function StepRow({ step }: { step: TraceStep }) {
  const meta = [
    step.reused ? copy.trace.reused : copy.trace.took(step.seconds.toFixed(1)),
    step.retries > 0 ? copy.trace.retried(step.retries + 1) : null,
  ].filter(Boolean);
  return (
    <li className="flex gap-3 py-2">
      {step.attention ? (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-foreground" aria-label={copy.trace.attention} />
      ) : (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-medium">{step.title}</p>
        <p className="text-sm text-muted-foreground">{step.summary}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {meta.join(" · ")}
          {/* Technical detail is allowed here only, in small print. */}
          <span className="ml-1">· {copy.trace.engine(step.provider)}</span>
        </p>
      </div>
    </li>
  );
}

/**
 * "How we worked this out". Loaded when opened, loaded again every time it is reopened, and
 * refreshed while open whenever `refreshKey` changes (new photo, new look, stage change).
 */
export function TracePanel({ projectId, refreshKey }: { projectId: string; refreshKey?: string }) {
  const [open, setOpen] = useState(false);
  const calls = useAiCalls(projectId, open);
  const { refetch } = calls;
  const groups = groupTrace(calls.data ?? []);
  const seenKey = useRef(refreshKey);

  // Opening (and reopening) loads the list by itself; new work while it is open loads it again.
  useEffect(() => {
    if (seenKey.current === refreshKey) return;
    seenKey.current = refreshKey;
    if (open) void refetch();
  }, [open, refreshKey, refetch]);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl border bg-card shadow-card">
      <CollapsibleTrigger className="flex w-full items-center gap-2.5 rounded-xl px-4 py-3.5 text-left text-sm font-medium outline-none hover:bg-paper/60 focus-visible:ring-2 focus-visible:ring-ring">
        <Info className="size-4 text-primary" aria-hidden="true" />
        {copy.trace.title}
        <ChevronDown className={cn("ml-auto size-4 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t px-4 pt-3 pb-4">
        <p className="mb-3 text-xs text-muted-foreground">{copy.trace.intro}</p>
        {calls.isPending ? (
          <Spinner />
        ) : calls.isError ? (
          <div className="flex flex-wrap items-center gap-3 text-sm" role="alert">
            <span className="text-destructive">{copy.trace.failed}</span>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              <RotateCcw aria-hidden="true" />
              {copy.common.tryAgain}
            </Button>
          </div>
        ) : groups.length ? (
          <ol className="space-y-4">
            {groups.map((g) => {
              const Icon = STAGE_ICON[g.stage];
              return (
                <li key={g.key}>
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <Icon className="size-4 text-primary" aria-hidden="true" />
                    {copy.trace.stages[g.stage]}
                    {g.run > 1 && <span className="font-normal text-muted-foreground">{copy.trace.again(g.run)}</span>}
                  </h3>
                  <ul className="ml-2 border-l pl-4">
                    {g.steps.map((s) => (
                      <StepRow key={s.id} step={s} />
                    ))}
                  </ul>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">{copy.trace.empty}</p>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
