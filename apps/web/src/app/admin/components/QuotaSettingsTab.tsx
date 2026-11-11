"use client";

import React from "react";
import type { GlobalQuotaResponse } from "@/lib/admin";

interface QuotaSettingsTabProps {
  globalQuota: GlobalQuotaResponse | null;
  globalDailyLimit: number;
  setGlobalDailyLimit: (val: number) => void;
  globalHourlyLimit: number;
  setGlobalHourlyLimit: (val: number) => void;
  globalQuotaReason: string;
  setGlobalQuotaReason: (val: string) => void;
  globalQuotaUpdating: boolean;
  globalQuotaSuccess: string | null;
  globalQuotaError: string | null;
  onSubmit: (e: React.FormEvent) => void;
}

export function QuotaSettingsTab({
  globalQuota,
  globalDailyLimit,
  setGlobalDailyLimit,
  globalHourlyLimit,
  setGlobalHourlyLimit,
  globalQuotaReason,
  setGlobalQuotaReason,
  globalQuotaUpdating,
  globalQuotaSuccess,
  globalQuotaError,
  onSubmit,
}: QuotaSettingsTabProps) {
  return (
    <section
      className="mt-6 max-w-2xl space-y-6"
      aria-label="Quota-instellingen"
    >
      <div className="rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-6">
        <h2 className="font-serif text-lg font-bold text-[#f3efdf]">
          Globale Scan-quota Limieten
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-[#b6bbaa]">
          Deze limieten bepalen het maximum aantal scans per dag en per uur voor
          gewone verzamelaars. Individuele accounts kunnen een specifieke
          overschrijving hebben.
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Dagelijkse scanlimiet per gebruiker
            </label>
            <input
              type="number"
              min={1}
              value={globalDailyLimit}
              onChange={(e) =>
                setGlobalDailyLimit(parseInt(e.target.value, 10) || 0)
              }
              required
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-sm text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Uurlijkse scanlimiet per gebruiker
            </label>
            <input
              type="number"
              min={1}
              value={globalHourlyLimit}
              onChange={(e) =>
                setGlobalHourlyLimit(parseInt(e.target.value, 10) || 0)
              }
              required
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-sm text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Reden voor wijziging (verplicht voor auditlog)
            </label>
            <input
              type="text"
              value={globalQuotaReason}
              onChange={(e) => setGlobalQuotaReason(e.target.value)}
              placeholder="Bijv. Uitbreiding pilotfase capaciteit"
              required
              minLength={3}
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-sm text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          {globalQuotaError && (
            <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2.5 text-xs text-[#ff9387]">
              {globalQuotaError}
            </div>
          )}

          {globalQuotaSuccess && (
            <div className="rounded border border-emerald-500/40 bg-emerald-950/40 p-2.5 text-xs text-emerald-300">
              {globalQuotaSuccess}
            </div>
          )}

          <button
            type="submit"
            disabled={globalQuotaUpdating}
            className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-4 py-2.5 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30 disabled:opacity-50"
          >
            {globalQuotaUpdating ? "Opslaan…" : "Globale Quota Bijwerken"}
          </button>
        </form>

        {globalQuota?.updated_at && (
          <p className="mt-4 font-mono text-[10px] text-[#b6bbaa]/50">
            Laatst bijgewerkt op:{" "}
            {new Date(globalQuota.updated_at).toLocaleString("nl-NL")}
          </p>
        )}
      </div>
    </section>
  );
}
