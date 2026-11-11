"use client";

import React from "react";
import type { AdminUserItem } from "@/lib/admin";

interface UserQuotaModalProps {
  user: AdminUserItem | null;
  quotaValue: string;
  setQuotaValue: (val: string) => void;
  reason: string;
  setReason: (reason: string) => void;
  updating: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function UserQuotaModal({
  user,
  quotaValue,
  setQuotaValue,
  reason,
  setReason,
  updating,
  error,
  onClose,
  onSubmit,
}: UserQuotaModalProps) {
  if (!user) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="quota-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
        <h2
          id="quota-modal-title"
          className="font-serif text-xl font-bold text-[#f3efdf]"
        >
          Scan-quota: {user.email}
        </h2>
        <p className="mt-2 text-xs leading-relaxed text-[#b6bbaa]">
          Stel een individuele dagelijkse scanlimiet in voor deze gebruiker.
          Laat het veld leeg om terug te keren naar de globale limiet.
        </p>

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Dagelijkse scanlimiet override (of leeg voor globaal)
            </label>
            <input
              type="number"
              min={0}
              value={quotaValue}
              onChange={(e) => setQuotaValue(e.target.value)}
              placeholder="Bijv. 250 (leeg = standaard)"
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Reden voor aanpassing (verplicht)
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Bijv. Verzoek van reviewer / power user test…"
              required
              minLength={3}
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          {error && (
            <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2 text-xs text-[#ff9387]">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-[#f3efdf]/20 px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
            >
              Annuleren
            </button>
            <button
              type="submit"
              disabled={updating}
              className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-4 py-1.5 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30 disabled:opacity-50"
            >
              {updating ? "Opslaan…" : "Quota Toepassen"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
