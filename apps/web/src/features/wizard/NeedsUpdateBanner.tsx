import { ArrowRight, RefreshCw } from "lucide-react";
import { Link, useLocation } from "react-router";
import type { DesignOut, ProjectOut } from "@/api/types";
import { copy } from "@/copy";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { StepSlug } from "./steps";

export interface NeedsUpdate {
  text: string;
  action: string;
  step: StepSlug;
  /** Steps whose own screen already explains this (with its own action), so the banner stays away. */
  quietOn: StepSlug[];
}

/**
 * One "Needs update" message with one next action, from the staleness flags
 *. The most upstream change wins.
 */
export function needsUpdateMessage(
  project: Pick<ProjectOut, "stage" | "regions_approved" | "scale_confirmed">,
  designs: DesignOut[],
  active: DesignOut | null,
): NeedsUpdate | null {
  if (project.stage === "regions_review" && !project.regions_approved && designs.length > 0) {
    return { text: copy.stale.parts, action: copy.stale.partsAction, step: "parts", quietOn: [] };
  }
  if (project.stage === "scale_review" && designs.length > 0) {
    // The size check screen asks for exactly this, so the banner would only repeat it there.
    return { text: copy.stale.size, action: copy.stale.sizeAction, step: "size", quietOn: ["size"] };
  }
  if (project.stage !== "designing" || !active) return null;
  if (active.render?.stale) {
    // "Your new look" shows its own out-of-date panel with a direct "create again" button.
    return { text: copy.stale.look, action: copy.stale.lookAction, step: "materials", quietOn: ["look"] };
  }
  if (active.estimate_stale) {
    return { text: copy.stale.estimate, action: copy.stale.estimateAction, step: "cost", quietOn: [] };
  }
  return null;
}

export function NeedsUpdateBanner({
  message,
  projectId,
  current,
}: {
  message: NeedsUpdate | null;
  projectId: string;
  current: StepSlug | null;
}) {
  const location = useLocation();
  if (!message || (current && message.quietOn.includes(current))) return null;
  const here = current === message.step;
  return (
    <Alert variant="warning" className="flex-wrap items-center sm:flex-nowrap" data-testid="needs-update">
      <RefreshCw aria-hidden="true" />
      <p className="min-w-0 flex-1 basis-56 font-medium">{message.text}</p>
      {!here && (
        <Button asChild size="sm" variant="warning" className="w-full sm:w-auto">
          <Link to={`/projects/${projectId}/${message.step}${location.search}`}>
            {message.action}
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      )}
    </Alert>
  );
}
