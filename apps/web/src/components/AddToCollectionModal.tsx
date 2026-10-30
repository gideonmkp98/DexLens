"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  ApiError,
  CardDetail,
  CollectionCondition,
  CollectionItem,
  CollectionVariant,
  createCollectionItem,
} from "@/lib/api";

interface AddToCollectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  card: CardDetail;
  onSuccess?: (item: CollectionItem) => void;
}

const CONDITION_OPTIONS: {
  value: CollectionCondition;
  label: string;
  sub: string;
}[] = [
  {
    value: "near_mint",
    label: "Near Mint (NM)",
    sub: "Minimale tot geen slijtage",
  },
  { value: "mint", label: "Mint (M)", sub: "Kaarsrecht, fabrieksnieuw" },
  {
    value: "lightly_played",
    label: "Lightly Played (LP)",
    sub: "Lichte randsporen",
  },
  {
    value: "moderately_played",
    label: "Moderately Played (MP)",
    sub: "Zichtbare wrijving of whitening",
  },
  {
    value: "heavily_played",
    label: "Heavily Played (HP)",
    sub: "Forse slijtage of krassen",
  },
  {
    value: "damaged",
    label: "Damaged (DMG)",
    sub: "Kreukels, deuken of scheurtjes",
  },
];

const VARIANT_OPTIONS: { value: CollectionVariant; label: string }[] = [
  { value: "normal", label: "Normaal (Regular)" },
  { value: "holo", label: "Holo / Foil" },
  { value: "reverse_holo", label: "Reverse Holo" },
  { value: "first_edition", label: "1st Edition" },
  { value: "promo", label: "Promo" },
  { value: "masterball", label: "Master Ball Foil" },
  { value: "pokeball", label: "Poké Ball Foil" },
];

