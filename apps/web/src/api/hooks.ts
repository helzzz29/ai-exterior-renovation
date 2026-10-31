/** TanStack Query hooks for every endpoint the app uses. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { POLL_MS } from "@/lib/config";
import { api, ApiError, unwrap } from "./client";
import type {
  AICallOut,
  Assignment,
  DesignOut,
  EstimateOut,
  JobOut,
  MaterialAdviceOut,
  MaterialOut,
  Measurements,
  PhotoUploadResult,
  ProjectOut,
  ProjectSummary,
  RatesOut,
  RatesPut,
  RegionIn,
  RegionsOut,
  RenderOut,
  RenderStarted,
  ReportOut,
  ScaleConfirm,
  ScaleOut,
  UserOut,
} from "./types";

export const qk = {
  me: ["me"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  job: (id: string) => ["job", id] as const,
  regions: (id: string) => ["regions", id] as const,
  scale: (id: string) => ["scale", id] as const,
  materials: ["materials"] as const,
  advice: (id: string) => ["advice", id] as const,
  designs: (id: string) => ["designs", id] as const,
  render: (designId: string) => ["render", designId] as const,
  estimate: (designId: string) => ["estimate", designId] as const,
  rates: (id: string) => ["rates", id] as const,
  reports: (designId: string) => ["reports", designId] as const,
  aiCalls: (id: string) => ["ai-calls", id] as const,
};

const pp = (project_id: string) => ({ params: { path: { project_id } } });
const dp = (design_id: string) => ({ params: { path: { design_id } } });

// ------------------------------------------------------------------ auth

export function useMe() {
  return useQuery<UserOut | null>({
    queryKey: qk.me,
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/auth/me"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin(kind: "login" | "register") {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: (body: { email: string; password: string }) =>
      unwrap(
        kind === "login"
          ? api.POST("/api/auth/login", { body })
          : api.POST("/api/auth/register", { body }),
      ),
    onSuccess: (user) => {
      qc.clear();
      qc.setQueryData(qk.me, user);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(qk.me, null);
    },
  });
}

// ------------------------------------------------------------------ projects

export function useProjects() {
  return useQuery<ProjectSummary[]>({
    queryKey: qk.projects,
    queryFn: () => unwrap(api.GET("/api/projects")),
  });
}

export function useProject(projectId: string) {
  return useQuery<ProjectOut>({
    queryKey: qk.project(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}", pp(projectId))),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; measurements: Measurements }) =>
      unwrap(api.POST("/api/projects", { body })),
    onSuccess: (p) => {
      qc.setQueryData(qk.project(p.id), p);
      void qc.invalidateQueries({ queryKey: qk.projects });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      unwrap(api.DELETE("/api/projects/{project_id}", pp(projectId))),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }),
  });
}

function useSetProject() {
  const qc = useQueryClient();
  return (p: ProjectOut) => {
    qc.setQueryData(qk.project(p.id), p);
    void qc.invalidateQueries({ queryKey: qk.projects });
  };
}

// ------------------------------------------------------------------ jobs

export function isJobFinished(job: JobOut | undefined | null): boolean {
  return !!job && (job.status === "done" || job.status === "failed");
}

/** Poll a background job until it is done or failed. */
export function useJob(jobId: string | null | undefined) {
  return useQuery<JobOut>({
    queryKey: qk.job(jobId ?? "none"),
    queryFn: () => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: jobId! } } })),
    enabled: !!jobId,
    refetchInterval: (q) => (isJobFinished(q.state.data) ? false : POLL_MS),
  });
}

// ------------------------------------------------------------------ photo

export function useUploadPhoto(projectId: string) {
  const setProject = useSetProject();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (file: File): Promise<PhotoUploadResult> => {
      const form = new FormData();
      form.append("file", file, file.name);
      return unwrap(
        api.POST("/api/projects/{project_id}/photo", {
          ...pp(projectId),
          // The generated type says string; the real body is multipart form data.
          body: form as unknown as { file: string },
          bodySerializer: (b) => b as unknown as FormData,
        }),
      );
    },
    onSuccess: (res) => setProject(res.project),
  });
}

