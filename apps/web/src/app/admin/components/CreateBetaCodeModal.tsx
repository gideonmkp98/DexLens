"use client";

import React from "react";

interface CreateBetaCodeModalProps {
  isOpen: boolean;
  label: string;
  setLabel: (val: string) => void;
  email: string;
  setEmail: (val: string) => void;
  maxUses: number;
  setMaxUses: (val: number) => void;
  expiresDays: number;
  setExpiresDays: (val: number) => void;
  creating: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function CreateBetaCodeModal({
  isOpen,
  label,
  setLabel,
  email,
  setEmail,
  maxUses,
  setMaxUses,
  expiresDays,
  setExpiresDays,
  creating,
  error,
  onClose,
  onSubmit,
}: CreateBetaCodeModalProps) {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-beta-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
        <h2
          id="create-beta-modal-title"
          className="font-serif text-xl font-bold text-[#f3efdf]"
        >
          Nieuwe Bètacode Aanmaken
        </h2>

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Label / Omschrijving
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Bijv. Early Tester Cohort #2"
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
              Gekoppeld E-mailadres (optioneel)
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="verzamelaar@voorbeeld.nl"
              className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                Max. gebruik
              </label>
              <input
                type="number"
                min={1}
                value={maxUses}
                onChange={(e) =>
                  setMaxUses(parseInt(e.target.value, 10) || 1)
                }
                className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                Geldigheid (dagen)
              </label>
              <input
                type="number"
                min={1}
                value={expiresDays}
                onChange={(e) =>
                  setExpiresDays(parseInt(e.target.value, 10) || 30)
                }
                className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
              />
            </div>
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
              disabled={creating}
              className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-4 py-1.5 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30 disabled:opacity-50"
            >
              {creating ? "Bezig…" : "Code Aanmaken"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
