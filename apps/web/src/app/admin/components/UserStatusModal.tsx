"use client";

import React from "react";
import type { AdminUserItem } from "@/lib/admin";

interface UserStatusModalProps {
  user: AdminUserItem | null;
  newStatus: "active" | "suspended" | "blocked";
  setNewStatus: (status: "active" | "suspended" | "blocked") => void;
  reason: string;
  setReason: (reason: string) => void;
  updating: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function UserStatusModal({
  user,
  newStatus,
  setNewStatus,
  reason,
  setReason,
  updating,
  error,
  onClose,
  onSubmit,
}: UserStatusModalProps) {
  if (!user) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="status-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
        <h2
          id="status-modal-title"
          className="font-serif text-xl font-bold text-[#f3efdf]"
        >
          Status Wijzigen: {user.email}
        </h2>
        <p className="mt-2 text-xs leading-relaxed text-[#b6bbaa]">
          Schorsen of blokkeren leidt ertoe dat alle actieve browsersessies van
          deze gebruiker onmiddellijk worden beëindigd.
        </p>

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Nieuwe Accountstatus
            </label>
            <select
              value={newStatus}
              onChange={(e) =>
                setNewStatus(e.target.value as "active" | "suspended" | "blocked")
              }
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            >
              <option value="active">Actief (volledige toegang)</option>
              <option value="suspended">
                Geschorst (tijdelijk geblokkeerd)
              </option>
              <option value="blocked">
                Geblokkeerd (permanente uitsluiting)
              </option>
            </select>
          </div>

          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Reden voor statuswijziging (verplicht)
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Bijv. Verdacht burst-patroon of verzoek van gebruiker…"
              required
              rows={3}
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
              className="rounded border border-[#c6372e] bg-[#c6372e] px-4 py-1.5 text-xs font-bold text-[#fffcf5] hover:brightness-110 disabled:opacity-50"
            >
              {updating ? "Bezig…" : "Bevestigen & Toepassen"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
