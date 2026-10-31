import { Check, CircleAlert, CircleDashed, Clock, Loader2, Lock, RefreshCw } from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** The states a step, a look or an estimate can be in. Always shown as icon + words, never colour alone. */
export type StatusTone = "done" | "progress" | "attention" | "stale" | "locked" | "neutral";

const TONE: Record<StatusTone, { variant: BadgeVariant; icon: typeof Check }> = {
  done: { variant: "success", icon: Check },
  progress: { variant: "info", icon: Clock },
  attention: { variant: "warning", icon: CircleAlert },
  stale: { variant: "warning", icon: RefreshCw },
  locked: { variant: "neutral", icon: Lock },
  neutral: { variant: "neutral", icon: CircleDashed },
};

export function StatusBadge({ tone, label, className }: { tone: StatusTone; label: string; className?: string }) {
  const { variant, icon: Icon } = TONE[tone];
  return (
    <Badge variant={variant} className={className}>
      <Icon aria-hidden="true" />
      {label}
    </Badge>
  );
}

/** Small "Saving… / Saved" line for autosaving editors. Announced politely, never steals focus. */
export function SaveStatus({
  state,
  savingLabel,
  savedLabel,
  className,
  testId,
}: {
  state: "idle" | "saving" | "saved";
  savingLabel: string;
  savedLabel: string;
  className?: string;
  testId?: string;
}) {
  return (
    <span
      aria-live="polite"
      data-testid={testId}
      className={cn("inline-flex min-h-5 items-center gap-1.5 text-xs text-muted-foreground", className)}
    >
      {state === "saving" && (
        <>
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          {savingLabel}
        </>
      )}
      {state === "saved" && (
        <>
          <Check className="size-3.5 text-success" aria-hidden="true" />
          {savedLabel}
        </>
      )}
    </span>
  );
}
