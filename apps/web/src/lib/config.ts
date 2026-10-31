const mode = import.meta.env.MODE;

/** How often we check on background work (photo analysis, new look, report). */
export const POLL_MS = mode === "test" ? 25 : 1000;

/** Delay before saving edits automatically. */
export const AUTOSAVE_MS = mode === "test" ? 30 : 800;

/** `pnpm dev:mock` (Vite mode "mock") runs the whole app against the in-browser mock API. */
export const IS_MOCK = mode === "mock" || import.meta.env.VITE_MOCK === "true";

/** Production is invite-only (built with VITE_SIGNUP_OPEN=false): no "Create account" page. */
export const SIGNUP_OPEN = import.meta.env.VITE_SIGNUP_OPEN !== "false";
