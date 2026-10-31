import { cn } from "@/lib/utils";

/** Decorative line drawing of a house front, in the app's teal and paper tones. */
export function FacadeArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 320 220" className={cn("h-auto w-full", className)} aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 206h292" strokeWidth="2" opacity="0.5" />
        {/* main block */}
        <rect x="52" y="58" width="168" height="148" rx="2" strokeWidth="2.2" />
        <path d="M44 58h184" strokeWidth="2.2" />
        <path d="M52 50h168v8H52z" strokeWidth="1.6" opacity="0.7" />
        {/* side block */}
        <rect x="220" y="104" width="64" height="102" rx="2" strokeWidth="2.2" />
        <path d="M214 104h76" strokeWidth="2.2" />
        {/* windows, upper floor */}
        <rect x="72" y="76" width="34" height="38" rx="1.5" strokeWidth="1.6" />
        <path d="M89 76v38M72 95h34" strokeWidth="1" opacity="0.6" />
        <rect x="166" y="76" width="34" height="38" rx="1.5" strokeWidth="1.6" />
        <path d="M183 76v38M166 95h34" strokeWidth="1" opacity="0.6" />
        {/* balcony */}
        <rect x="118" y="80" width="36" height="34" rx="1.5" strokeWidth="1.6" />
        <path d="M110 114h52M110 114v14h52v-14M118 114v14M126 114v14M134 114v14M142 114v14M150 114v14" strokeWidth="1.2" opacity="0.75" />
        {/* floor line */}
        <path d="M52 136h168" strokeWidth="1.2" opacity="0.45" />
        {/* door and ground-floor windows */}
        <rect x="120" y="150" width="32" height="56" rx="1.5" strokeWidth="1.8" />
        <circle cx="146" cy="180" r="1.6" fill="currentColor" stroke="none" />
        <rect x="72" y="152" width="34" height="32" rx="1.5" strokeWidth="1.6" />
        <rect x="166" y="152" width="34" height="32" rx="1.5" strokeWidth="1.6" />
        <rect x="236" y="124" width="32" height="30" rx="1.5" strokeWidth="1.6" />
        {/* pillars */}
        <path d="M60 136v70M212 136v70" strokeWidth="1.4" opacity="0.55" />
        {/* gate */}
        <path d="M236 206v-30h32v30M244 176v30M252 176v30M260 176v30" strokeWidth="1.2" opacity="0.7" />
      </g>
      {/* material swatches, like samples pinned to a board */}
      <g>
        <rect x="18" y="20" width="22" height="22" rx="4" fill="#cdb79e" />
        <rect x="18" y="46" width="22" height="22" rx="4" fill="#c97b5a" />
        <rect x="18" y="72" width="22" height="22" rx="4" fill="#d6e0d8" />
      </g>
    </svg>
  );
}
