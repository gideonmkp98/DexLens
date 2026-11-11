"use client";

import React from "react";
import type { BetaCodeResponse } from "@/lib/admin";

interface BetaCodesTabProps {
  betaCodes: BetaCodeResponse[];
  betaTotal: number;
  betaLoading: boolean;
  betaSearch: string;
  setBetaSearch: (val: string) => void;
  betaStatusFilter: string;
  setBetaStatusFilter: (val: string) => void;
  onRefresh: () => void;
  onOpenCreateModal: () => void;
  onOpenRevokeModal: (code: BetaCodeResponse) => void;
}

export function BetaCodesTab({
  betaCodes,
  betaTotal,
  betaLoading,
  betaSearch,
  setBetaSearch,
  betaStatusFilter,
  setBetaStatusFilter,
  onRefresh,
  onOpenCreateModal,
  onOpenRevokeModal,
}: BetaCodesTabProps) {
  return (
    <section className="mt-6 space-y-6" aria-label="Bètacodes & Uitnodigingen">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <input
            type="text"
            value={betaSearch}
            onChange={(e) => setBetaSearch(e.target.value)}
            placeholder="Zoek code of label…"
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] placeholder:text-[#b6bbaa]/50 focus:border-[#f1ca53] focus:outline-none"
          />
          <select
            value={betaStatusFilter}
            onChange={(e) => setBetaStatusFilter(e.target.value)}
            aria-label="Filter op status"
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
          >
            <option value="">Alle statussen</option>
            <option value="active">Actief</option>
            <option value="exhausted">Opgebruikt</option>
            <option value="expired">Verlopen</option>
            <option value="revoked">Ingetrokken</option>
          </select>
          <button
            type="button"
            onClick={onRefresh}
            className="rounded border border-[#f3efdf]/20 bg-[#20251f] px-3 py-2 font-bold text-[#f3efdf] hover:border-[#f1ca53]"
          >
            Vernieuwen
          </button>
        </div>
        <button
          type="button"
          onClick={onOpenCreateModal}
          className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-3.5 py-2 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30"
        >
          + Nieuwe Bètacode
        </button>
      </div>

      {/* Beta Codes Table */}
      <div className="overflow-x-auto rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f]">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-[#f3efdf]/15 bg-[#171c16] font-mono text-[10px] uppercase text-[#b6bbaa]">
            <tr>
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Label</th>
              <th className="px-4 py-3">Uitnodiging voor</th>
              <th className="px-4 py-3">Gebruik</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Verloopt</th>
              <th className="px-4 py-3 text-right">Actie</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#f3efdf]/10">
            {betaLoading ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-[#b6bbaa]"
                >
                  Bètacodes laden…
                </td>
              </tr>
            ) : betaCodes.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-[#b6bbaa]"
                >
                  Geen bètacodes gevonden.
                </td>
              </tr>
            ) : (
              betaCodes.map((code) => (
                <tr key={code.id} className="hover:bg-[#1a1f19]/70">
                  <td className="px-4 py-3 font-mono font-bold text-[#f1ca53]">
                    {code.code}
                  </td>
                  <td className="px-4 py-3 text-[#f3efdf]">
                    {code.label || "—"}
                  </td>
                  <td className="px-4 py-3 text-[#b6bbaa]">
                    {code.invitation_email || "Iedereen"}
                  </td>
                  <td className="px-4 py-3 font-mono">
                    {code.used_count} / {code.max_uses}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                        code.status === "active"
                          ? "border border-emerald-500/30 bg-emerald-950 text-emerald-300"
                          : code.status === "revoked"
                            ? "border border-rose-500/30 bg-rose-950 text-rose-300"
                            : "bg-[#171c16] text-[#b6bbaa]"
                      }`}
                    >
                      {code.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-[10px] text-[#b6bbaa]">
                    {code.expires_at
                      ? new Date(code.expires_at).toLocaleDateString("nl-NL")
                      : "Onbeperkt"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {code.status === "active" && (
                      <button
                        type="button"
                        onClick={() => onOpenRevokeModal(code)}
                        className="rounded border border-[#eb6b5d]/30 bg-[#eb6b5d]/10 px-2 py-1 text-[11px] font-semibold text-[#ff9387] hover:bg-[#eb6b5d]/20"
                      >
                        Intrekken
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="text-right text-xs text-[#b6bbaa]">
        Totaal geregistreerde codes: {betaTotal}
      </div>
    </section>
  );
}
