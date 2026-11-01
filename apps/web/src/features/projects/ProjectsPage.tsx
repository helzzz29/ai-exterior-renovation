import { useMemo, useState } from "react";
import {
  ArrowRight,
  House,
  ImageOff,
  Plus,
  Search,
  X,
} from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import { useDeleteProject, useProjects } from "@/api/hooks";
import type { ProjectSummary } from "@/api/types";
import { copy } from "@/copy";
import type { StatusTone } from "@/components/feedback";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/states";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export function projectStatus(p: Pick<ProjectSummary, "stage" | "report_ready">): { tone: StatusTone; label: string } {
  if (p.report_ready) return { tone: "done", label: copy.projects.reportReady };
  const label = copy.projects.stage[p.stage] ?? "";
  switch (p.stage) {
    case "photo_rejected":
    case "photo_warning":
      return { tone: "attention", label };
    case "upload":
      return { tone: "neutral", label };
    default:
      return { tone: "progress", label };
  }
}

function estimateBadge(p: ProjectSummary): string | null {
  if (p.report_ready) return "Estimate Ready";
  if (p.stage === "designing") return "In Studio";
  return null;
}

function ProjectCard({ p, onDelete }: { p: ProjectSummary; onDelete: () => void }) {
  const status = projectStatus(p);
  const badge = estimateBadge(p);

  return (
    <Card className="group flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white transition-all duration-300 hover:-translate-y-1 hover:border-emerald-400 hover:shadow-md">
      <Link
        to={`/projects/${p.id}`}
        className="flex flex-1 flex-col rounded-t-2xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="relative aspect-[16/10] overflow-hidden bg-slate-100">
          {p.thumbnail_url ? (
            <>
              <img
                src={p.thumbnail_url}
                alt=""
                className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-70" />
            </>
          ) : (
            <div className="grid size-full place-items-center bg-[repeating-linear-gradient(135deg,#f8fafc,#f8fafc_10px,#f1f5f9_10px,#f1f5f9_20px)] text-slate-400">
              <span className="flex flex-col items-center gap-2 text-sm font-medium">
                <ImageOff aria-hidden="true" className="size-5 opacity-60" />
                {copy.projects.noPhoto}
              </span>
            </div>
          )}

          {/* Status badge top-left */}
          <div className="absolute left-3 top-3">
            <span
              className={cn(
                "inline-flex items-center rounded-lg px-2.5 py-1 text-[11px] font-semibold tracking-tight shadow-xs backdrop-blur-md",
                p.report_ready
                  ? "bg-white/95 text-emerald-800 border border-emerald-300"
                  : "bg-white/95 text-slate-700 border border-slate-200",
              )}
            >
              {status.label}
            </span>
          </div>

          {/* Badge bottom-right */}
          {badge && (
            <div className="absolute right-3 bottom-3">
              <span className="inline-flex items-center rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-bold tracking-tight text-white shadow-xs">
                {badge}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-1.5 p-4">
          <h2 className="text-sm font-bold leading-snug tracking-tight text-slate-900 transition-colors group-hover:text-emerald-700 line-clamp-1">
            {p.name}
          </h2>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>{copy.projects.updated(formatRelative(p.updated_at))}</span>
          </div>
        </div>
      </Link>

      {/* Action buttons row matching Picture 2 */}
      <div className="flex items-center gap-2 border-t border-slate-100 bg-slate-50/70 px-3 py-2.5">
        <Link
          to={`/projects/${p.id}`}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 transition-colors"
        >
          <span>Open Studio</span>
          <ArrowRight className="size-3 text-emerald-100" />
        </Link>
        <Link
          to={`/projects/${p.id}/cost`}
          className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
          title="Bill of Quantities / Cost Report"
        >
          BOQ
        </Link>
        <button
          type="button"
          onClick={onDelete}
          className="grid size-8 place-items-center rounded-lg border border-transparent text-slate-400 hover:border-red-200 hover:bg-red-50 hover:text-red-600 transition-colors"
          aria-label={`${copy.projects.delete} ${p.name}`}
          title={copy.projects.delete}
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
    </Card>
  );
}

export function ProjectsPage() {
  const projects = useProjects();
  const del = useDeleteProject();
  const [toDelete, setToDelete] = useState<ProjectSummary | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredProjects = useMemo(() => {
    if (!projects.data) return [];
    if (!searchQuery.trim()) return projects.data;
    const q = searchQuery.toLowerCase();
    return projects.data.filter((p) => p.name.toLowerCase().includes(q));
  }, [projects.data, searchQuery]);

  const workflowSteps = [
    {
      step: "Step 1",
      title: "Upload House Image",
      desc: "Validate photo quality & perspective",
    },
    {
      step: "Step 2",
      title: "AI Facade Detection",
      desc: "Segment walls, windows, pillars & balconies",
    },
    {
      step: "Step 3",
      title: "Apply Materials",
      desc: "Surface-by-surface editing with Day & Night lighting",
    },
    {
      step: "Step 4",
      title: "Confirm Measurements",
      desc: "Set scale using known dimensions; correct areas",
    },
    {
      step: "Step 5",
      title: "Smart Budget Engine",
      desc: "Recalculate quantities, wastage, labor & total",
    },
    {
      step: "Step 6",
      title: "Compare & Export",
      desc: "Download contractor-ready PDF & CSV report",
    },
  ];

  if (projects.isPending) {
    return (
      <div className="space-y-6" aria-busy="true">
        <span className="sr-only" role="status">
          {copy.common.loading}
        </span>
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-10 w-36 rounded-xl" />
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="overflow-hidden rounded-2xl border bg-card" aria-hidden="true">
              <Skeleton className="aspect-[16/10] rounded-none" />
              <div className="space-y-2.5 p-4">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (projects.isError) {
    return <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />;
  }

  const confirmDelete = () => {
    if (!toDelete) return;
    del.mutate(toDelete.id, {
      onSuccess: () => toast.success(copy.projects.deleted),
      onSettled: () => setToDelete(null),
    });
  };

  return (
    <div className="space-y-8">
      {/* Top Header Section matching Picture 2 */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-slate-900 sm:text-3xl">
            My projects
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Select an existing house renovation project or start a new exterior redesign.
          </p>
        </div>
        <Link
          to="/projects/new"
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-emerald-700 transition-all"
        >
          <Plus className="size-4" />
          <span>{copy.projects.newProject}</span>
        </Link>
      </div>

      {/* HOW RENOVA AI WORKS — 6 SIMPLE STEPS */}
      <section
        aria-label="How Renova AI Works"
        className="rounded-2xl border border-slate-200/90 bg-white p-4 sm:p-5 shadow-xs"
      >
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
          How Renova AI Works &mdash; 6 Simple Steps
        </p>
        <div className="mt-3.5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {workflowSteps.map((s) => (
            <div
              key={s.step}
              className="rounded-xl border border-slate-200 bg-slate-50/50 p-3 transition-colors hover:border-emerald-300 hover:bg-emerald-50/30"
            >
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                {s.step}
              </span>
              <p className="mt-1 text-xs font-bold leading-tight text-slate-900">
                {s.title}
              </p>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">
                {s.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Projects Grid or Empty State Matching Picture 2 */}
      {projects.data.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white p-12 sm:p-16 text-center">
          <div className="mb-4 grid size-16 place-items-center rounded-2xl bg-emerald-50 text-emerald-700">
            <House className="size-8" />
          </div>
          <h2 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
            No projects yet
          </h2>
          <p className="mt-2 max-w-md text-sm text-slate-500">
            Start with one photo of the front of your house. We'll take it from there.
          </p>
          <div className="mt-6">
            <Link
              to="/projects/new"
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-emerald-700 transition-all"
            >
              <Plus className="size-4" />
              <span>Start my first project</span>
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {projects.data.length > 2 && (
            <div className="relative max-w-sm">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Filter projects by name…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-xs placeholder:text-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          )}

          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {filteredProjects.map((p) => (
              <li key={p.id}>
                <ProjectCard p={p} onDelete={() => setToDelete(p)} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <ConfirmDialog
        open={!!toDelete}
        title={toDelete ? copy.projects.deleteTitle(toDelete.name) : ""}
        body={copy.projects.deleteBody}
        confirmLabel={copy.projects.deleteButton}
        cancelLabel={copy.projects.keepProject}
        pending={del.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