export function useContinuePhoto(projectId: string) {
  const setProject = useSetProject();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/projects/{project_id}/photo/continue", pp(projectId))),
    onSuccess: setProject,
  });
}

// ------------------------------------------------------------------ regions

export function useRegions(projectId: string, enabled = true) {
  return useQuery<RegionsOut>({
    queryKey: qk.regions(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}/regions", pp(projectId))),
    enabled,
  });
}

export function useSaveRegions(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (regions: RegionIn[]) =>
      unwrap(api.PUT("/api/projects/{project_id}/regions", { ...pp(projectId), body: { regions } })),
    onSuccess: (out) => {
      qc.setQueryData(qk.regions(projectId), out);
      void qc.invalidateQueries({ queryKey: qk.project(projectId) });
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

export function useApproveRegions(projectId: string) {
  const qc = useQueryClient();
  const setProject = useSetProject();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/projects/{project_id}/regions/approve", pp(projectId))),
    onSuccess: (p) => {
      setProject(p);
      void qc.invalidateQueries({ queryKey: qk.regions(projectId) });
      void qc.invalidateQueries({ queryKey: qk.scale(projectId) });
      void qc.invalidateQueries({ queryKey: qk.advice(projectId) });
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
      void qc.invalidateQueries({ queryKey: ["estimate"] });
    },
  });
}

// ------------------------------------------------------------------ scale

export function useScale(projectId: string, enabled = true) {
  return useQuery<ScaleOut>({
    queryKey: qk.scale(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}/scale", pp(projectId))),
    enabled,
  });
}

export function useConfirmScale(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ScaleConfirm) => {
      const scale = await unwrap(api.POST("/api/projects/{project_id}/scale/confirm", { ...pp(projectId), body }));
      // The stage moves on after a size check; load it before the screen moves to the next step.
      const project = await unwrap(api.GET("/api/projects/{project_id}", pp(projectId)));
      return { scale, project };
    },
    onSuccess: ({ scale, project }) => {
      qc.setQueryData(qk.scale(projectId), scale);
      qc.setQueryData(qk.project(projectId), project);
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
      void qc.invalidateQueries({ queryKey: ["estimate"] });
    },
  });
}

// ------------------------------------------------------------------ materials & designs

export function useMaterials() {
  return useQuery<MaterialOut[]>({
    queryKey: qk.materials,
    queryFn: () => unwrap(api.GET("/api/materials")),
    staleTime: 10 * 60_000,
  });
}

export function useMaterialAdvice(projectId: string) {
  return useQuery<MaterialAdviceOut>({
    queryKey: qk.advice(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}/material-advice", pp(projectId))),
    refetchInterval: (q) => (q.state.data?.ready ? false : POLL_MS),
  });
}

export function useDesigns(projectId: string, enabled = true) {
  return useQuery<DesignOut[]>({
    queryKey: qk.designs(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}/designs", pp(projectId))),
    enabled,
  });
}

export function useCreateDesign(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; copy_from?: string | null }) =>
      unwrap(api.POST("/api/projects/{project_id}/designs", { ...pp(projectId), body })),
    onSuccess: (d) => {
      qc.setQueryData<DesignOut[]>(qk.designs(projectId), (old) =>
        old ? [...old.filter((x) => x.id !== d.id), d] : [d],
      );
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

export function useRenameDesign(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ designId, name }: { designId: string; name: string }) =>
      unwrap(api.PATCH("/api/designs/{design_id}", { ...dp(designId), body: { name } })),
    onSuccess: (d) => {
      qc.setQueryData<DesignOut[]>(qk.designs(projectId), (old) => old?.map((x) => (x.id === d.id ? d : x)));
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

export function useDeleteDesign(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (designId: string) => unwrap(api.DELETE("/api/designs/{design_id}", dp(designId))),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.designs(projectId) }),
  });
}

export function useSaveAssignments(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ designId, assignments }: { designId: string; assignments: Assignment[] }) =>
      unwrap(api.PUT("/api/designs/{design_id}/assignments", { ...dp(designId), body: { assignments } })),
    onSuccess: (d) => {
      qc.setQueryData<DesignOut[]>(qk.designs(projectId), (old) =>
        old?.map((x) => (x.id === d.id ? d : x)),
      );
      void qc.invalidateQueries({ queryKey: qk.estimate(d.id) });
      void qc.invalidateQueries({ queryKey: qk.render(d.id) });
    },
  });
}

