import { useOutletContext } from "react-router";
import type { ProjectOut } from "@/api/types";

export interface WizardContext {
  project: ProjectOut;
}

export function useWizard(): WizardContext {
  return useOutletContext<WizardContext>();
}
