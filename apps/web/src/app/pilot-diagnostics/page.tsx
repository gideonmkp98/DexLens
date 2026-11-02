"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

interface PilotSummaryMetrics {
  total_scans: number;
  completion_rate: number;
  top_candidate_acceptance_rate: number;
  candidate_correction_rate: number;
  processing_duration_median_ms: number | null;
  processing_duration_p95_ms: number | null;
  capture_mode_distribution: Record<string, number>;
  failure_categories: Record<string, number>;
  total_feedback_count: number;
  feedback_breakdown: Record<string, number>;
}

export default function PilotDiagnosticsPage() {
  const [metrics, setMetrics] = useState<PilotSummaryMetrics | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [pilotSecret, setPilotSecret] = useState<string>("");
  const [isAuthorized, setIsAuthorized] = useState<boolean>(true);

  const fetchMetrics = useCallback(
    async (token?: string) => {
      setLoading(true);
      setError(null);

      const headers: Record<string, string> = {
        Accept: "application/json",
      };
      const activeToken = token || pilotSecret;
      if (activeToken) {
        headers["X-Pilot-Admin-Token"] = activeToken;
      }

      try {
        const res = await fetch("/api/v1/analytics/admin/summary", {
          headers,
          credentials: "include",
        });

        if (res.status === 401 || res.status === 403) {
          setIsAuthorized(false);
          setLoading(false);
          return;
        }

        if (!res.ok) {
          throw new Error(`API fout status ${res.status}`);
        }

        const data = (await res.json()) as PilotSummaryMetrics;
        setMetrics(data);
        setIsAuthorized(true);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Kon pilot-statistieken niet laden."
        );
      } finally {
        setLoading(false);
      }
    },
    [pilotSecret]
  );

  useEffect(() => {
    void fetchMetrics();
  }, [fetchMetrics]);

  return (
    <main
      id="main-content"
      className="min-h-screen bg-[#20251f] px-4 py-8 text-[#f3efdf] sm:px-6 lg:px-8"
    >
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="flex flex-col justify-between gap-4 border-b border-[#f3efdf]/15 pb-6 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2">
              <span
                className="pokeball brand-ball !h-6 !w-6"
                aria-hidden="true"
              />
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#f1ca53]">
                Fase 8 &bull; Veldvalidatie
              </span>
            </div>
            <h1 className="mt-1 font-serif text-2xl font-bold tracking-tight text-[#f3efdf] sm:text-3xl">
              Pilot &amp; Diagnostiek Dashboard
            </h1>
            <p className="mt-1 text-xs text-[#b6bbaa]">
              Geaggregeerde herkennings-, prestatie- en feedbackmetingen zonder
              persoonsgegevens.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/scan"
              className="rounded-[5px] border border-[#f3efdf]/25 bg-[#252923] px-3.5 py-2 text-xs font-bold text-[#f3efdf] shadow-[3px_3px_0_#10150f] hover:border-[#f1ca53]"
            >
              ← Naar Scanner
            </Link>
            <button
              type="button"
              onClick={() => void fetchMetrics()}
              className="rounded-[5px] border border-[#c6372e] bg-[#c6372e] px-3.5 py-2 text-xs font-black text-[#fffcf5] shadow-[3px_3px_0_#10150f] hover:brightness-110"
            >
              Vernieuwen ↻
            </button>
          </div>
        </div>

        {/* Auth Gate (if protected) */}
        {!isAuthorized && (
          <div className="mx-auto mt-12 max-w-md rounded-[5px] border border-[#f1ca53]/40 bg-[#252923] p-6 text-center shadow-[5px_5px_0_#10150f]">
            <span className="pokeball mx-auto mb-4" aria-hidden="true" />
            <h2 className="font-serif text-lg font-bold text-[#f3efdf]">
              Toegang Beveiligd
            </h2>
            <p className="mt-2 text-xs text-[#b6bbaa]">
              Voer de pilot admin secret in om toegang te krijgen tot het
              diagnostiek dashboard.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void fetchMetrics(pilotSecret);
              }}
              className="mt-4 flex gap-2"
            >
              <input
                type="password"
                value={pilotSecret}
                onChange={(e) => setPilotSecret(e.target.value)}
                placeholder="Pilot Admin Secret"
                aria-label="Pilot Admin Secret"
                className="flex-1 rounded-[3px] border border-[#f3efdf]/25 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] placeholder-[#b6bbaa]/50 focus:border-[#f1ca53] focus:outline-none"
              />
              <button
                type="submit"
                className="rounded-[3px] border border-[#252923] bg-[#f1ca53] px-4 py-2 text-xs font-black text-[#252923]"
              >
                Inloggen
              </button>
            </form>
          </div>
        )}

        {/* Loading & Error States */}
        {loading && isAuthorized && (
          <div className="py-20 text-center font-mono text-xs text-[#b6bbaa]">
            Pilot statistieken laden…
          </div>
        )}

        {error && isAuthorized && (
          <div className="mt-6 rounded-[5px] border border-[#eb6b5d] bg-[#252923] p-4 text-xs text-[#eb6b5d]">
            Fout bij het laden van diagnostiek: {error}
          </div>
        )}

        {/* Metrics Grid */}
        {metrics && isAuthorized && !loading && (
          <div className="mt-8 space-y-8">
            {/* Top KPI row */}
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-4 shadow-[3px_3px_0_#10150f]">
                <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Totaal Scans
                </p>
                <p className="mt-2 font-mono text-2xl font-black text-[#f3efdf]">
                  {metrics.total_scans}
                </p>
              </div>

              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-4 shadow-[3px_3px_0_#10150f]">
                <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Voltooiingsratio
                </p>
                <p className="mt-2 font-mono text-2xl font-black text-emerald-400">
                  {((metrics.completion_rate ?? 0) * 100).toFixed(1)}%
                </p>
              </div>

              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-4 shadow-[3px_3px_0_#10150f]">
                <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Top Match Acceptatie
                </p>
                <p className="mt-2 font-mono text-2xl font-black text-[#f1ca53]">
                  {((metrics.top_candidate_acceptance_rate ?? 0) * 100).toFixed(
                    1
                  )}
                  %
                </p>
              </div>

              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-4 shadow-[3px_3px_0_#10150f]">
                <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Correctieratio
                </p>
                <p className="mt-2 font-mono text-2xl font-black text-[#eb6b5d]">
                  {((metrics.candidate_correction_rate ?? 0) * 100).toFixed(1)}%
                </p>
              </div>

              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-4 shadow-[3px_3px_0_#10150f]">
                <p className="font-mono text-[9px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Mediaan Snelheid
                </p>
                <p className="mt-2 font-mono text-2xl font-black text-[#f3efdf]">
                  {metrics.processing_duration_median_ms != null
                    ? `${Math.round(metrics.processing_duration_median_ms)} ms`
                    : "n.v.t."}
                </p>
                <span className="font-mono text-[9px] text-[#b6bbaa]">
                  {metrics.processing_duration_p95_ms != null
                    ? `p95: ${Math.round(metrics.processing_duration_p95_ms)} ms`
                    : "p95: n.v.t."}
                </span>
              </div>
            </div>

            {/* Middle Section: Modus Vergelijking & Feedback Categorieën */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {/* Opnamemodus Vergelijking */}
              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-5 shadow-[4px_4px_0_#10150f]">
                <h3 className="font-serif text-sm font-bold text-[#f3efdf]">
                  Prestaties per Opnamemodus
                </h3>
                <div className="mt-4 space-y-3">
                  <div className="flex items-center justify-between rounded-[3px] border border-[#f3efdf]/10 bg-[#171c16] p-3 text-xs">
                    <div>
                      <strong className="text-emerald-400">
                        Automatische Live Capture
                      </strong>
                      <p className="text-[10px] text-[#b6bbaa]">
                        Auto-capture triggers
                      </p>
                    </div>
                    <span className="font-mono text-sm font-bold text-[#f3efdf]">
                      {metrics.capture_mode_distribution?.auto ?? 0} scans
                    </span>
                  </div>

                  <div className="flex items-center justify-between rounded-[3px] border border-[#f3efdf]/10 bg-[#171c16] p-3 text-xs">
                    <div>
                      <strong className="text-[#f1ca53]">
                        Handmatige Shutter
                      </strong>
                      <p className="text-[10px] text-[#b6bbaa]">
                        Handmatige sluitertijd
                      </p>
                    </div>
                    <span className="font-mono text-sm font-bold text-[#f3efdf]">
                      {metrics.capture_mode_distribution?.manual ?? 0} scans
                    </span>
                  </div>

                  <div className="flex items-center justify-between rounded-[3px] border border-[#f3efdf]/10 bg-[#171c16] p-3 text-xs">
                    <div>
                      <strong className="text-[#f3efdf]">
                        Foto Upload Fallback
                      </strong>
                      <p className="text-[10px] text-[#b6bbaa]">
                        Bestand upload route
                      </p>
                    </div>
                    <span className="font-mono text-sm font-bold text-[#f3efdf]">
                      {metrics.capture_mode_distribution?.upload ?? 0} scans
                    </span>
                  </div>
                </div>
              </div>

              {/* Gebruikersfeedback Breakdown */}
              <div className="rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-5 shadow-[4px_4px_0_#10150f]">
                <div className="flex items-center justify-between">
                  <h3 className="font-serif text-sm font-bold text-[#f3efdf]">
                    Gebruikersfeedback Signalen
                  </h3>
                  <span className="font-mono text-[10px] text-[#b6bbaa]">
                    {metrics.total_feedback_count} inzendingen
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-[3px] border border-emerald-500/20 bg-emerald-950/20 p-2.5">
                    <span className="font-mono text-base font-black text-emerald-400">
                      {metrics.feedback_breakdown?.correct_match ?? 0}
                    </span>
                    <p className="mt-0.5 text-[10px] text-[#b6bbaa]">
                      Match Klopt (✓)
                    </p>
                  </div>

                  <div className="rounded-[3px] border border-[#eb6b5d]/20 bg-[#eb6b5d]/10 p-2.5">
                    <span className="font-mono text-base font-black text-[#eb6b5d]">
                      {metrics.feedback_breakdown?.wrong_card ?? 0}
                    </span>
                    <p className="mt-0.5 text-[10px] text-[#b6bbaa]">
                      Verkeerde Kaart
                    </p>
                  </div>

                  <div className="rounded-[3px] border border-[#f1ca53]/20 bg-[#f1ca53]/10 p-2.5">
                    <span className="font-mono text-base font-black text-[#f1ca53]">
                      {metrics.feedback_breakdown?.in_alternatives ?? 0}
                    </span>
                    <p className="mt-0.5 text-[10px] text-[#b6bbaa]">
                      In Alternatieven
                    </p>
                  </div>

                  <div className="rounded-[3px] border border-[#f3efdf]/10 bg-[#171c16] p-2.5">
                    <span className="font-mono text-base font-black text-[#f3efdf]">
                      {metrics.feedback_breakdown?.ocr_incorrect ?? 0}
                    </span>
                    <p className="mt-0.5 text-[10px] text-[#b6bbaa]">
                      OCR / Nr Onjuist
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
