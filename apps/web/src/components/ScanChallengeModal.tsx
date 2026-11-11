"use client";

import { useEffect, useState } from "react";
import TurnstileWidget from "@/components/TurnstileWidget";

export interface ScanChallengeModalProps {
  isOpen: boolean;
  siteKey?: string;
  onSolved: (token: string) => void;
  onCancel: () => void;
}

export default function ScanChallengeModal({
  isOpen,
  siteKey,
  onSolved,
  onCancel,
}: ScanChallengeModalProps) {
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setToken(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCancel();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const handleVerify = (receivedToken: string) => {
    setToken(receivedToken);
    // Smooth transition to allow the user to see success
    setTimeout(() => {
      onSolved(receivedToken);
    }, 400);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="challenge-modal-title"
      aria-describedby="challenge-modal-description"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f] sm:p-8">
        <div className="flex items-start justify-between gap-4 border-b border-[#f3efdf]/15 pb-4">
          <div className="flex items-center gap-3">
            <span
              className="pokeball brand-ball !h-7 !w-7"
              aria-hidden="true"
            />
            <div>
              <h2
                id="challenge-modal-title"
                className="font-serif text-xl font-bold tracking-tight text-[#f3efdf]"
              >
                Beveiligingscontrole
              </h2>
              <p className="font-mono text-[10px] uppercase tracking-wider text-[#f1ca53]">
                Piekdetectie actief
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="flex h-8 w-8 items-center justify-center rounded border border-[#f3efdf]/20 text-xs font-bold text-[#b6bbaa] transition hover:border-[#f1ca53] hover:text-[#f3efdf]"
            aria-label="Annuleer controle"
          >
            ✕
          </button>
        </div>

        <div className="mt-4">
          <p
            id="challenge-modal-description"
            className="text-sm leading-relaxed text-[#b6bbaa]"
          >
            Er zijn meerdere snelle scanverzoeken waargenomen vanaf dit netwerk.
            Voltooi de onderstaande verificatie om direct verder te gaan.
          </p>

          <div className="my-6 flex justify-center">
            <TurnstileWidget
              siteKey={siteKey}
              action="scan_burst_challenge"
              onVerify={handleVerify}
            />
          </div>

          {token && (
            <div className="rounded border border-emerald-500/40 bg-emerald-950/40 p-2.5 text-center text-xs font-bold text-emerald-300">
              ✓ Verificatie geslaagd! Scan wordt voortgezet…
            </div>
          )}

          <div className="mt-6 flex justify-end gap-3 border-t border-[#f3efdf]/10 pt-4">
            <button
              type="button"
              onClick={onCancel}
              className="rounded border border-[#f3efdf]/20 px-4 py-2 text-xs font-semibold text-[#b6bbaa] transition hover:text-[#f3efdf]"
            >
              Annuleren
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
