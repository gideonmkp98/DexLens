"use client";

import { useEffect, useRef } from "react";

export interface ScannerOnboardingModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ScannerOnboardingModal({
  isOpen,
  onClose,
}: ScannerOnboardingModalProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    closeBtnRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="scanner-tips-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-md rounded-[5px] border border-[#f3efdf]/30 bg-[#20251f] p-5 text-[#f3efdf] shadow-[5px_5px_0_#10150f] sm:p-6">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#f3efdf]/15 pb-3">
          <div className="flex items-center gap-2">
            <span
              className="pokeball brand-ball !h-6 !w-6"
              aria-hidden="true"
            />
            <h2
              id="scanner-tips-title"
              className="font-serif text-base font-bold tracking-tight text-[#f3efdf]"
            >
              Scan Tips voor Verzamelaars
            </h2>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-[3px] border border-[#f3efdf]/30 text-xs font-bold text-[#f3efdf] hover:border-[#f1ca53]"
            aria-label="Sluit tips"
          >
            ✕
          </button>
        </div>

        {/* Tip Items */}
        <div className="mt-4 space-y-3.5 text-xs text-[#f3efdf]/90">
          <div className="flex gap-3 rounded-[3px] border border-[#f3efdf]/15 bg-[#252923] p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#f1ca53] font-mono text-xs font-black text-[#20251f]">
              1
            </span>
            <div>
              <strong className="block font-semibold text-[#f1ca53]">
                Plaatsing in het kader
              </strong>
              <p className="mt-0.5 leading-relaxed text-[#f3efdf]/80">
                Houd de kaart binnen de witte hoeken. Vul ongeveer 70% van het
                scherm voor de scherpste randdetectie en tekstherkenning.
              </p>
            </div>
          </div>

          <div className="flex gap-3 rounded-[3px] border border-[#f3efdf]/15 bg-[#252923] p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#f1ca53] font-mono text-xs font-black text-[#20251f]">
              2
            </span>
            <div>
              <strong className="block font-semibold text-[#f1ca53]">
                Licht & Weerspiegeling
              </strong>
              <p className="mt-0.5 leading-relaxed text-[#f3efdf]/80">
                Voorkom directe lampreflecties op holo of folie kaarten. Kantel
                de kaart een klein beetje bij te felle glans.
              </p>
            </div>
          </div>

          <div className="flex gap-3 rounded-[3px] border border-[#f3efdf]/15 bg-[#252923] p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#f1ca53] font-mono text-xs font-black text-[#20251f]">
              3
            </span>
            <div>
              <strong className="block font-semibold text-[#f1ca53]">
                Auto vs. Zelf
              </strong>
              <p className="mt-0.5 leading-relaxed text-[#f3efdf]/80">
                <strong>Auto:</strong> Maakt automatisch een foto zodra de kaart
                volledig stabiel ligt.
                <br />
                <strong>Zelf:</strong> Bepaal zelf het moment via de grote knop.
              </p>
            </div>
          </div>
        </div>

        {/* Action Button */}
        <div className="mt-5 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-[5px] border border-[#c6372e] bg-[#c6372e] py-2.5 text-xs font-black uppercase tracking-wider text-[#fffcf5] shadow-[3px_3px_0_#10150f] transition hover:brightness-110 active:translate-x-[1px] active:translate-y-[1px]"
          >
            Begrepen & Start Scanner
          </button>
        </div>
      </div>
    </div>
  );
}
