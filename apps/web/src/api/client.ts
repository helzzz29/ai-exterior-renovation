import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { copy } from "@/copy";

/**
 * Typed API client. All paths in the contract already start with `/api`.
 * The base URL is the page origin, so the dev proxy (or the same host in production) serves the
 * API and the session cookie stays same-origin. `fetch` is resolved lazily so test tooling that
 * patches `globalThis.fetch` (MSW) is always picked up.
 */
export const api = createClient<paths>({
  baseUrl: typeof window !== "undefined" ? window.location.origin : "",
  credentials: "include",
  fetch: (request: Request) => globalThis.fetch(request),
});

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface MaybeErrorBody {
  code?: unknown;
  message?: unknown;
  detail?: unknown;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/**
 * Turn any error body into a plain-language ApiError.
 * Accepts the contract's `ApiError` body (`{code, message}`), the same wrapped in FastAPI's
 * `{detail: {...}}`, a plain `{detail: "..."}` string, or FastAPI validation errors.
 */
export function toApiError(status: number, body: unknown): ApiError {
  const b: MaybeErrorBody = isObject(body) ? body : {};
  const inner: MaybeErrorBody = isObject(b.detail) && !Array.isArray(b.detail) ? b.detail : b;
  if (typeof inner.message === "string" && inner.message.trim()) {
    return new ApiError(status, typeof inner.code === "string" ? inner.code : "error", inner.message);
  }
  if (status === 401) return new ApiError(status, "unauthorised", copy.errors.signedOut);
  if (status === 404) return new ApiError(status, "not_found", copy.errors.notFound);
  if (Array.isArray(b.detail)) return new ApiError(status, "invalid", copy.errors.invalidInput);
  if (typeof b.detail === "string" && [400, 403, 409, 422].includes(status)) {
    return new ApiError(status, "error", b.detail);
  }
  if (status === 0) return new ApiError(0, "network", copy.errors.network);
  return new ApiError(status, "server", copy.errors.generic);
}

interface FetchResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Await an openapi-fetch call and return its data, or throw a friendly ApiError. */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch {
    throw toApiError(0, null);
  }
  if (!result.response.ok) {
    throw toApiError(result.response.status, result.error);
  }
  return result.data as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return copy.errors.generic;
}
