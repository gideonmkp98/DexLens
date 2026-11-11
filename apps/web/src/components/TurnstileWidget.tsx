"use client";

import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement | string,
        options: {
          sitekey: string;
          action?: string;
          theme?: "auto" | "light" | "dark";
          callback?: (token: string) => void;
          "error-callback"?: (error?: string) => void;
          "expired-callback"?: () => void;
        }
      ) => string;
      reset: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
    onloadTurnstileCallback?: () => void;
  }
}

export interface TurnstileWidgetProps {
  siteKey?: string;
  action?: string;
  onVerify: (token: string) => void;
  onError?: (err?: string) => void;
  onExpire?: () => void;
  theme?: "auto" | "light" | "dark";
  className?: string;
}

const DEFAULT_DEV_KEY = "1x00000000000000000000AA";

export default function TurnstileWidget({
  siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || DEFAULT_DEV_KEY,
  action,
  onVerify,
  onError,
  onExpire,
  theme = "dark",
  className = "",
}: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isScriptLoaded, setIsScriptLoaded] = useState<boolean>(false);
  const [hasSimulated, setHasSimulated] = useState<boolean>(false);

  const isLocalOrTestKey =
    siteKey === DEFAULT_DEV_KEY ||
    siteKey.startsWith("1x") ||
    siteKey.startsWith("2x") ||
    process.env.NODE_ENV === "development";

  // Load Turnstile explicit script once
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (window.turnstile) {
      setIsScriptLoaded(true);
      return;
    }

    const scriptId = "cf-turnstile-script";
    const existingScript = document.getElementById(scriptId) as HTMLScriptElement | null;

    if (existingScript) {
      const handleLoad = () => setIsScriptLoaded(true);
      existingScript.addEventListener("load", handleLoad);
      return () => existingScript.removeEventListener("load", handleLoad);
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.defer = true;

    script.onload = () => {
      setIsScriptLoaded(true);
    };

    script.onerror = () => {
      setLoadError("Kan beveiligingscontrole niet laden. Schakel je adblocker uit of controleer je verbinding.");
      if (onError) onError("script_load_failed");
    };

    document.head.appendChild(script);

    // Timeout check in case script is silently blocked by content blocker
    const timer = setTimeout(() => {
      if (!window.turnstile && !loadError) {
        setLoadError("Beveiligingscontrole reageert niet. Mogelijk blokkeert een adblocker Cloudflare Turnstile.");
      }
    }, 6000);

    return () => clearTimeout(timer);
  }, [loadError, onError]);

  // Render Turnstile widget once script is ready
  useEffect(() => {
    if (!isScriptLoaded || !containerRef.current || !window.turnstile) return;

    // Reset or clean up any prior widget
    if (widgetIdRef.current) {
      try {
        window.turnstile.remove(widgetIdRef.current);
      } catch {
        // ignore cleanup error
      }
      widgetIdRef.current = null;
    }

    try {
      const id = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        action,
        theme,
        callback: (token: string) => {
          setLoadError(null);
          onVerify(token);
        },
        "error-callback": (error?: string) => {
          const msg = `Verificatiefout: ${error || "Mislukt"}`;
          setLoadError(msg);
          if (onError) onError(error);
        },
        "expired-callback": () => {
          if (onExpire) onExpire();
        },
      });

      widgetIdRef.current = id;
    } catch (renderErr) {
      const msg = renderErr instanceof Error ? renderErr.message : "Fout bij renderen";
      setLoadError(`Kan widget niet weergeven: ${msg}`);
      if (onError) onError(msg);
    }

    return () => {
      if (widgetIdRef.current && window.turnstile) {
        try {
          window.turnstile.remove(widgetIdRef.current);
        } catch {
          // ignore
        }
        widgetIdRef.current = null;
      }
    };
  }, [isScriptLoaded, siteKey, action, theme, onVerify, onError, onExpire]);

  const handleSimulateLocal = () => {
    setHasSimulated(true);
    setLoadError(null);
    onVerify("XXXX.DUMMY.TOKEN.XXXX");
  };

  const handleRetry = () => {
    setLoadError(null);
    setHasSimulated(false);
    if (widgetIdRef.current && window.turnstile) {
      try {
        window.turnstile.reset(widgetIdRef.current);
      } catch {
        // ignore
      }
    }
  };

  return (
    <div
      role="region"
      aria-label="Beveiligingsverificatie"
      className={`turnstile-wrapper my-2 flex flex-col items-center justify-center min-h-[65px] ${className}`}
    >
      <div ref={containerRef} className="cf-turnstile" />

      {loadError && (
        <div
          role="alert"
          className="mt-2 w-full rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2.5 text-center text-xs text-[#ff9387]"
        >
          <p>{loadError}</p>
          <div className="mt-2 flex items-center justify-center gap-2">
            <button
              type="button"
              onClick={handleRetry}
              className="rounded bg-[#20251f] px-2.5 py-1 text-xs font-semibold text-[#f3efdf] hover:border-[#f1ca53] border border-[#f3efdf]/20"
            >
              Opnieuw proberen
            </button>
            {isLocalOrTestKey && (
              <button
                type="button"
                onClick={handleSimulateLocal}
                className="rounded bg-emerald-900/60 px-2.5 py-1 text-xs font-semibold text-emerald-300 border border-emerald-500/30 hover:bg-emerald-900"
              >
                Simuleer verificatie (Lokale modus)
              </button>
            )}
          </div>
        </div>
      )}

      {hasSimulated && !loadError && (
        <div className="mt-1 text-[11px] font-mono text-emerald-400">
          ✓ Lokale testverificatie actief
        </div>
      )}
    </div>
  );
}
