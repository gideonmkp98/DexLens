"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  addScanToCollection,
  ApiError,
  CandidateMatchItem,
  CollectionItem,
  confirmCatalogCard,
  LiveCaptureResponse,
} from "@/lib/api";

export interface LiveScanMatchModalProps {
  isOpen: boolean;
  captureResult: LiveCaptureResponse | null;
  onClose: () => void;
  onRetake: () => void;
  onCardAddedToCollection?: (item: CollectionItem) => void;
}

export default function LiveScanMatchModal({
  isOpen,
  captureResult,
  onClose,
  onRetake,
  onCardAddedToCollection,
}: LiveScanMatchModalProps) {
  const [activeMatch, setActiveMatch] = useState<CandidateMatchItem | null>(
    null
  );
  const [showAlternatives, setShowAlternatives] = useState<boolean>(false);
  const [isAdding, setIsAdding] = useState<boolean>(false);
  const [isSelectingAlt, setIsSelectingAlt] = useState<boolean>(false);
  const [addedItem, setAddedItem] = useState<CollectionItem | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Sync state whenever captureResult updates
  useEffect(() => {
    if (captureResult) {
      setActiveMatch(
        captureResult.best_match || captureResult.candidates[0] || null
      );
      setAddedItem(null);
      setActionError(null);
      setShowAlternatives(captureResult.scan.confidence_state === "low");
    }
  }, [captureResult]);

  // Handle escape key to rearm
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !captureResult) {
    return null;
  }

  const scan = captureResult.scan;
  const match = activeMatch;
  const hasExistingInCollection =
    Boolean(addedItem) || Boolean(captureResult.in_collection);
  const isThisScanAdded = Boolean(addedItem);
  const collectionQty =
    (addedItem?.quantity ?? captureResult.collection_quantity) || 1;

  // Confidence calculations
  const confidenceScore =
    match?.score !== undefined && match?.score !== null
      ? Math.round(match.score)
      : scan.ocr_confidence !== undefined && scan.ocr_confidence !== null
        ? Math.round(scan.ocr_confidence)
        : null;
  const confidenceState =
    scan.confidence_state ||
    (confidenceScore !== null && confidenceScore >= 75
      ? "high"
      : confidenceScore !== null && confidenceScore >= 45
        ? "medium"
        : "low");
  const isLowConfidence = confidenceState === "low";
  const confidenceLabel =
    confidenceState === "high"
      ? "Sterke match"
      : confidenceState === "medium"
        ? "Waarschijnlijke match"
        : "Controleer deze suggestie";

  const handleAddToCollection = async () => {
    if (isAdding || isThisScanAdded) return;
    setIsAdding(true);
    setActionError(null);

    try {
      if (!scan.confirmed_card && match) {
        await confirmCatalogCard(scan.id, {
          card_id: match.id,
          expected_crop_version: scan.crop_version || 1,
        });
      }
      const item = await addScanToCollection(scan.id);
      setAddedItem(item);
      onCardAddedToCollection?.(item);
    } catch (err) {
      setActionError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Kon de kaart niet toevoegen aan de collectie."
      );
    } finally {
      setIsAdding(false);
    }
  };

  const handleSelectAlternative = async (candidate: CandidateMatchItem) => {
    setIsSelectingAlt(true);
    setActionError(null);

    try {
      await confirmCatalogCard(scan.id, {
        card_id: candidate.id,
        expected_crop_version: scan.crop_version || 1,
      });
      setActiveMatch(candidate);
      setAddedItem(null);
    } catch (err) {
      setActionError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Kon de alternatieve kaart niet bevestigen."
      );
    } finally {
      setIsSelectingAlt(false);
    }
  };

  // Alternative candidates list
  const alternativeCandidates = captureResult.candidates.filter(
    (c) => c.id !== match?.id
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#10150f]/90 p-0 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="live-scan-match-title"
    >
      {/* Background overlay click */}
      <div className="fixed inset-0" onClick={onClose} aria-hidden="true" />

      {/* Modal Dialog Card / Sheet */}
      <div className="relative z-10 flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-t-[10px] border border-[#f3efdf]/25 bg-[#20251f] text-[#f3efdf] shadow-[0_-6px_0_#10150f] sm:rounded-[10px] sm:shadow-[7px_7px_0_#10150f]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#f3efdf]/15 px-5 py-4">
          <div className="flex items-center gap-2">
            <span
              className={`flex h-2.5 w-2.5 rounded-full ${
                confidenceState === "high"
                  ? "bg-emerald-400"
                  : isLowConfidence
                    ? "bg-[#eb6b5d]"
                    : "bg-[#f1ca53]"
              }`}
            />
            <h2
              id="live-scan-match-title"
              className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#f3efdf]"
            >
              {confidenceLabel}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Sluit dialoogvenster"
            className="flex h-8 w-8 items-center justify-center rounded-[5px] border border-[#f3efdf]/20 text-[#b6bbaa] transition hover:border-[#eb6b5d] hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* Content body */}
        <div className="scrollbar-thin flex-1 overflow-y-auto p-6">
          {actionError && (
            <div
              role="alert"
              className="mb-4 rounded-[5px] border border-[#eb6b5d] bg-[#171c16] p-3 text-xs text-[#f3efdf]"
            >
              {actionError}
            </div>
          )}

          {match ? (
            <div>
              <div
                className={`mb-5 rounded-[5px] border p-3 text-xs leading-relaxed ${
                  isLowConfidence
                    ? "border-[#eb6b5d]/70 bg-[#eb6b5d]/10 text-[#f3efdf]"
                    : confidenceState === "medium"
                      ? "border-[#f1ca53]/60 bg-[#f1ca53]/10 text-[#f3efdf]"
                      : "border-emerald-400/35 bg-emerald-400/10 text-emerald-100"
                }`}
              >
                <strong className="font-black">{confidenceLabel}.</strong>{" "}
                {isLowConfidence
                  ? "Vergelijk de afbeelding en kies zo nodig een andere mogelijkheid voordat je de kaart toevoegt."
                  : "Vergelijk de afbeelding kort met je kaart voordat je bevestigt."}
              </div>
              {/* Primary Card Slab */}
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
                {/* Artwork */}
                <div className="relative mx-auto aspect-card w-40 flex-shrink-0 overflow-hidden rounded-[6px] border-2 border-[#f1ca53]/65 bg-[#171c16] shadow-[5px_5px_0_#10150f] sm:mx-0 sm:w-44">
                  {match.image_url || scan.crop_image_url ? (
                    <Image
                      src={match.image_url || scan.crop_image_url || ""}
                      alt={match.name}
                      fill
                      sizes="176px"
                      className="object-contain"
                      unoptimized
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center font-mono text-xs text-[#8d9485]">
                      Geen afbeelding
                    </div>
                  )}

                  {confidenceScore !== null && (
                    <span className="absolute bottom-2 left-2 rounded-[3px] border border-[#f3efdf]/25 bg-[#171c16]/95 px-2 py-0.5 font-mono text-[10px] font-bold text-[#f1ca53]">
                      Rangscore {confidenceScore}/100
                    </span>
                  )}
                </div>

                {/* Details */}
                <div className="flex flex-1 flex-col justify-center">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-[3px] border border-[#f3efdf]/15 bg-[#171c16] px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-[#d9d4c4]">
                      #{match.local_id}
                    </span>
                    {hasExistingInCollection && (
                      <span className="rounded-full border border-emerald-500/30 bg-emerald-500/20 px-2.5 py-0.5 text-[10px] font-bold text-emerald-300">
                        In collectie (×{collectionQty})
                      </span>
                    )}
                  </div>

                  <h3 className="mt-2 text-xl font-black tracking-tight text-[#f3efdf] sm:text-2xl">
                    {match.name}
                  </h3>

                  <p className="mt-1 font-mono text-xs text-[#b6bbaa]">
                    {match.set_name}
                  </p>

                  {match.reasons && match.reasons.length > 0 && (
                    <p className="mt-2 text-[11px] leading-relaxed text-[#9fa696]">
                      {match.reasons.join(" · ")}
                    </p>
                  )}

                  {/* Actions */}
                  <div className="mt-5 flex flex-col gap-2.5 sm:flex-row">
                    <button
                      type="button"
                      onClick={handleAddToCollection}
                      disabled={isAdding || isThisScanAdded}
                      className={`inline-flex items-center justify-center gap-2 rounded-[5px] border px-4 py-2.5 text-xs font-black shadow-[3px_3px_0_#10150f] transition active:translate-x-0.5 active:translate-y-0.5 active:shadow-none ${
                        isThisScanAdded
                          ? "cursor-default border-emerald-500/40 bg-emerald-500/20 text-emerald-300"
                          : "border-[#252923] bg-[#c6372e] text-[#fff9ee] hover:bg-[#d94b40]"
                      }`}
                    >
                      {isAdding ? (
                        <>
                          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                          <span>Toevoegen…</span>
                        </>
                      ) : isThisScanAdded ? (
                        <>
                          <span>In collectie</span>
                          <span aria-hidden="true">✓</span>
                        </>
                      ) : (
                        <>
                          <span>
                            {isLowConfidence
                              ? "Bevestig & voeg toe"
                              : "Voeg toe aan collectie"}
                          </span>
                          <span aria-hidden="true">+</span>
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={onClose}
                      className="inline-flex items-center justify-center gap-2 rounded-[5px] border border-[#f3efdf]/25 bg-[#2a3028] px-5 py-2.5 text-xs font-bold text-[#f3efdf] transition hover:border-[#f1ca53] active:scale-95"
                    >
                      <span>Volgende kaart scannen</span>
                      <span aria-hidden="true">→</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Alternative candidates accordion */}
              {alternativeCandidates.length > 0 && (
                <div className="mt-6 border-t border-[#f3efdf]/15 pt-4">
                  <button
                    type="button"
                    onClick={() => setShowAlternatives((prev) => !prev)}
                    className="flex w-full items-center justify-between py-1 text-xs font-bold text-[#d9d4c4] hover:text-white"
                  >
                    <span>
                      Andere mogelijkheden ({alternativeCandidates.length})
                    </span>
                    <span className="font-mono text-[#b6bbaa]">
                      {showAlternatives ? "− Inklappen" : "+ Uitklappen"}
                    </span>
                  </button>

                  {showAlternatives && (
                    <div className="mt-3 space-y-2">
                      {alternativeCandidates.map((alt) => (
                        <div
                          key={alt.id}
                          className="flex items-center justify-between gap-3 rounded-[5px] border border-[#f3efdf]/15 bg-[#171c16] p-2.5 text-xs transition hover:border-[#f1ca53]/60"
                        >
                          <div className="flex min-w-0 items-center gap-3">
                            {alt.image_url ? (
                              <div className="relative h-12 w-9 flex-shrink-0 overflow-hidden rounded-[3px] bg-[#10150f]">
                                <Image
                                  src={alt.image_url}
                                  alt={alt.name}
                                  fill
                                  sizes="36px"
                                  className="object-contain"
                                  unoptimized
                                />
                              </div>
                            ) : null}
                            <div className="min-w-0">
                              <p className="truncate font-bold text-[#f3efdf]">
                                {alt.name}
                              </p>
                              <p className="truncate font-mono text-[10px] text-[#b6bbaa]">
                                {alt.set_name} · #{alt.local_id}
                              </p>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleSelectAlternative(alt)}
                            disabled={isSelectingAlt}
                            className="flex-shrink-0 rounded-[4px] border border-[#f3efdf]/25 bg-[#2a3028] px-2.5 py-1 text-[11px] font-bold text-[#f3efdf] transition hover:border-[#f1ca53] active:scale-95 disabled:opacity-50"
                          >
                            Kies deze kaart
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            /* Fallback when no candidate detected */
            <div className="py-6 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-[5px] border border-[#f1ca53]/50 bg-[#f1ca53]/10 text-[#f1ca53]">
                <svg
                  className="h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <h3 className="text-base font-bold text-[#f3efdf]">
                Geen kaart automatisch herkend
              </h3>
              <p className="mt-1 text-xs text-[#b6bbaa]">
                Zorg voor voldoende licht en houd de kaart recht binnen het
                kader.
              </p>
              <div className="mt-5 flex justify-center gap-3">
                <button
                  type="button"
                  onClick={onRetake}
                  className="rounded-[5px] border border-[#252923] bg-[#c6372e] px-4 py-2 text-xs font-black text-[#fff9ee] shadow-[2px_2px_0_#10150f] transition hover:bg-[#d94b40]"
                >
                  Opnieuw scannen
                </button>
                <Link
                  href={`/scan/${scan.id}`}
                  className="rounded-[5px] border border-[#f3efdf]/25 bg-[#2a3028] px-4 py-2 text-xs font-bold text-[#f3efdf] transition hover:border-[#f1ca53]"
                >
                  Handmatig uitsnijden & zoeken →
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer Secondary actions */}
        <div className="flex items-center justify-between border-t border-[#f3efdf]/15 bg-[#171c16] px-6 py-3 text-xs text-[#b6bbaa]">
          <button
            type="button"
            onClick={onRetake}
            className="transition hover:text-white"
          >
            ← Opnieuw scannen
          </button>
          <Link
            href={`/scan/${scan.id}`}
            className="text-[#f1ca53] transition hover:text-[#ffe178]"
          >
            Handmatig aanpassen →
          </Link>
        </div>
      </div>
    </div>
  );
}
