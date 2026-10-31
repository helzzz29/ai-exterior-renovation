import type { ProjectStage } from "@/api/types";
import { copy } from "@/copy";

export const STEP_SLUGS = ["photo", "parts", "size", "materials", "look", "cost"] as const;
export type StepSlug = (typeof STEP_SLUGS)[number];

export const STEPS = STEP_SLUGS.map((slug, i) => ({ slug, index: i, title: copy.stepper.steps[i] }));

/** The furthest step the user may open, decided by the project's stage from the API. */
export function maxReachableStep(stage: ProjectStage): number {
  switch (stage) {
    case "upload":
    case "analyzing":
    case "photo_rejected":
    case "photo_warning":
      return 0;
    case "regions_review":
      return 1;
    case "scale_review":
      return 2;
    case "designing":
      return 5;
  }
}

/** Where to send the user when they open a project. */
export function stepForStage(stage: ProjectStage): StepSlug {
  switch (stage) {
    case "regions_review":
      return "parts";
    case "scale_review":
      return "size";
    case "designing":
      return "materials";
    default:
      return "photo";
  }
}
