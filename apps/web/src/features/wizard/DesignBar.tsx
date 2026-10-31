import { useId } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useLocation } from "react-router";
import type { DesignOut } from "@/api/types";
import { copy } from "@/copy";
import { StatusBadge } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { estimateState, lookState } from "./progress";
import { STEPS, type StepSlug } from "./steps";

const LOOK_TONE = { none: "neutral", busy: "progress", ready: "attention", accepted: "done", stale: "stale", failed: "attention" } as const;
const ESTIMATE_TONE = { draft: "neutral", final: "done", stale: "stale" } as const;

/**
 * Which design steps 5 and 6 are about, a way to switch to another one, and where it stands for
 * the report: its new look and its estimate, straight from the server's flags.
 */
export function DesignBar({
  designs,
  active,
  onSelect,
}: {
  designs: DesignOut[];
  active: DesignOut;
  onSelect: (id: string) => void;
}) {
  const id = useId();
  const look = lookState(active.render);
  const est = estimateState(active);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border bg-card px-4 py-3 shadow-card" data-testid="design-bar">
      <div className="flex min-w-0 items-center gap-2">
        <label htmlFor={id} className="text-sm font-medium text-muted-foreground">
          {copy.design.label}
        </label>
        {designs.length > 1 ? (
          <select
            id={id}
            value={active.id}
            onChange={(e) => onSelect(e.target.value)}
            className="h-10 min-w-0 max-w-64 truncate rounded-md border border-input bg-card px-2.5 text-sm font-semibold shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30 sm:h-9"
          >
            {designs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        ) : (
          <output id={id} className="truncate text-sm font-semibold">
            {active.name}
          </output>
        )}
      </div>
      <dl className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <div className="flex items-center gap-2">
          <dt className="text-muted-foreground">{copy.design.look}</dt>
          <dd>
            <StatusBadge tone={LOOK_TONE[look]} label={copy.design.lookState[look]} />
          </dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="text-muted-foreground">{copy.design.estimate}</dt>
          <dd>
            <StatusBadge tone={ESTIMATE_TONE[est]} label={copy.design.estimateState[est]} />
          </dd>
        </div>
      </dl>
    </div>
  );
}

/** "Back" to the step before this one, keeping the chosen design. Never skips a gate: earlier steps are always open. */
export function BackLink({ projectId, from }: { projectId: string; from: StepSlug }) {
  const { search } = useLocation();
  const index = STEPS.findIndex((s) => s.slug === from);
  if (index <= 0) return null;
  const prev = STEPS[index - 1];
  return (
    <Button asChild variant="ghost" className="-ml-2">
      <Link to={`/projects/${projectId}/${prev.slug}${search}`} title={prev.title}>
        <ArrowLeft aria-hidden="true" />
        {copy.common.back}
      </Link>
    </Button>
  );
}
