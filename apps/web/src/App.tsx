import { Navigate, Route, Routes } from "react-router";
import { AppShell, RequireAuth } from "@/components/AppShell";
import { NotFound } from "@/components/states";
import { AuthPage } from "@/features/auth/AuthPage";
import { SIGNUP_OPEN } from "@/lib/config";
import { CreateProjectPage } from "@/features/projects/CreateProjectPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { WizardIndex, WizardLayout } from "@/features/wizard/WizardLayout";
import { PhotoStep } from "@/features/photo/PhotoStep";
import { RegionsStep } from "@/features/regions/RegionsStep";
import { ScaleStep } from "@/features/scale/ScaleStep";
import { MaterialsStep } from "@/features/materials/MaterialsStep";
import { RenderStep } from "@/features/render/RenderStep";
import { EstimateStep } from "@/features/estimate/EstimateStep";
import { StepGuard } from "@/features/wizard/StepGuard";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage key="login" mode="login" />} />
      <Route
        path="/register"
        element={SIGNUP_OPEN ? <AuthPage key="register" mode="register" /> : <Navigate to="/login" replace />}
      />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<ProjectsPage />} />
        <Route path="projects" element={<Navigate to="/" replace />} />
        <Route path="projects/new" element={<CreateProjectPage />} />
        <Route path="projects/:projectId" element={<WizardLayout />}>
          <Route index element={<WizardIndex />} />
          <Route path="photo" element={<PhotoStep />} />
          <Route path="parts" element={<StepGuard step={1}><RegionsStep /></StepGuard>} />
          <Route path="size" element={<StepGuard step={2}><ScaleStep /></StepGuard>} />
          <Route path="materials" element={<StepGuard step={3}><MaterialsStep /></StepGuard>} />
          <Route path="look" element={<StepGuard step={4}><RenderStep /></StepGuard>} />
          <Route path="cost" element={<StepGuard step={5}><EstimateStep /></StepGuard>} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
