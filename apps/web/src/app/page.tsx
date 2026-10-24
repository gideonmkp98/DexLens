"use client";

import { useCallback, useEffect, useState } from "react";
import { getHealth, HealthResponse } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkStatus = useCallback(async () => {
    setLoading(true);
    const result = await getHealth();
    setHealth(result);
    setLastChecked(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    void checkStatus();
  }, [checkStatus]);

  const isApiConnected = health !== null && health.status !== "disconnected";
  const isDbConnected = health !== null && health.database === "connected";

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6 text-slate-900">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Pokémon TCG Scanner
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Phase 1: System Foundation &amp; Health Monitor
        </p>

        <div className="mt-6 space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-4">
            <span className="text-sm font-medium text-slate-700">
              API Status
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full ${
                  loading
                    ? "animate-pulse bg-amber-400"
                    : isApiConnected
                      ? "bg-emerald-500"
                      : "bg-rose-500"
                }`}
              />
              <span
                className={`text-sm font-semibold ${
                  loading
                    ? "text-slate-500"
                    : isApiConnected
                      ? "text-emerald-700"
                      : "text-rose-700"
                }`}
              >
                {loading
                  ? "Checking..."
                  : isApiConnected
                    ? "Connected"
                    : "Disconnected"}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-4">
            <span className="text-sm font-medium text-slate-700">
              Database Status
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full ${
                  loading
                    ? "animate-pulse bg-amber-400"
                    : isDbConnected
                      ? "bg-emerald-500"
                      : "bg-rose-500"
                }`}
              />
              <span
                className={`text-sm font-semibold ${
                  loading
                    ? "text-slate-500"
                    : isDbConnected
                      ? "text-emerald-700"
                      : "text-rose-700"
                }`}
              >
                {loading
                  ? "Checking..."
                  : isDbConnected
                    ? "Connected"
                    : "Disconnected"}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-col gap-3">
          <button
            type="button"
            onClick={() => void checkStatus()}
            disabled={loading}
            className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? "Checking..." : "Refresh Status"}
          </button>

          {lastChecked && (
            <p className="text-center text-xs text-slate-400">
              Last checked: {lastChecked.toLocaleTimeString()}
            </p>
          )}

          <div className="mt-4 flex items-center justify-between gap-2 border-t border-slate-100 pt-4 text-xs font-semibold">
            <a
              href="/cards"
              className="flex-1 rounded-lg border border-slate-200 py-2 text-center text-slate-700 transition hover:bg-slate-50"
            >
              Browse Cards &rarr;
            </a>
            <a
              href="/sets"
              className="flex-1 rounded-lg border border-slate-200 py-2 text-center text-slate-700 transition hover:bg-slate-50"
            >
              Browse Sets &rarr;
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
