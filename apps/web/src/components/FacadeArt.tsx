import { cn } from "@/lib/utils";

/**
 * Modern architectural facade elevation showcase with realistic materials,
 * textures, lighting accents, and AI structure detection badges.
 */
export function FacadeArt({ className }: { className?: string }) {
  return (
    <div className={cn("relative mx-auto w-full max-w-md select-none", className)}>
      {/* Container Card with subtle shadow and border */}
      <div className="overflow-hidden rounded-xl border border-blue-100/90 bg-white/95 p-2.5 shadow-lg shadow-blue-950/5 backdrop-blur-sm sm:p-3">
        {/* Mockup Header Toolbar */}
        <div className="mb-1.5 flex items-center justify-between border-b border-slate-100 pb-1.5 px-0.5 text-[11px]">
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-blue-500 animate-pulse" />
            <span className="font-semibold text-slate-700">AI Facade Scan & Elevation</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 border border-blue-200/60">
              Grade A (84/100)
            </span>
            <span className="text-[10px] font-medium text-slate-400">1:50</span>
          </div>
        </div>

        {/* Architectural Elevation SVG */}
        <svg
          viewBox="0 0 420 270"
          className="h-auto max-h-[190px] xl:max-h-[220px] w-full rounded-lg bg-gradient-to-b from-sky-50/60 via-slate-50/40 to-blue-50/30 object-contain"
          aria-hidden="true"
          focusable="false"
        >
          <defs>
            {/* Architectural Sky Gradient */}
            <linearGradient id="skyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#f0f9ff" />
              <stop offset="100%" stopColor="#f8fafc" />
            </linearGradient>

            {/* Glass window reflection gradient */}
            <linearGradient id="glassReflect" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#bae6fd" stopOpacity="0.55" />
              <stop offset="50%" stopColor="#e0f2fe" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#7dd3fc" stopOpacity="0.45" />
            </linearGradient>

            {/* Teak Wood Slats Pattern */}
            <pattern id="teakLouvers" width="8" height="8" patternUnits="userSpaceOnUse">
              <rect width="8" height="8" fill="#c68a4c" />
              <rect width="4" height="8" fill="#b07236" />
              <line x1="0" y1="0" x2="0" y2="8" stroke="#8c5321" strokeWidth="0.75" />
            </pattern>

            {/* Limestone / Stone Block Pattern */}
            <pattern id="limestoneBlocks" width="28" height="14" patternUnits="userSpaceOnUse">
              <rect width="28" height="14" fill="#ede5d8" />
              <line x1="0" y1="14" x2="28" y2="14" stroke="#d6c8b4" strokeWidth="0.8" />
              <line x1="14" y1="0" x2="14" y2="7" stroke="#d6c8b4" strokeWidth="0.8" />
              <line x1="28" y1="7" x2="28" y2="14" stroke="#d6c8b4" strokeWidth="0.8" />
              <line x1="0" y1="7" x2="28" y2="7" stroke="#d6c8b4" strokeWidth="0.8" />
            </pattern>

            {/* Charcoal Metal Siding Pattern */}
            <pattern id="metalSiding" width="12" height="12" patternUnits="userSpaceOnUse">
              <rect width="12" height="12" fill="#334155" />
              <line x1="12" y1="0" x2="12" y2="12" stroke="#1e293b" strokeWidth="1" />
            </pattern>

            {/* Warm Sconce Glow */}
            <radialGradient id="sconceGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fef08a" stopOpacity="0.8" />
              <stop offset="40%" stopColor="#fde047" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#fde047" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Background ground & sky */}
          <rect x="0" y="0" width="420" height="235" fill="url(#skyGrad)" />
          <line x1="10" y1="235" x2="410" y2="235" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4 2" />
          <rect x="0" y="235" width="420" height="35" fill="#f1f5f9" />

          {/* Ground pavers */}
          <g stroke="#cbd5e1" strokeWidth="1" opacity="0.7">
            <line x1="30" y1="235" x2="20" y2="270" />
            <line x1="80" y1="235" x2="70" y2="270" />
            <line x1="130" y1="235" x2="120" y2="270" />
            <line x1="180" y1="235" x2="170" y2="270" />
            <line x1="230" y1="235" x2="220" y2="270" />
            <line x1="280" y1="235" x2="270" y2="270" />
            <line x1="330" y1="235" x2="320" y2="270" />
            <line x1="380" y1="235" x2="370" y2="270" />
          </g>

          {/* MAIN RESIDENCE STRUCTURE */}
          {/* Main House Drop Shadow */}
          <rect x="42" y="44" width="336" height="191" rx="4" fill="#0f172a" opacity="0.06" />

          {/* GROUND FLOOR (STONE & PLASTER) */}
          <rect x="40" y="132" width="220" height="103" rx="2" fill="url(#limestoneBlocks)" stroke="#475569" strokeWidth="1.2" />

          {/* SIDE EXTENSION (GARAGE / PORCH) */}
          <rect x="260" y="145" width="115" height="90" rx="2" fill="url(#metalSiding)" stroke="#1e293b" strokeWidth="1.2" />
          {/* Garage Door Section Lines */}
          <g stroke="#475569" strokeWidth="0.8">
            <line x1="268" y1="168" x2="367" y2="168" />
            <line x1="268" y1="190" x2="367" y2="190" />
            <line x1="268" y1="212" x2="367" y2="212" />
          </g>

          {/* UPPER FLOOR (CANTILEVER WITH WOOD & GLASS) */}
          {/* Cantilever Box */}
          <rect x="52" y="42" width="240" height="90" rx="2" fill="#ffffff" stroke="#334155" strokeWidth="1.4" />

          {/* Fluted Teak Feature Wall on Left Upper */}
          <rect x="53" y="43" width="95" height="88" fill="url(#teakLouvers)" />
          <rect x="52" y="42" width="97" height="90" fill="none" stroke="#64748b" strokeWidth="1" />

          {/* Upper Floor Large Window Panel */}
          <rect x="156" y="52" width="124" height="68" rx="2" fill="url(#glassReflect)" stroke="#0f172a" strokeWidth="1.5" />
          {/* Window Mullions */}
          <line x1="218" y1="52" x2="218" y2="120" stroke="#0f172a" strokeWidth="1.2" />
          <line x1="156" y1="92" x2="280" y2="92" stroke="#0f172a" strokeWidth="1" />
          {/* Window Glass Glare Accents */}
          <path d="M162 114 L178 58 L188 58 L172 114 Z" fill="#ffffff" opacity="0.4" />
          <path d="M194 114 L204 78 L210 78 L200 114 Z" fill="#ffffff" opacity="0.3" />

          {/* Cantilever Roof Coping (Charcoal Aluminum) */}
          <rect x="48" y="38" width="248" height="6" rx="1" fill="#1e293b" />
          <rect x="256" y="141" width="122" height="5" rx="1" fill="#1e293b" />

          {/* GROUND FLOOR DETAILS */}
          {/* Main Entrance Door (Modern Pivot Door in Dark Oak) */}
          <rect x="178" y="152" width="42" height="83" rx="1" fill="#451a03" stroke="#1c1917" strokeWidth="1.2" />
          {/* Long Vertical Architectural Handle */}
          <line x1="184" y1="180" x2="184" y2="215" stroke="#f8fafc" strokeWidth="2" strokeLinecap="round" />
          <line x1="184" y1="180" x2="184" y2="215" stroke="#fbbf24" strokeWidth="1.2" strokeLinecap="round" />

          {/* Entrance Canopy */}
          <rect x="170" y="148" width="58" height="4" rx="1" fill="#0f172a" />

          {/* Ground Floor Picture Windows */}
          <rect x="62" y="155" width="98" height="65" rx="1.5" fill="url(#glassReflect)" stroke="#0f172a" strokeWidth="1.4" />
          <line x1="111" y1="155" x2="111" y2="220" stroke="#0f172a" strokeWidth="1.2" />
          <path d="M68 214 L80 162 L88 162 L76 214 Z" fill="#ffffff" opacity="0.35" />

          {/* Architectural Wall Sconces with Glow */}
          {/* Sconce 1 (Front Door) */}
          <circle cx="228" cy="172" r="14" fill="url(#sconceGlow)" />
          <rect x="226" y="169" width="4" height="7" rx="1" fill="#1e293b" />
          <circle cx="228" cy="172" r="1.5" fill="#fef08a" />

          {/* Sconce 2 (Garage) */}
          <circle cx="274" cy="160" r="12" fill="url(#sconceGlow)" />
          <rect x="272" y="157" width="4" height="6" rx="1" fill="#1e293b" />
          <circle cx="274" cy="160" r="1.2" fill="#fef08a" />

          {/* Modern Minimalist Planters & Greenery */}
          {/* Planter 1 (Beside door) */}
          <rect x="226" y="218" width="16" height="17" rx="1" fill="#64748b" stroke="#334155" strokeWidth="0.8" />
          <ellipse cx="234" cy="214" rx="9" ry="8" fill="#15803d" />
          <ellipse cx="234" cy="211" rx="6" ry="6" fill="#22c55e" />

          {/* Planter 2 (Near Corner) */}
          <rect x="46" y="218" width="14" height="17" rx="1" fill="#64748b" stroke="#334155" strokeWidth="0.8" />
          <ellipse cx="53" cy="214" rx="8" ry="7" fill="#166534" />
          <ellipse cx="53" cy="211" rx="5" ry="5" fill="#15803d" />

          {/* Balcony Glass Railing on Upper Level */}
          <rect x="150" y="104" width="138" height="28" fill="#bae6fd" fillOpacity="0.25" stroke="#38bdf8" strokeWidth="0.8" strokeDasharray="3 1" />
          <line x1="148" y1="104" x2="290" y2="104" stroke="#475569" strokeWidth="1.5" />
          <line x1="196" y1="104" x2="196" y2="132" stroke="#64748b" strokeWidth="1" />
          <line x1="244" y1="104" x2="244" y2="132" stroke="#64748b" strokeWidth="1" />

          {/* OVERLAY AI DETECTION PINS & CALLOUTS */}
          {/* Pin 1: Teak Battens */}
          <g>
            <circle cx="95" cy="78" r="4" fill="#10b981" />
            <circle cx="95" cy="78" r="1.8" fill="#ffffff" />
            <line x1="95" y1="73" x2="95" y2="24" stroke="#10b981" strokeWidth="1" strokeDasharray="2 2" />
            <rect x="52" y="10" width="86" height="17" rx="3.5" fill="#0f172a" fillOpacity="0.85" />
            <text x="58" y="21.5" fill="#ffffff" fontSize="8.5" fontWeight="600" fontFamily="sans-serif">
              Teak Battens • 340 sq.ft
            </text>
          </g>

          {/* Pin 2: Double Glazing */}
          <g>
            <circle cx="240" cy="80" r="4" fill="#10b981" />
            <circle cx="240" cy="80" r="1.8" fill="#ffffff" />
            <line x1="240" y1="75" x2="258" y2="24" stroke="#10b981" strokeWidth="1" strokeDasharray="2 2" />
            <rect x="252" y="10" width="94" height="17" rx="3.5" fill="#0f172a" fillOpacity="0.85" />
            <text x="258" y="21.5" fill="#ffffff" fontSize="8.5" fontWeight="600" fontFamily="sans-serif">
              Low-E Glass • 120 sq.ft
            </text>
          </g>

          {/* Pin 3: Travertine Stone */}
          <g>
            <circle cx="110" cy="188" r="4" fill="#10b981" />
            <circle cx="110" cy="188" r="1.8" fill="#ffffff" />
            <line x1="110" y1="193" x2="70" y2="246" stroke="#10b981" strokeWidth="1" strokeDasharray="2 2" />
            <rect x="20" y="244" width="105" height="17" rx="3.5" fill="#0f172a" fillOpacity="0.85" />
            <text x="26" y="255.5" fill="#ffffff" fontSize="8.5" fontWeight="600" fontFamily="sans-serif">
              Travertine Stone • 480 sq.ft
            </text>
          </g>
        </svg>

        {/* Mockup Footer Card with BOQ Metrics */}
        <div className="mt-1.5 flex items-center justify-between rounded-lg bg-slate-50 border border-slate-200/60 px-2.5 py-1 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="flex size-4 items-center justify-center rounded bg-blue-600 text-[9px] font-bold text-white">
              ₹
            </span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[10px] uppercase font-semibold text-slate-400">Makeover Est:</span>
              <span className="text-xs font-bold text-slate-800">₹4,85,000</span>
            </div>
          </div>
          <div className="text-right">
            <span className="text-[11px] font-semibold text-blue-700">940 sq.ft • 3 Finishes</span>
          </div>
        </div>
      </div>
    </div>
  );
}
