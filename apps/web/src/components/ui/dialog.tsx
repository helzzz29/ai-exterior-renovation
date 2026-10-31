import { type ReactNode, useEffect, useId, useRef } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

/**
 * A confirmation for actions that can't be undone, built on the native modal `<dialog>`: the page
 * behind it is inert, Escape cancels, focus starts on the safe choice and goes back to the button
 * that opened it.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel,
  pending = false,
  destructive = true,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body?: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  pending?: boolean;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const bodyId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      returnTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      cancelRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
      returnTo.current?.focus();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={body ? bodyId : undefined}
      onCancel={(e) => {
        e.preventDefault();
        if (!pending) onCancel();
      }}
      onClick={(e) => {
        // A click on the dimmed backdrop (the dialog element itself) counts as Cancel.
        if (e.target === ref.current && !pending) onCancel();
      }}
      className={cn(
        "m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border bg-card p-0 text-card-foreground shadow-overlay",
      )}
    >
      {open && (
        <div className="space-y-3 p-6">
          <h2 id={titleId} className="text-lg font-semibold leading-snug tracking-tight">
            {title}
          </h2>
          {body && (
            <div id={bodyId} className="text-sm text-muted-foreground">
              {body}
            </div>
          )}
          <div className="flex flex-col-reverse gap-2 pt-3 sm:flex-row sm:justify-end">
            <Button ref={cancelRef} variant="outline" onClick={onCancel} disabled={pending}>
              {cancelLabel}
            </Button>
            <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm} pending={pending}>
              {confirmLabel}
            </Button>
          </div>
        </div>
      )}
    </dialog>
  );
}
