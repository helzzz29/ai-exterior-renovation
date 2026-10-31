import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Circle, Lightbulb, Loader2, RotateCcw, XCircle } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { ApiError, errorMessage } from "@/api/client";
import { isJobFinished, qk, useContinuePhoto, useJob, useUploadPhoto } from "@/api/hooks";
import type { JobOut, ProjectOut } from "@/api/types";
import { copy } from "@/copy";
import { PageHeader } from "@/components/layout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useWizard } from "@/features/wizard/context";
import { PhotoDropzone } from "./PhotoDropzone";

export interface UploadProblem {
  title: string;
  message: string;
}

/** A title that matches what went wrong: the file, the connection, the daily limit, or the photo itself. */
export function uploadProblem(err: unknown): UploadProblem {
  const message = errorMessage(err);
  if (err instanceof ApiError) {
    if (err.status === 0 || err.status >= 500) return { title: copy.photo.problemTitles.network, message };
    if (err.status === 429 || err.code === "daily_limit") return { title: copy.photo.problemTitles.limit, message };
    if (err.code === "unsupported_type") return { title: copy.photo.problemTitles.type, message };
  }
  return { title: copy.photo.problemTitle, message };
}

function AnalysisProgress({ job, photoUrl }: { job: JobOut | undefined; photoUrl?: string | null }) {
  const steps = copy.photo.progressSteps;
  const idx = job?.step ? steps.findIndex((s) => s.toLowerCase() === job.step!.toLowerCase()) : 0;
  const currentIdx = idx === -1 ? 0 : idx;
  return (
    <Card aria-live="polite" className="overflow-hidden">
      <div className="grid sm:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {photoUrl && (
          <div className="relative bg-muted">
            <img src={photoUrl} alt={copy.photo.currentPhoto} className="size-full max-h-72 object-cover sm:max-h-none" />
            <div className="absolute inset-0 bg-gradient-to-t from-foreground/30 to-transparent" aria-hidden="true" />
          </div>
        )}
        <div className={cn("space-y-4 p-5 sm:p-6", !photoUrl && "sm:col-span-2")}>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">{copy.photo.analysingTitle}</h2>
            <p className="text-sm text-muted-foreground">{copy.photo.analysingIntro}</p>
          </div>
          <ol className="space-y-3">
            {steps.map((s, i) => {
              const done = i < currentIdx;
              const now = i === currentIdx;
              return (
                <li key={s} className={cn("flex items-center gap-3", !done && !now && "text-muted-foreground")}>
                  {done ? (
                    <CheckCircle2 className="size-5 shrink-0 text-success" aria-hidden="true" />
                  ) : now ? (
                    <Loader2 className="size-5 shrink-0 animate-spin text-primary" aria-hidden="true" />
                  ) : (
                    <Circle className="size-5 shrink-0" aria-hidden="true" />
                  )}
                  <span className={cn(now && "font-medium")}>{s}</span>
                </li>
              );
            })}
          </ol>
          {job?.step && idx === -1 && <p className="text-sm text-muted-foreground">{job.step}</p>}
        </div>
      </div>
    </Card>
  );
}

