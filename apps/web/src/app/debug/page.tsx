"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getHealth, HealthResponse } from "@/lib/api";

export default function DebugPage() {
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
    <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-zinc-200 bg-zinc-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-zinc-600 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-400">
              SYSTEM DIAGNOSTICS
            </span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-3xl">
            Service Telemetry
          </h1>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            Internal connectivity monitor for FastAPI backend and MariaDB
            database.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void checkStatus()}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-zinc-800 disabled:opacity-50 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200"
        >
          {loading ? (
            <>
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
              <span>Verifying...</span>
            </>
          ) : (
            <>
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span>Refresh Status</span>
            </>
          )}
        </button>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* API Status */}
        <div className="card-slab rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-obsidian-900">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-zinc-600 dark:text-zinc-400">
              FastAPI Service
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${
                loading
                  ? "border border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                  : isApiConnected
                    ? "border border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "border border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-400"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  loading
                    ? "animate-pulse bg-amber-500"
                    : isApiConnected
                      ? "bg-emerald-500"
                      : "bg-rose-500"
                }`}
              />
              {loading
                ? "Testing..."
                : isApiConnected
                  ? "Connected"
                  : "Disconnected"}
            </span>
          </div>

          <div className="mt-4">
            <span className="font-mono text-xl font-bold text-zinc-900 dark:text-white">
              {health?.status ? health.status.toUpperCase() : "UNKNOWN"}
            </span>
            <p className="mt-1 font-mono text-xs text-zinc-400">
              Endpoint: /api/v1/health
            </p>
          </div>
        </div>

        {/* Database Status */}
        <div className="card-slab rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-obsidian-900">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold text-zinc-600 dark:text-zinc-400">
              MariaDB Database
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold ${
                loading
                  ? "border border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                  : isDbConnected
                    ? "border border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "border border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-400"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  loading
                    ? "animate-pulse bg-amber-500"
                    : isDbConnected
                      ? "bg-emerald-500"
                      : "bg-rose-500"
                }`}
              />
              {loading
                ? "Testing..."
                : isDbConnected
                  ? "Healthy"
                  : "Unreachable"}
            </span>
          </div>

          <div className="mt-4">
            <span className="font-mono text-xl font-bold text-zinc-900 dark:text-white">
              {health?.database ? health.database.toUpperCase() : "UNKNOWN"}
            </span>
            <p className="mt-1 font-mono text-xs text-zinc-400">
              Connection pool &amp; migrations active
            </p>
          </div>
        </div>
      </div>

      {/* Last checked note */}
      {lastChecked && (
        <p className="mt-4 text-center font-mono text-xs text-zinc-400">
          Last health verification: {lastChecked.toLocaleTimeString()}
        </p>
      )}

      {/* Quick Navigation */}
      <div className="card-slab mt-8 rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-obsidian-900">
        <h2 className="font-mono text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
          Application Shortlinks
        </h2>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Link
            href="/"
            className="flex items-center justify-between rounded-xl border border-zinc-200 p-3 font-mono text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-obsidian-850"
          >
            <span>Public Home</span>
            <span>&rarr;</span>
          </Link>
          <Link
            href="/scan"
            className="flex items-center justify-between rounded-xl border border-zinc-200 p-3 font-mono text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-obsidian-850"
          >
            <span>Card Scanner</span>
            <span>&rarr;</span>
          </Link>
          <Link
            href="/cards"
            className="flex items-center justify-between rounded-xl border border-zinc-200 p-3 font-mono text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-obsidian-850"
          >
            <span>Card Catalog</span>
            <span>&rarr;</span>
          </Link>
        </div>
      </div>
    </main>
  );
}
