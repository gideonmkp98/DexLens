"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ensureBrowserSession,
  isSessionRequestSupersededError,
  refreshBrowserSession,
  onUnauthorized,
  type BrowserSessionState,
} from "@/lib/session";

export type AuthStatus = "loading" | "anonymous" | "authenticated" | "error";

export interface AuthUser {
  id: string;
  email: string;
  role: string;
  username?: string | null;
  email_verified?: boolean;
  has_beta_access?: boolean;
  beta_entitlement?: string | null;
  scan_quota?: number | null;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  username?: string | null;
  password_confirmation?: string | null;
  accepted_policies?: boolean;
  beta_code?: string;
  invite_token?: string;
}

export interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  sessionId: string | null;
  sessionType: string | null;
  refreshAuth: () => Promise<BrowserSessionState>;
  login: (credentials: { email: string; password: string }) => Promise<void>;
  register: (credentials: RegisterCredentials) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const BROADCAST_CHANNEL_NAME = "dexlens_auth";
const STORAGE_SYNC_KEY = "dexlens_auth_sync";
const FOCUS_REFRESH_THROTTLE_MS = 15000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionType, setSessionType] = useState<string | null>(null);

  const lastFocusRefreshRef = useRef<number>(0);
  const broadcastChannelRef = useRef<BroadcastChannel | null>(null);

  const applySessionState = useCallback((state: BrowserSessionState) => {
    if (state.is_authenticated && state.user) {
      setUser(state.user);
      setStatus("authenticated");
    } else {
      setUser(null);
      setStatus("anonymous");
    }
    setSessionId(state.session_id);
    setSessionType(state.session_type);
  }, []);

  const broadcastAuthChange = useCallback(() => {
    let broadcastSent = false;
    try {
      if (broadcastChannelRef.current) {
        broadcastChannelRef.current.postMessage({
          type: "AUTH_STATE_CHANGED",
          timestamp: Date.now(),
        });
        broadcastSent = true;
      }
    } catch {
      // BroadcastChannel unavailable
    }
    try {
      if (
        !broadcastSent &&
        typeof window !== "undefined" &&
        window.localStorage
      ) {
        localStorage.setItem(STORAGE_SYNC_KEY, Date.now().toString());
      }
    } catch {
      // LocalStorage unavailable
    }
  }, []);

  const refreshAuth = useCallback(async (): Promise<BrowserSessionState> => {
    const state = await refreshBrowserSession();
    applySessionState(state);
    return state;
  }, [applySessionState]);

  const login = useCallback(
    async (credentials: { email: string; password: string }): Promise<void> => {
      const endpoint = "/api/v1/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(credentials),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        const detailMsg =
          errJson.detail?.message ||
          errJson.detail ||
          "Inloggen mislukt. Controleer je gegevens.";
        throw new Error(
          typeof detailMsg === "string" ? detailMsg : "Ongeldige inloggegevens."
        );
      }

      // Invalidate the cached anonymous bootstrap promise and fetch fresh /auth/me
      const freshState = await refreshBrowserSession({ force: true });
      if (!freshState.is_authenticated || !freshState.user) {
        throw new Error(
          "Inloggen geslaagd, maar verificatie van de sessie is mislukt. Probeer het opnieuw."
        );
      }

      applySessionState(freshState);
      broadcastAuthChange();
    },
    [applySessionState, broadcastAuthChange]
  );

  const register = useCallback(
    async (credentials: RegisterCredentials): Promise<void> => {
      const endpoint = "/api/v1/auth/register";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: credentials.email,
          password: credentials.password,
          ...(credentials.beta_code ? { beta_code: credentials.beta_code } : {}),
          ...(credentials.invite_token ? { invite_token: credentials.invite_token } : {}),
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        const detailMsg =
          errJson.detail?.message ||
          errJson.detail ||
          "Registreren mislukt. Controleer je gegevens.";
        throw new Error(
          typeof detailMsg === "string" ? detailMsg : "Registreren mislukt."
        );
      }

      // Invalidate the cached anonymous bootstrap promise and fetch fresh /auth/me
      const freshState = await refreshBrowserSession({ force: true });
      if (!freshState.is_authenticated || !freshState.user) {
        throw new Error(
          "Registratie geslaagd, maar verificatie van de sessie is mislukt. Probeer het opnieuw."
        );
      }

      applySessionState(freshState);
      broadcastAuthChange();
    },
    [applySessionState, broadcastAuthChange]
  );

  const logout = useCallback(async (): Promise<void> => {
    const response = await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error("Uitloggen is niet gelukt. Probeer het opnieuw.");
    }

    const freshState = await refreshBrowserSession({ force: true });
    if (freshState.is_authenticated) {
      throw new Error("De sessie kon niet veilig worden afgemeld.");
    }
    applySessionState(freshState);
    broadcastAuthChange();
  }, [applySessionState, broadcastAuthChange]);

  // Initial single-flight bootstrap
  useEffect(() => {
    let active = true;
    ensureBrowserSession()
      .then((state) => {
        if (!active) return;
        applySessionState(state);
      })
      .catch((error) => {
        if (!active) return;
        if (!isSessionRequestSupersededError(error)) {
          setStatus("error");
        }
      });

    return () => {
      active = false;
    };
  }, [applySessionState]);

  // 401 interceptor subscription
  useEffect(() => {
    return onUnauthorized(() => {
      void refreshAuth().catch(() => {});
    });
  }, [refreshAuth]);

  // Multi-tab sync via BroadcastChannel and localStorage event
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (typeof BroadcastChannel !== "undefined") {
      try {
        const channel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
        broadcastChannelRef.current = channel;
        channel.onmessage = (event) => {
          if (event.data?.type === "AUTH_STATE_CHANGED") {
            void refreshAuth().catch(() => {});
          }
        };
      } catch {
        // Channel unavailable
      }
    }

    const handleStorageEvent = (event: StorageEvent) => {
      if (event.key === STORAGE_SYNC_KEY && event.newValue) {
        void refreshAuth().catch(() => {});
      }
    };

    if (!broadcastChannelRef.current) {
      window.addEventListener("storage", handleStorageEvent);
    }

    return () => {
      window.removeEventListener("storage", handleStorageEvent);
      if (broadcastChannelRef.current) {
        broadcastChannelRef.current.close();
        broadcastChannelRef.current = null;
      }
    };
  }, [refreshAuth]);

  // Focus and visibility bounded refresh (debounced/throttled)
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleVisibilityOrFocus = () => {
      if (document.visibilityState === "hidden") return;
      const now = Date.now();
      if (now - lastFocusRefreshRef.current < FOCUS_REFRESH_THROTTLE_MS) {
        return;
      }
      lastFocusRefreshRef.current = now;
      void refreshAuth().catch(() => {});
    };

    window.addEventListener("focus", handleVisibilityOrFocus);
    document.addEventListener("visibilitychange", handleVisibilityOrFocus);

    return () => {
      window.removeEventListener("focus", handleVisibilityOrFocus);
      document.removeEventListener("visibilitychange", handleVisibilityOrFocus);
    };
  }, [refreshAuth]);

  const value: AuthContextValue = {
    status,
    user,
    sessionId,
    sessionType,
    refreshAuth,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