function Tips() {
  return (
    <div className="rounded-2xl border bg-paper p-5">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Lightbulb className="size-4 text-primary" aria-hidden="true" />
        {copy.photo.tipsTitle}
      </p>
      <ul className="space-y-2.5 text-sm leading-relaxed">
        {copy.photo.tips.map((t, i) => (
          <li key={t} className="flex gap-2.5">
            <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-card text-[11px] font-semibold text-primary shadow-xs" aria-hidden="true">
              {i + 1}
            </span>
            {t}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The rejected photo, when it can still be loaded; nothing (no broken image) otherwise. */
function RejectedThumb({ url }: { url: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) return null;
  return (
    <img
      src={url}
      alt={copy.photo.rejectedPhotoAlt}
      onError={() => setBroken(true)}
      className="max-h-56 w-full rounded-lg border bg-muted object-contain sm:w-56"
    />
  );
}

function issueMessages(p: ProjectOut, severity: "warn" | "hard"): string[] {
  return (p.verdict?.issues ?? []).filter((i) => i.severity === severity).map((i) => i.message);
}

export function PhotoStep() {
  const { project } = useWizard();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const upload = useUploadPhoto(project.id);
  const continueWarn = useContinuePhoto(project.id);
  const [problem, setProblem] = useState<UploadProblem | null>(null);
  const [showUploader, setShowUploader] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const problemId = useId();

  const analysing = project.stage === "analyzing";
  const activeJobId = analysing ? (project.active_job?.id ?? jobId) : null;
  const job = useJob(activeJobId);
  const watched = useRef(false);

  // When the analysis finishes, reload the project; a clean photo goes straight to the next step.
  useEffect(() => {
    if (!analysing || !isJobFinished(job.data)) return;
    watched.current = true;
    void qc.invalidateQueries({ queryKey: qk.project(project.id) });
    void qc.invalidateQueries({ queryKey: qk.regions(project.id) });
    void qc.invalidateQueries({ queryKey: qk.projects });
  }, [analysing, job.data, qc, project.id]);

  useEffect(() => {
    if (watched.current && project.stage === "regions_review") {
      watched.current = false;
      navigate(`/projects/${project.id}/parts`);
    }
  }, [project.stage, project.id, navigate]);

  const onFile = (file: File) => {
    setProblem(null);
    upload.mutate(file, {
      onSuccess: (res) => {
        setJobId(res.job_id);
        setShowUploader(false);
        watched.current = true;
      },
      onError: (err) => setProblem(uploadProblem(err)),
    });
  };

  // Going back from the uploader changes nothing: no request is sent until a photo is chosen.
  const canCancelUpload = showUploader && !upload.isPending;
  const cancelUpload = () => {
    setProblem(null);
    setShowUploader(false);
  };

  const uploader = (
    <div className="space-y-4">
      {problem && (
        <Alert variant="destructive" id={problemId}>
          <XCircle aria-hidden="true" />
          <div>
            <AlertTitle>{problem.title}</AlertTitle>
            <AlertDescription>{problem.message}</AlertDescription>
          </div>
        </Alert>
      )}
      {upload.isPending ? (
        <div className="grid place-items-center gap-2 rounded-2xl border-2 border-dashed border-primary/40 bg-accent/50 px-6 py-14 text-center" aria-live="polite">
          <Loader2 className="size-8 animate-spin text-primary" aria-hidden="true" />
          <p role="status" className="font-medium">
            {copy.photo.uploading}
          </p>
          <p className="text-sm text-muted-foreground">{copy.photo.uploadingHint}</p>
        </div>
      ) : (
        <PhotoDropzone
          onFile={onFile}
          onWrongType={() => setProblem({ title: copy.photo.problemTitles.type, message: copy.photo.wrongType })}
          describedBy={problem ? problemId : undefined}
        />
      )}
      {canCancelUpload && (
        <Button variant="ghost" onClick={cancelUpload} className="-ml-2">
          <RotateCcw aria-hidden="true" />
          {copy.photo.cancelReplace}
        </Button>
      )}
    </div>
  );

  let body: ReactNode;
  if (analysing && !upload.isPending) {
    body =
      job.data?.status === "failed" ? (
        <div className="space-y-4">
          <Alert variant="destructive">
            <XCircle aria-hidden="true" />
            <AlertDescription>{copy.photo.analysisFailed}</AlertDescription>
          </Alert>
          {uploader}
        </div>
      ) : (
        <AnalysisProgress job={job.data} photoUrl={project.photo?.url} />
      );
  } else if (project.stage === "photo_warning" && !showUploader) {
    body = (
      <Card className="overflow-hidden border-warning">
        <CardHeader className="bg-warning-soft/60">
          <CardTitle className="flex items-center gap-2 text-warning-foreground">
            <AlertTriangle className="size-5 shrink-0" aria-hidden="true" />
            {copy.photo.warningTitle}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 pt-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:pt-5">
          {project.photo && (
            <img src={project.photo.url} alt={copy.photo.currentPhoto} className="max-h-72 w-full rounded-lg border bg-muted object-contain" />
          )}
          <div className="space-y-2 leading-relaxed">
            {issueMessages(project, "warn").map((m) => (
              <p key={m}>{m}</p>
            ))}
          </div>
        </CardContent>
        <CardFooter>
          <Button
            onClick={() =>
              continueWarn.mutate(undefined, { onSuccess: () => navigate(`/projects/${project.id}/parts`) })
            }
            pending={continueWarn.isPending}
          >
            {copy.photo.useThisPhoto}
          </Button>
          <Button variant="outline" onClick={() => setShowUploader(true)}>
            {copy.photo.uploadBetter}
          </Button>
        </CardFooter>
      </Card>
    );
  } else if (project.stage === "photo_rejected" && !showUploader) {
    const msgs = issueMessages(project, "hard");
    body = (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <XCircle className="size-5 shrink-0 text-destructive" aria-hidden="true" />
            {copy.photo.rejectTitle}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-start">
          {project.photo && <RejectedThumb url={project.photo.url} />}
          <div className="space-y-2 leading-relaxed">
            {(msgs.length ? msgs : [copy.photo.rejectFallback]).map((m) => (
              <p key={m}>{m}</p>
            ))}
          </div>
        </CardContent>
        <CardFooter>
          <Button onClick={() => setShowUploader(true)}>{copy.photo.uploadAnother}</Button>
        </CardFooter>
      </Card>
    );
  } else if (project.photo && !showUploader && project.stage !== "upload" && project.stage !== "photo_rejected" && project.stage !== "photo_warning") {
    body = (
      <Card className="overflow-hidden">
        <div className="bg-muted">
          <img src={project.photo.url} alt={copy.photo.currentPhoto} className="mx-auto max-h-[28rem] w-full object-contain" />
        </div>
        <CardContent className="space-y-4 pt-4 sm:pt-5">
          <Alert variant="success">
            <CheckCircle2 aria-hidden="true" />
            <p className="font-medium">{copy.photo.done}</p>
          </Alert>
        </CardContent>
        <CardFooter>
          <Button asChild>
            <Link to={`/projects/${project.id}/parts`}>
              {copy.photo.toParts}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <Button variant="outline" onClick={() => setShowUploader(true)}>
            {copy.photo.replace}
          </Button>
        </CardFooter>
      </Card>
    );
  } else {
    body = (
      <div className="space-y-4">
        {project.photo && project.regions_approved && (
          <Alert variant="warning">
            <AlertTriangle aria-hidden="true" />
            <p>{copy.photo.replaceWarning}</p>
          </Alert>
        )}
        {uploader}
      </div>
    );
  }

  return (
    <section className="space-y-6" aria-labelledby="photo-title">
      <PageHeader id="photo-title" eyebrow={copy.stepper.stepOf(1, 6)} title={copy.photo.title} description={copy.photo.intro} />
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">{body}</div>
        <aside className="lg:sticky lg:top-24">
          <Tips />
        </aside>
      </div>
    </section>
  );
}