export default function AddToCollectionModal({
  isOpen,
  onClose,
  card,
  onSuccess,
}: AddToCollectionModalProps) {
  const [variant, setVariant] = useState<CollectionVariant>("normal");
  const [condition, setCondition] = useState<CollectionCondition>("near_mint");
  const [quantity, setQuantity] = useState<number>(1);
  const [purchasePrice, setPurchasePrice] = useState<string>("");
  const [currency, setCurrency] = useState<string>("EUR");
  const [acquiredAt, setAcquiredAt] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLSelectElement>(null);

  // Close on Escape & focus trap management
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    // Prevent background scroll
    const origOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Focus initial field
    setTimeout(() => {
      firstInputRef.current?.focus();
    }, 50);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = origOverflow;
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const priceVal = purchasePrice.trim()
        ? parseFloat(purchasePrice.replace(",", "."))
        : null;

      const item = await createCollectionItem({
        card_id: card.external_id || card.id?.toString() || "",
        provider: card.source || "tcgdex",
        card_name: card.name,
        set_id: card.set?.external_id || card.set_id || null,
        set_name: card.set?.name || null,
        collector_number: card.local_id,
        card_image_url: card.large_image_url || card.small_image_url || null,
        quantity: Math.max(1, quantity),
        language: card.language || "en",
        variant,
        condition,
        notes: notes.trim() || null,
        purchase_price: priceVal !== null && !isNaN(priceVal) ? priceVal : null,
        currency: purchasePrice.trim() ? currency.toUpperCase() : null,
        acquired_at: acquiredAt || null,
      });

      if (onSuccess) {
        onSuccess(item);
      }
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Toevoegen aan collectie is mislukt. Controleer je invoer.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const imageUrl = card.large_image_url || card.small_image_url;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-add-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog Card */}
      <div
        ref={modalRef}
        className="relative z-10 flex max-h-[92vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-[var(--surface)] text-[var(--ink)] shadow-2xl dark:border-white/10 dark:bg-vault-900"
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-[var(--line)] px-6 py-4 dark:border-white/10">
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-[var(--muted)]">
              PERSOONLIJKE COLLECTIE
            </p>
            <h2
              id="modal-add-title"
              className="text-lg font-black tracking-tight"
            >
              Voeg kaart toe aan collectie
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Sluit dialoogvenster"
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--line)] text-[var(--muted)] transition hover:bg-[var(--paper)] hover:text-[var(--ink)] dark:border-white/10"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Modal Form Body (Scrollable) */}
        <form
          onSubmit={handleSubmit}
          className="flex flex-1 flex-col overflow-y-auto p-6"
        >
          {/* Card Snapshot Summary */}
          <div className="mb-5 flex items-center gap-4 rounded-xl border border-[var(--line)] bg-[var(--paper)] p-3 dark:border-white/10">
            {imageUrl ? (
              <div className="relative h-16 w-12 flex-shrink-0 overflow-hidden rounded border border-black/10 shadow-sm">
                <Image
                  src={imageUrl}
                  alt={card.name}
                  fill
                  sizes="48px"
                  className="object-contain"
                  unoptimized
                />
              </div>
            ) : (
              <div className="flex h-16 w-12 flex-shrink-0 items-center justify-center rounded border border-[var(--line)] bg-[var(--surface)] font-mono text-[10px] text-[var(--muted)]">
                N/A
              </div>
            )}
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-bold text-[var(--ink)]">
                {card.name}
              </h3>
              <p className="truncate font-mono text-xs text-[var(--muted)]">
                {card.set?.name || "Onbekende set"} · #{card.local_id}
              </p>
              <span className="mt-1 inline-block rounded border border-[var(--line)] bg-[var(--surface)] px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-[var(--muted)] dark:border-white/10">
                {card.language?.toUpperCase() || "EN"}
              </span>
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="mb-4 flex items-start gap-2.5 rounded-xl border border-rose-300 bg-rose-50 p-3 text-xs font-medium text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200"
            >
              <svg
                className="mt-0.5 h-4 w-4 flex-shrink-0 text-rose-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <circle cx="12" cy="12" r="10" strokeWidth={2} />
                <path
                  strokeLinecap="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01"
                />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-4 text-xs">
            {/* Condition & Variant row */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="card-condition"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Conditie <span className="text-[var(--red)]">*</span>
                </label>
                <select
                  ref={firstInputRef}
                  id="card-condition"
                  value={condition}
                  onChange={(e) =>
                    setCondition(e.target.value as CollectionCondition)
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-sans font-medium text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                >
                  {CONDITION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label} — {opt.sub}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor="card-variant"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Drukvariant <span className="text-[var(--red)]">*</span>
                </label>
                <select
                  id="card-variant"
                  value={variant}
                  onChange={(e) =>
                    setVariant(e.target.value as CollectionVariant)
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-sans font-medium text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                >
                  {VARIANT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Quantity */}
            <div>
              <label
                htmlFor="card-quantity"
                className="mb-1 block font-bold text-[var(--ink)]"
              >
                Aantal exemplaren <span className="text-[var(--red)]">*</span>
              </label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                  className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--paper)] text-base font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] dark:border-white/15 dark:bg-vault-800"
                  aria-label="Verlaag aantal"
                >
                  −
                </button>
                <input
                  id="card-quantity"
                  type="number"
                  min="1"
                  max="999"
                  value={quantity}
                  onChange={(e) =>
                    setQuantity(Math.max(1, parseInt(e.target.value, 10) || 1))
                  }
                  className="h-10 w-20 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 text-center font-mono text-sm font-bold text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                />
                <button
                  type="button"
                  onClick={() => setQuantity((q) => q + 1)}
                  className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--paper)] text-base font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] dark:border-white/15 dark:bg-vault-800"
                  aria-label="Verhoog aantal"
                >
                  +
                </button>
                {quantity > 1 && (
                  <span className="font-mono text-xs font-semibold text-amber-600 dark:text-amber-400">
                    ({quantity - 1} dubbel{quantity > 2 ? "en" : ""})
                  </span>
                )}
              </div>
            </div>

            {/* Price & Currency */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="card-price"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Aankoopprijs (optioneel)
                </label>
                <div className="relative">
                  <input
                    id="card-price"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={purchasePrice}
                    onChange={(e) => setPurchasePrice(e.target.value)}
                    className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-mono text-xs text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="card-currency"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Valuta
                </label>
                <select
                  id="card-currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-sans font-medium text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                >
                  <option value="EUR">EUR (€)</option>
                  <option value="USD">USD ($)</option>
                  <option value="GBP">GBP (£)</option>
                  <option value="JPY">JPY (¥)</option>
                </select>
              </div>
            </div>

            {/* Acquisition Date */}
            <div>
              <label
                htmlFor="card-acquired"
                className="mb-1 block font-bold text-[var(--ink)]"
              >
                Verkregen op (optioneel)
              </label>
              <input
                id="card-acquired"
                type="date"
                value={acquiredAt}
                onChange={(e) => setAcquiredAt(e.target.value)}
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-sans text-xs text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
              />
            </div>

            {/* Collector Notes */}
            <div>
              <label
                htmlFor="card-notes"
                className="mb-1 block font-bold text-[var(--ink)]"
              >
                Notities (optioneel)
              </label>
              <textarea
                id="card-notes"
                rows={2}
                maxLength={500}
                placeholder="Bijvoorbeeld: gekocht op beurs, map 1, grading kandidaat..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 font-sans text-xs text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
              />
            </div>
          </div>

          {/* Modal Actions Footer */}
          <div className="mt-6 flex flex-col-reverse justify-end gap-3 border-t border-[var(--line)] pt-4 dark:border-white/10 sm:flex-row">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-xl border border-[var(--line)] bg-[var(--paper)] px-4 py-2.5 font-sans text-xs font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] disabled:opacity-50 dark:border-white/10 dark:bg-vault-800"
            >
              Annuleren
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--red)] px-5 py-2.5 font-sans text-xs font-bold text-white shadow-md transition hover:brightness-110 active:scale-95 disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  <span>Opslaan…</span>
                </>
              ) : (
                <>
                  <span>Voeg toe aan collectie</span>
                  <span aria-hidden="true">✓</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
