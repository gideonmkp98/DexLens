export interface BrowserSessionState {
  is_authenticated: boolean;
  user: { id: string; email: string; role: string } | null;
  session_id: string;
  session_type: string;
}

let bootstrapPromise: Promise<BrowserSessionState> | null = null;

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
    bootstrapPromise = fetch("/api/v1/auth/me", {
      credentials: "include",
      cache: "no-store",
    }).then(async (response) => {
      if (!response.ok) {
        bootstrapPromise = null;
        throw new Error("Browser session bootstrap failed");
      }
      return (await response.json()) as BrowserSessionState;
    });
  }

  return bootstrapPromise;
}

export function resetBrowserSessionBootstrap(): void {
  bootstrapPromise = null;
}
