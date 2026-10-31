import type { ReactNode } from "react";
import { AlertTriangle, ArrowLeft, Loader2, MapPinOff, RotateCcw } from "lucide-react";
import { Link } from "react-router";
import { ApiError, errorMessage } from "@/api/client";
import { copy } from "@/copy";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      <span className={label ? "text-sm" : "sr-only"}>{label ?? copy.common.loading}</span>
    </span>
  );
}

/** Page-level loading placeholder, shaped like a title, an intro and a large panel. */
export function PageSkeleton({ label = copy.common.loading }: { label?: string }) {
  return (
    <div className="space-y-4" aria-busy="true">
      <span className="sr-only" role="status">
        {label}
      </span>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-1/2 max-w-sm" />
      <Skeleton className="h-4 w-3/4 max-w-xl" />
      <Skeleton className="h-72 w-full rounded-xl" />
    </div>
  );
}

/** True for errors that trying again can't fix: the thing is gone or belongs to someone else. */
export function isMissing(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/**
 * A request failed. Retryable errors offer "Try again"; a missing item (404) offers the way back
 * to My projects instead, because retrying can never succeed.
 */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const missing = isMissing(error);
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-4 rounded-xl border border-destructive/30 bg-destructive-soft p-5 sm:p-6"
    >
      <div className="flex items-start gap-3 font-medium text-destructive">
        <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <p>{errorMessage(error)}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {onRetry && !missing && (
          <Button variant="outline" onClick={onRetry}>
            <RotateCcw aria-hidden="true" />
            {copy.common.tryAgain}
          </Button>
        )}
        {missing && (
          <Button asChild variant="outline">
            <Link to="/">
              <ArrowLeft aria-hidden="true" />
              {copy.errors.backHome}
            </Link>
          </Button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  action,
  headingLevel = 2,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
  headingLevel?: 1 | 2;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border-strong bg-card px-6 py-12 text-center sm:py-16">
      {icon && (
        <div className="mb-1 grid size-14 place-items-center rounded-2xl bg-accent text-primary [&_svg]:size-7" aria-hidden="true">
          {icon}
        </div>
      )}
      <Heading className="text-lg font-semibold tracking-tight">{title}</Heading>
      {body && <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{body}</p>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function NotFound() {
  return (
    <EmptyState
      icon={<MapPinOff />}
      title={copy.errors.pageMissing}
      body={copy.errors.pageMissingBody}
      headingLevel={1}
      action={
        <Button asChild>
          <Link to="/">{copy.errors.backHome}</Link>
        </Button>
      }
    />
  );
}
