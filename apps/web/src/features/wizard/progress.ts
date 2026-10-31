import type { DesignOut, ProjectOut, RenderOut } from "@/api/types";
import { copy } from "@/copy";
import type { StatusTone } from "@/components/feedback";
import { maxReachableStep } from "./steps";

/**
 * What each step of the wizard really is, from the project and the active design: a tick means
 * the work is done and still up to date, never just "the user has gone past it".
 */
export type StepStatus = "done" | "progress" | "attention" | "ready" | "stale" | "todo" | "locked";

export const STATUS_TONE: Record<StepStatus, StatusTone> = {
  done: "done",
  progress: "progress",
  attention: "attention",
  ready: "attention",
  stale: "stale",
  todo: "neutral",
  locked: "locked",
};

export const STATUS_LABEL: Record<StepStatus, string> = {
  done: copy.stepper.status.done,
  progress: copy.stepper.status.progress,
  attention: copy.stepper.status.attention,
  ready: copy.stepper.status.ready,
  stale: copy.stepper.status.stale,
  todo: copy.stepper.status.todo,
  locked: copy.stepper.status.locked,
};

type ProjectBits = Pick<ProjectOut, "stage" | "photo" | "regions_approved" | "scale_confirmed">;
type DesignBits = Pick<DesignOut, "assignments" | "render" | "estimate_finalised" | "estimate_stale">;

export type LookState = "none" | "busy" | "ready" | "accepted" | "stale" | "failed";

/** The state of a design's new look, in the words the readiness summary uses. */
export function lookState(render: Pick<RenderOut, "status" | "stale"> | null | undefined): LookState {
  if (!render) return "none";
  if (render.status === "queued" || render.status === "running") return "busy";
  if (render.status === "failed") return "failed";
  if (render.stale) return "stale";
  return render.status === "accepted" ? "accepted" : "ready";
}

export type EstimateState = "draft" | "final" | "stale";

/** Finalised and current, finalised but changed since, or not finalised yet. */
export function estimateState(d: Pick<DesignOut, "estimate_finalised" | "estimate_stale">): EstimateState {
  if (d.estimate_finalised && d.estimate_stale) return "stale";
  return d.estimate_finalised ? "final" : "draft";
}

export function stepStatuses(project: ProjectBits, active: DesignBits | null): StepStatus[] {
  const reach = maxReachableStep(project.stage);
  const lockedOr = (i: number, s: StepStatus): StepStatus => (i > reach ? "locked" : s);
  const past = project.stage === "regions_review" || project.stage === "scale_review" || project.stage === "designing";

  const photo: StepStatus =
    past && project.photo
      ? "done"
      : project.stage === "analyzing"
        ? "progress"
        : project.stage === "photo_warning" || project.stage === "photo_rejected"
          ? "attention"
          : "todo";

  const look = lookState(active?.render);
  const lookStatus: StepStatus =
    look === "none" ? "todo" : look === "busy" ? "progress" : look === "ready" ? "ready" : look === "accepted" ? "done" : look === "stale" ? "stale" : "attention";

  const est = active ? estimateState(active) : "draft";

  return [
    photo,
    lockedOr(1, project.regions_approved ? "done" : "attention"),
    lockedOr(2, project.scale_confirmed ? "done" : "attention"),
    lockedOr(3, active && active.assignments.length > 0 ? "done" : "todo"),
    lockedOr(4, lookStatus),
    lockedOr(5, est === "final" ? "done" : est === "stale" ? "stale" : "todo"),
  ];
}
