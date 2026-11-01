import { useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, Clock, House, ImageOff, Plus, Search, Sparkles, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { useDeleteProject, useProjects } from "@/api/hooks";
import type { ProjectSummary } from "@/api/types";
import { copy } from "@/copy";
import { StatusBadge, type StatusTone } from "@/components/feedback";
import { PageHeader } from "@/components/layout";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/states";
import { formatRelative } from "@/lib/format";

/**
 * A plain link styled as a button (no Slot wrapper), with an explicit navigate on click so the
 * new-project screen always opens, even if another handler stops the default link behaviour.
 */
function NewProjectLink({ children, size }: { children: ReactNode; size?: "lg" }) {
  const navigate = useNavigate();
  return (
    <Link
      to="/projects/new"
      className={buttonVariants({ size })}
      onClick={(e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        navigate("/projects/new");
      }}
    >
      {children}
    </Link>
  );
}

/** What the card says about a project, from the server's stage (and its report flag). */
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

function ProjectCard({ p, onDelete }: { p: ProjectSummary; onDelete: () => void }) {
  const status = projectStatus(p);
  return (
    <Card className="group flex h-full flex-col overflow-hidden rounded-2xl border border-border/80 bg-card transition-all duration-300 hover:-translate-y-1 hover:border-primary/30 hover:shadow-raised">
      <Link
        to={`/projects/${p.id}`}
        className="flex flex-1 flex-col rounded-t-2xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="relative aspect-[4/3] overflow-hidden bg-muted/60">
          {p.thumbnail_url ? (
            <>
              <img
                src={p.thumbnail_url}
                alt=""
                className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
            </>
          ) : (
            <div className="grid size-full place-items-center bg-[repeating-linear-gradient(135deg,var(--muted),var(--muted)_10px,var(--paper)_10px,var(--paper)_20px)] text-muted-foreground">
              <span className="flex flex-col items-center gap-2 text-sm font-medium">
                <ImageOff aria-hidden="true" className="size-5 opacity-60" />
                {copy.projects.noPhoto}
              </span>
            </div>
          )}
          <div className="absolute left-3 top-3">
            <StatusBadge tone={status.tone} label={status.label} className="shadow-sm backdrop-blur-md" />
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-2 p-4">
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-base font-semibold leading-snug tracking-tight text-foreground transition-colors group-hover:text-primary">
              {p.name}
            </h2>
            <ChevronRight className="mt-0.5 size-4.5 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary" aria-hidden="true" />
          </div>
          <p className="mt-auto text-xs font-medium text-muted-foreground">{copy.projects.updated(formatRelative(p.updated_at))}</p>
        </div>
      </Link>
      <div className="flex justify-end border-t border-border/60 bg-muted/20 px-3 py-2">
        <Button
          variant="ghost"
          size="sm"
          className="h-8 rounded-lg text-xs font-medium text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          onClick={onDelete}
          aria-label={`${copy.projects.delete} ${p.name}`}
        >
          <Trash2 aria-hidden="true" className="size-3.5" />
          {copy.projects.delete}
        </Button>
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

  const stats = useMemo(() => {
    if (!projects.data) return { total: 0, ready: 0, inProgress: 0 };
    const total = projects.data.length;
    const ready = projects.data.filter((p) => p.report_ready).length;
    const inProgress = total - ready;
    return { total, ready, inProgress };
  }, [projects.data]);

  const header = (
    <PageHeader
      className="mb-6 sm:mb-8"
      title={copy.projects.title}
      description={projects.data?.length ? copy.projects.intro : undefined}
      aside={
        <NewProjectLink>
          <Plus aria-hidden="true" />
          {copy.projects.newProject}
        </NewProjectLink>
      }
    />
  );

  if (projects.isPending) {
    return (
      <div>
        {header}
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
          <span className="sr-only" role="status">
            {copy.common.loading}
          </span>
          {[0, 1, 2].map((i) => (
            <div key={i} className="overflow-hidden rounded-xl border bg-card" aria-hidden="true">
              <Skeleton className="aspect-[4/3] rounded-none" />
              <div className="space-y-2.5 p-4">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-5 w-1/3 rounded-full" />
                <Skeleton className="h-3 w-1/4" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (projects.isError) {
    return (
      <div>
        {header}
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      </div>
    );
  }
  if (!projects.data.length) {
    return (
      <div>
        {header}
        <EmptyState
          icon={<House />}
          title={copy.projects.emptyTitle}
          body={copy.projects.emptyBody}
          action={<NewProjectLink size="lg">{copy.projects.emptyCta}</NewProjectLink>}
        />
      </div>
    );
  }

  const confirmDelete = () => {
    if (!toDelete) return;
    del.mutate(toDelete.id, {
      onSuccess: () => toast.success(copy.projects.deleted),
      onSettled: () => setToDelete(null),
    });
  };

  return (
    <div className="space-y-6">
      {header}

      {/* KPI Stats Overview */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="flex items-center gap-4 rounded-xl border border-border/80 bg-card p-4 shadow-sm">
          <div className="grid size-11 place-items-center rounded-xl bg-primary/10 text-primary">
            <Sparkles className="size-5" />
          </div>
          <div>
            <p className="text-2xl font-bold tracking-tight text-foreground">{stats.total}</p>
            <p className="text-xs font-medium text-muted-foreground">Total Exterior Projects</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-xl border border-border/80 bg-card p-4 shadow-sm">
          <div className="grid size-11 place-items-center rounded-xl bg-amber-500/10 text-amber-600">
            <Clock className="size-5" />
          </div>
          <div>
            <p className="text-2xl font-bold tracking-tight text-foreground">{stats.inProgress}</p>
            <p className="text-xs font-medium text-muted-foreground">In Design & Analysis</p>
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-xl border border-border/80 bg-card p-4 shadow-sm">
          <div className="grid size-11 place-items-center rounded-xl bg-emerald-500/10 text-emerald-600">
            <CheckCircle2 className="size-5" />
          </div>
          <div>
            <p className="text-2xl font-bold tracking-tight text-foreground">{stats.ready}</p>
            <p className="text-xs font-medium text-muted-foreground">Cost Estimates Ready</p>
          </div>
        </div>
      </div>

      {/* Search and Filters Bar */}
      {projects.data.length > 2 && (
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search projects by name…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-input bg-card py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      )}

      {/* Projects Grid */}
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {filteredProjects.map((p) => (
          <li key={p.id}>
            <ProjectCard p={p} onDelete={() => setToDelete(p)} />
          </li>
        ))}
      </ul>

      {filteredProjects.length === 0 && (
        <div className="rounded-xl border border-dashed py-12 text-center text-sm text-muted-foreground">
          No projects matching &ldquo;{searchQuery}&rdquo;
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
