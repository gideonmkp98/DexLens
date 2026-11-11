export interface BrowserSessionState {
  is_authenticated: boolean;
  user: {
    id: string;
    email: string;
    role: string;
    has_beta_access?: boolean;
    beta_entitlement?: string | null;
    scan_quota?: number | null;
  } | null;
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
  for (const handler of unauthorizedHandlers) {
    try {
      handler();
    } catch {
      // Non-fatal
    }
  }
}

/**
 * Establish exactly one browser identity before parallel API calls start.
 * Without this gate, first-load analytics and scanner requests can each receive
 * a different anonymous cookie and leave a newly-created scan session orphaned.
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
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error("Browser session refresh failed");
    }
    const state = (await response.json()) as BrowserSessionState;
    if (generation !== requestGeneration) {
      throw new SessionRequestSupersededError();
    }
    return state;
  });

  const trackedRequest = request.then(
    (state) => {
      if (refreshPromise === trackedRequest) {
        refreshPromise = null;
      }
      if (generation === requestGeneration) {
        bootstrapPromise = Promise.resolve(state);
      }
      return state;
    },
    (error) => {
      if (refreshPromise === trackedRequest) {
        refreshPromise = null;
      }
      if (bootstrapPromise === trackedRequest) {
        bootstrapPromise = null;
      }
      throw error;
    }
  );

  refreshPromise = trackedRequest;
  bootstrapPromise = trackedRequest;
  return trackedRequest;
}

/**
 * Reset the cached bootstrap promise so subsequent reads fetch fresh state.
 */
export function resetBrowserSessionBootstrap(): void {
  requestGeneration++;
  bootstrapPromise = null;
  refreshPromise = null;
}

/**
 * Update the in-memory cache directly with known fresh state.
 */
export function setBrowserSessionState(state: BrowserSessionState): void {
  requestGeneration++;
  refreshPromise = null;
  bootstrapPromise = Promise.resolve(state);
}
