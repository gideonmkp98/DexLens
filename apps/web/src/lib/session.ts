export interface SessionUser {
  id: string;
  email: string;
  role: string;
  username?: string | null;
  email_verified?: boolean;
  has_beta_access?: boolean;
  beta_entitlement?: string | null;
  scan_quota?: number | null;
}

export interface BrowserSessionState {
  is_authenticated: boolean;
  user: SessionUser | null;
  session_id: string;
  session_type: string;
}

let bootstrapPromise: Promise<BrowserSessionState> | null = null;
let refreshPromise: Promise<BrowserSessionState> | null = null;
let requestGeneration = 0;

export class SessionRequestSupersededError extends Error {
  constructor() {
    super("Browser session request was superseded");
    this.name = "SessionRequestSupersededError";
  }
}

export function isSessionRequestSupersededError(
  error: unknown
): error is SessionRequestSupersededError {
  return error instanceof SessionRequestSupersededError;
}

type UnauthorizedHandler = () => void;
const unauthorizedHandlers = new Set<UnauthorizedHandler>();

export function onUnauthorized(handler: UnauthorizedHandler): () => void {
  unauthorizedHandlers.add(handler);
  return () => {
    unauthorizedHandlers.delete(handler);
  };
}

export function notifyUnauthorized(): void {
  for (const handler of Array.from(unauthorizedHandlers)) {
    try {
      handler();
    } catch {
      // Ignore subscriber errors to guarantee delivery to remaining listeners.
    }
  }
}

/**
 * Return the cached initial browser session or initiate a single flight
 * bootstrap fetch to /api/v1/auth/me. Safe to call from multiple components
 * concurrently.
 */
export function ensureBrowserSession(): Promise<BrowserSessionState> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Browser session is client-only"));
  }

  if (!bootstrapPromise) {
    const generation = requestGeneration;
    const request = fetch("/api/v1/auth/me", {
      credentials: "include",
      cache: "no-store",
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error("Browser session bootstrap failed");
      }
      const state = (await response.json()) as BrowserSessionState;
      if (generation !== requestGeneration) {
        throw new SessionRequestSupersededError();
      }
      return state;
    });

    const trackedRequest = request.catch((error) => {
      if (bootstrapPromise === trackedRequest) {
        bootstrapPromise = null;
      }
      throw error;
    });
    bootstrapPromise = trackedRequest;
  }

  return bootstrapPromise;
}

/**
 * Invalidate any stale cached browser-session promise and perform a fresh
 * fetch to /api/v1/auth/me. Ensures single-flight execution if multiple
 * callers trigger a refresh concurrently.
 */
export function refreshBrowserSession(options?: {
  force?: boolean;
}): Promise<BrowserSessionState> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Browser session is client-only"));
  }

  if (refreshPromise && !options?.force) {
    return refreshPromise;
  }

  const generation = ++requestGeneration;
  const request = fetch("/api/v1/auth/me", {
    credentials: "include",
    cache: "no-store",
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error("Browser session refresh failed");
      }
      const state = (await response.json()) as BrowserSessionState;
      if (generation !== requestGeneration) {
        throw new SessionRequestSupersededError();
      }
      // Re-seed bootstrap cache with fresh state so subsequent ensure calls
      // don't repeat the fetch.
      bootstrapPromise = Promise.resolve(state);
      return state;
    })
    .finally(() => {
      refreshPromise = null;
    });

  refreshPromise = request;
  return request;
}

/**
 * Reset all cached bootstrap state. Intended strictly for test teardowns.
 */
export function resetBrowserSessionBootstrap(): void {
  bootstrapPromise = null;
  refreshPromise = null;
  requestGeneration = 0;
  unauthorizedHandlers.clear();
}
