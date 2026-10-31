import { useState } from "react";
import { ChevronRight, House, ImageOff, Plus, Trash2 } from "lucide-react";
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
    <Card className="group flex h-full flex-col overflow-hidden transition-shadow hover:shadow-raised">
      <Link
        to={`/projects/${p.id}`}
        className="flex flex-1 flex-col rounded-t-xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <div className="relative aspect-[4/3] overflow-hidden bg-muted">
          {p.thumbnail_url ? (
            <img
              src={p.thumbnail_url}
              alt=""
              className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            />
          ) : (
            <div className="grid size-full place-items-center bg-[repeating-linear-gradient(135deg,var(--muted),var(--muted)_10px,var(--paper)_10px,var(--paper)_20px)] text-muted-foreground">
              <span className="flex flex-col items-center gap-1.5 text-sm">
                <ImageOff aria-hidden="true" />
                {copy.projects.noPhoto}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-1 flex-col gap-2 p-4">
          <div className="flex items-start justify-between gap-2">
            <h2 className="font-semibold leading-snug tracking-tight group-hover:text-primary">{p.name}</h2>
            <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden="true" />
          </div>
          <StatusBadge tone={status.tone} label={status.label} className="w-fit" />
          <p className="mt-auto text-xs text-muted-foreground">{copy.projects.updated(formatRelative(p.updated_at))}</p>
        </div>
      </Link>
      <div className="flex justify-end border-t px-2 py-1.5">
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:bg-destructive-soft hover:text-destructive"
          onClick={onDelete}
          aria-label={`${copy.projects.delete} ${p.name}`}
        >
          <Trash2 aria-hidden="true" />
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
    <div>
      {header}
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {projects.data.map((p) => (
          <li key={p.id}>
            <ProjectCard p={p} onDelete={() => setToDelete(p)} />
          </li>
        ))}
      </ul>
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
