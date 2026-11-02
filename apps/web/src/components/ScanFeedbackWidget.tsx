"use client";

import { useState } from "react";
import { trackEvent } from "@/lib/analytics";

export type FeedbackType =
  | "correct_match"
  | "wrong_card"
  | "in_alternatives"
  | "not_found"
  | "ocr_incorrect"
  | "crop_failed"
  | "too_slow"
  | "other";

export interface ScanFeedbackWidgetProps {
  scanId: string;
  suggestedCardId?: string | null;
  selectedCardId?: string | null;
  confidenceState?: "high" | "medium" | "low" | "none" | string | null;
  selectedInCandidates?: boolean | null;
  onSubmitted?: () => void;
  className?: string;
}

export default function ScanFeedbackWidget({
  scanId,
  suggestedCardId,
  selectedCardId,
  confidenceState,
  selectedInCandidates,
  onSubmitted,
  className = "",
}: ScanFeedbackWidgetProps) {
  const [status, setStatus] = useState<
    "idle" | "options" | "submitting" | "done"
  >("idle");
  const [selectedType, setSelectedType] = useState<FeedbackType | null>(null);
  const [notes, setNotes] = useState<string>("");

  const submitFeedback = async (type: FeedbackType, textNotes?: string) => {
    setStatus("submitting");
    setSelectedType(type);

    try {
      await fetch(`/api/v1/feedback/scans/${scanId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          feedback_type: type,
          suggested_card_id: suggestedCardId ?? null,
          selected_card_id: selectedCardId ?? null,
          confidence_state: confidenceState ?? null,
          selected_in_candidates: selectedInCandidates ?? null,
          notes: textNotes?.trim() ? textNotes.trim().slice(0, 500) : null,
        }),
      });

      trackEvent("user_feedback_submitted", {
        scan_id: scanId,
        metadata: { feedback_type: type },
      });

      setStatus("done");
      onSubmitted?.();
    } catch {
      // Non-fatal if feedback API is unreachable
      setStatus("done");
    }
  };

  if (status === "done") {
    return (
      <div
        data-testid="scan-feedback-success"
        className={`rounded-[3px] border border-[#f1ca53]/30 bg-[#252923] px-3 py-2 text-center text-xs font-bold text-[#f1ca53] ${className}`}
      >
        ✓ Bedankt voor je feedback! Hiermee verbeteren we de herkenning.
      </div>
    );
  }

  return (
    <div
      data-testid="scan-feedback-widget"
      className={`rounded-[5px] border border-[#f3efdf]/15 bg-[#252923] p-3 text-[#f3efdf] ${className}`}
    >
      {status === "idle" && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-bold text-[#d9d4c4]">
            Klopt deze kaartmatch?
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => void submitFeedback("correct_match")}
              className="rounded-[3px] border border-emerald-500/40 bg-emerald-950/40 px-2.5 py-1 text-xs font-bold text-emerald-300 transition hover:bg-emerald-900/60"
            >
              ✓ Klopt
            </button>
            <button
              type="button"
              onClick={() => setStatus("options")}
              className="rounded-[3px] border border-[#f3efdf]/20 bg-[#20251f] px-2.5 py-1 text-xs font-bold text-[#f3efdf]/90 transition hover:border-[#eb6b5d] hover:text-[#eb6b5d]"
            >
              ✕ Niet juist
            </button>
          </div>
        </div>
      )}

      {status === "options" && (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#f1ca53]">
              Wat ging er mis?
            </span>
            <button
              type="button"
              onClick={() => setStatus("idle")}
              className="text-xs text-[#b6bbaa] hover:text-[#f3efdf]"
            >
              Annuleren
            </button>
          </div>

          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => void submitFeedback("in_alternatives")}
              className="rounded-[3px] border border-[#f3efdf]/15 bg-[#20251f] p-2 text-left text-xs text-[#f3efdf] hover:border-[#f1ca53]"
            >
              Juiste kaart stond in alternatieven
            </button>
            <button
              type="button"
              onClick={() => void submitFeedback("not_found")}
              className="rounded-[3px] border border-[#f3efdf]/15 bg-[#20251f] p-2 text-left text-xs text-[#f3efdf] hover:border-[#f1ca53]"
            >
              Juiste kaart niet gevonden
            </button>
            <button
              type="button"
              onClick={() => void submitFeedback("ocr_incorrect")}
              className="rounded-[3px] border border-[#f3efdf]/15 bg-[#20251f] p-2 text-left text-xs text-[#f3efdf] hover:border-[#f1ca53]"
            >
              Kaartnummer of tekst verkeerd gelezen
            </button>
            <button
              type="button"
              onClick={() => void submitFeedback("crop_failed")}
              className="rounded-[3px] border border-[#f3efdf]/15 bg-[#20251f] p-2 text-left text-xs text-[#f3efdf] hover:border-[#f1ca53]"
            >
              Kaartkader of uitsnede mislukt
            </button>
          </div>

          <div className="flex gap-2 pt-1">
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optionele toelichting (bv. glans/sleeve)..."
              maxLength={200}
              className="flex-1 rounded-[3px] border border-[#f3efdf]/20 bg-[#171c16] px-2.5 py-1.5 text-xs text-[#f3efdf] placeholder-[#b6bbaa]/50 focus:border-[#f1ca53] focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void submitFeedback("other", notes)}
              className="rounded-[3px] border border-[#252923] bg-[#c6372e] px-3 py-1.5 text-xs font-bold text-[#fffcf5] transition hover:brightness-110"
            >
              Verzenden
            </button>
          </div>
        </div>
      )}

      {status === "submitting" && (
        <div className="py-2 text-center text-xs text-[#b6bbaa]">
          Feedback opslaan…
        </div>
      )}
    </div>
  );
}
