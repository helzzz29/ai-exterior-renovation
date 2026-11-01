import { Moon, Sun, Sunset } from "lucide-react";
import { cn } from "@/lib/utils";

export type LightingMode = "day" | "sunset" | "night";

export interface LightingStyle {
  filter: string;
  overlayClass?: string;
  overlayStyle?: React.CSSProperties;
}

export const LIGHTING_STYLES: Record<LightingMode, LightingStyle> = {
  day: {
    filter: "brightness(1) contrast(1)",
  },
  sunset: {
    filter: "sepia(0.28) saturate(1.45) brightness(0.96) contrast(1.06)",
    overlayStyle: {
      background: "linear-gradient(180deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.08) 50%, rgba(0, 0, 0, 0.15) 100%)",
      mixBlendMode: "overlay",
    },
  },
  night: {
    filter: "brightness(0.7) contrast(1.22) saturate(1.1) hue-rotate(192deg)",
    overlayStyle: {
      background: "radial-gradient(circle at 50% 95%, rgba(251, 191, 36, 0.32) 0%, rgba(30, 41, 59, 0.35) 60%, rgba(2, 6, 23, 0.65) 100%)",
      mixBlendMode: "hard-light",
    },
  },
};

export function PhotoLightingControl({
  mode,
  onChange,
  className,
}: {
  mode: LightingMode;
  onChange: (m: LightingMode) => void;
  className?: string;
}) {
  const options = [
    { id: "day", label: "Daylight", icon: Sun, color: "text-amber-400" },
    { id: "sunset", label: "Golden Dusk", icon: Sunset, color: "text-orange-400" },
    { id: "night", label: "Night Illum.", icon: Moon, color: "text-cyan-400" },
  ] as const;

  return (
    <div
      role="radiogroup"
      aria-label="Facade lighting simulation"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-border/80 bg-card/90 p-1 shadow-md backdrop-blur-md",
        className,
      )}
    >
      <span className="pl-2 pr-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
        Lighting:
      </span>
      {options.map(({ id, label, icon: Icon, color }) => {
        const active = mode === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-all outline-none",
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted/80 hover:text-foreground",
            )}
          >
            <Icon className={cn("size-3.5", !active && color)} aria-hidden="true" />
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}
