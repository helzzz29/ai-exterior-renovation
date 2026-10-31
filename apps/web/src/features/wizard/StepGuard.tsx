import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useWizard } from "./context";
import { maxReachableStep, stepForStage } from "./steps";

/** Sends the user to the right step when they open one that isn't available yet. */
export function StepGuard({ step, children }: { step: number; children: ReactNode }) {
  const { project } = useWizard();
  const location = useLocation();
  if (step > maxReachableStep(project.stage)) {
    return <Navigate to={`/projects/${project.id}/${stepForStage(project.stage)}${location.search}`} replace />;
  }
  return <>{children}</>;
}