/**
 * Save material choices while the screen is closing. `keepalive` lets the request finish even if
 * the page itself is being unloaded.
 */
export function putAssignmentsKeepalive(designId: string, assignments: Assignment[]): Promise<unknown> {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return globalThis
    .fetch(`${origin}/api/designs/${encodeURIComponent(designId)}/assignments`, {
      method: "PUT",
      keepalive: true,
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assignments }),
    })
    .catch(() => undefined);
}

// ------------------------------------------------------------------ renders

export function isRenderBusy(r: RenderOut | null | undefined): boolean {
  return !!r && (r.status === "queued" || r.status === "running");
}

export function useRender(designId: string | null | undefined) {
  return useQuery<RenderOut | null>({
    queryKey: qk.render(designId ?? "none"),
    queryFn: async () => (await unwrap(api.GET("/api/designs/{design_id}/render", dp(designId!)))) ?? null,
    enabled: !!designId,
    refetchInterval: (q) => (isRenderBusy(q.state.data) ? POLL_MS : false),
  });
}

export function useStartRender(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ designId, note }: { designId: string; note?: string | null }) =>
      unwrap(api.POST("/api/designs/{design_id}/render", { ...dp(designId), body: { note: note ?? null } })),
    onSuccess: (res: RenderStarted, vars) => {
      qc.setQueryData(qk.render(vars.designId), res.render);
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

export function useAcceptRender(projectId: string, designId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (renderId: string) =>
      unwrap(api.POST("/api/renders/{render_id}/accept", { params: { path: { render_id: renderId } } })),
    onSuccess: (r) => {
      qc.setQueryData(qk.render(designId), r);
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

// ------------------------------------------------------------------ estimates & rates

export function useEstimate(designId: string | null | undefined) {
  return useQuery<EstimateOut>({
    queryKey: qk.estimate(designId ?? "none"),
    queryFn: () => unwrap(api.GET("/api/designs/{design_id}/estimate", dp(designId!))),
    enabled: !!designId,
    placeholderData: (prev) => prev,
  });
}

export function useFinaliseEstimate(projectId: string, designId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/designs/{design_id}/estimate/finalise", dp(designId))),
    onSuccess: (e) => {
      qc.setQueryData(qk.estimate(designId), e);
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

export function useRates(projectId: string) {
  return useQuery<RatesOut>({
    queryKey: qk.rates(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}/rates", pp(projectId))),
  });
}

export function useSaveRates(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RatesPut) =>
      unwrap(api.PUT("/api/projects/{project_id}/rates", { ...pp(projectId), body })),
    onSuccess: (rates) => {
      qc.setQueryData(qk.rates(projectId), rates);
      void qc.invalidateQueries({ queryKey: ["estimate"] });
      void qc.invalidateQueries({ queryKey: qk.designs(projectId) });
    },
  });
}

/** Save prices while the page is closing (same idea as `putAssignmentsKeepalive`). */
export function putRatesKeepalive(projectId: string, body: RatesPut): Promise<unknown> {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return globalThis
    .fetch(`${origin}/api/projects/${encodeURIComponent(projectId)}/rates`, {
      method: "PUT",
      keepalive: true,
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    .catch(() => undefined);
}

// ------------------------------------------------------------------ reports

export function useReports(designId: string | null | undefined) {
  return useQuery<ReportOut[]>({
    queryKey: qk.reports(designId ?? "none"),
    queryFn: () => unwrap(api.GET("/api/designs/{design_id}/reports", dp(designId!))),
    enabled: !!designId,
  });
}

export function useCreateReport() {
  return useMutation({
    mutationFn: (designId: string) => unwrap(api.POST("/api/designs/{design_id}/report", dp(designId))),
  });
}

// ------------------------------------------------------------------ trace

export function useAiCalls(projectId: string, enabled: boolean) {
  return useQuery<AICallOut[]>({
    queryKey: qk.aiCalls(projectId),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}/ai-calls", pp(projectId))),
    enabled,
  });
}
