import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Title block shared by every screen: optional small "eyebrow" (e.g. "Step 2 of 6"), one `h1`,
 * an intro line and an optional slot on the right for status or actions.
 */
export function PageHeader({
  id,
  eyebrow,
  title,
  description,
  aside,
  className,
}: {
  id?: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0 max-w-2xl space-y-1.5">
        {eyebrow && <p className="text-xs font-semibold tracking-wide text-primary uppercase">{eyebrow}</p>}
        <h1 id={id} className="text-2xl font-semibold tracking-tight sm:text-[1.75rem] sm:leading-tight">
          {title}
        </h1>
        {description && <p className="text-[0.95rem] leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {aside && <div className="flex flex-wrap items-center gap-2">{aside}</div>}
    </div>
  );
}

/**
 * Action bar that sticks to the bottom of the screen while its section is on screen. It sits in
 * the normal flow at the end of the section, so it never covers the last row of content, and it
 * clears the phone's home indicator.
 */
export function StickyActionBar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "sticky bottom-0 z-20 -mx-4 border-t bg-background/95 px-4 pt-3 pb-safe shadow-[0_-4px_16px_-8px_oklch(0.22_0.02_255/0.12)] backdrop-blur supports-[backdrop-filter]:bg-background/85 sm:-mx-6 sm:px-6",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">{children}</div>
    </div>
  );
}
