import { useSyncExternalStore } from "react";

/** True while the CSS media query matches (e.g. "(min-width: 1024px)"); false where matchMedia is missing. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener?.("change", onChange);
      return () => mql.removeEventListener?.("change", onChange);
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  );
}

/** Desktop layout breakpoint used by the working screens (Tailwind `lg`). */
export const DESKTOP = "(min-width: 1024px)";
