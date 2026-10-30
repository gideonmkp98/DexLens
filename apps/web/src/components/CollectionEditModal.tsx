"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ApiError,
  CollectionCondition,
  CollectionItem,
  CollectionVariant,
  deleteCollectionItem,
  getCollectionItem,
  updateCollectionItem,
} from "@/lib/api";
import {
  formatConditionBadge,
  formatVariantLabel,
} from "@/components/CollectionCardTile";

interface CollectionEditModalProps {
  item: CollectionItem | null;
  isOpen: boolean;
  onClose: () => void;
  onUpdated: (updatedItem: CollectionItem) => void;
  onDeleted: (deletedId: string) => void;
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

export default function CollectionEditModal({
  item,
  isOpen,
  onClose,
  onUpdated,
  onDeleted,
}: CollectionEditModalProps) {
  // Editable form fields
  const [quantity, setQuantity] = useState<number>(1);
  const [condition, setCondition] = useState<CollectionCondition>("near_mint");
  const [variant, setVariant] = useState<CollectionVariant>("normal");
  const [purchasePrice, setPurchasePrice] = useState<string>("");
  const [currency, setCurrency] = useState<string>("EUR");
  const [acquiredAt, setAcquiredAt] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  // States
  const [saving, setSaving] = useState<boolean>(false);
  const [deleting, setDeleting] = useState<boolean>(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentItem, setCurrentItem] = useState<CollectionItem | null>(item);

  const modalRef = useRef<HTMLDivElement>(null);

  // Sync form when item prop changes
  useEffect(() => {
    if (item) {
      setCurrentItem(item);
      setQuantity(item.quantity);
      setCondition(item.condition);
      setVariant(item.variant);
      setPurchasePrice(
        item.purchase_price !== null ? String(item.purchase_price) : ""
      );
      setCurrency(item.currency || "EUR");
      setAcquiredAt(item.acquired_at || "");
      setNotes(item.notes || "");
      setError(null);
      setShowDeleteConfirm(false);
    }
  }, [item]);

  // Handle escape key and body overflow
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showDeleteConfirm) {
          setShowDeleteConfirm(false);
        } else {
          onClose();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    const origOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = origOverflow;
    };
  }, [isOpen, onClose, showDeleteConfirm]);

  if (!isOpen || !currentItem) return null;

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!currentItem) return;

    setSaving(true);
    setError(null);

    try {
      const priceVal = purchasePrice.trim()
        ? parseFloat(purchasePrice.replace(",", "."))
        : null;

      const updated = await updateCollectionItem(currentItem.id, {
        quantity: Math.max(1, quantity),
        condition,
        variant,
        notes: notes.trim() ? notes.trim() : null,
        purchase_price: priceVal !== null && !isNaN(priceVal) ? priceVal : null,
        currency: purchasePrice.trim() ? currency.toUpperCase() : null,
        acquired_at: acquiredAt || null,
        expected_version: currentItem.version,
      });

      setCurrentItem(updated);
      onUpdated(updated);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setError(
            "Deze kaart is tussentijds gewijzigd door een andere sessie. We hebben de nieuwste gegevens opgehaald."
          );
          // Refresh item from server
          try {
            const fresh = await getCollectionItem(currentItem.id);
            setCurrentItem(fresh);
            setQuantity(fresh.quantity);
            setCondition(fresh.condition);
            setVariant(fresh.variant);
            setPurchasePrice(
              fresh.purchase_price !== null ? String(fresh.purchase_price) : ""
            );
            setCurrency(fresh.currency || "EUR");
            setAcquiredAt(fresh.acquired_at || "");
            setNotes(fresh.notes || "");
          } catch {
            // ignore
          }
        } else {
          setError(err.message);
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Opslaan van wijzigingen is mislukt.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!currentItem) return;
    setDeleting(true);
    setError(null);

    try {
      await deleteCollectionItem(currentItem.id);
      onDeleted(currentItem.id);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Verwijderen van deze kaart is mislukt.");
      }
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const condBadge = formatConditionBadge(condition);
  const variantLabel = formatVariantLabel(variant);
  const hasDuplicates = quantity > 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-edit-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/65 backdrop-blur-sm transition-opacity"
        onClick={() => !showDeleteConfirm && onClose()}
        aria-hidden="true"
      />

      {/* Main Dialog Container */}
      <div
        ref={modalRef}
        className="relative z-10 flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-[var(--surface)] text-[var(--ink)] shadow-2xl dark:border-white/10 dark:bg-vault-900"
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between border-b border-[var(--line)] px-6 py-4 dark:border-white/10">
          <div className="flex items-center gap-2">
            <span
              className="pokeball brand-ball h-5 w-5 border-2 border-[var(--ink)]"
              aria-hidden="true"
            />
            <h2
              id="modal-edit-title"
              className="text-base font-black tracking-tight"
            >
              {currentItem.card_name}
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

        {/* Modal Body: Two-column layout on larger screens */}
        <div className="flex flex-1 flex-col overflow-y-auto p-6 md:flex-row md:gap-6">
          {/* Left Column: Artwork preview & Links */}
          <div className="flex flex-col items-center md:w-52 md:flex-shrink-0">
            <div className="card-tile-art relative aspect-[2.5/3.5] w-full max-w-[200px] overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--paper)] p-2 shadow-md dark:border-white/10">
              {currentItem.card_image_url ? (
                <Image
                  src={currentItem.card_image_url}
                  alt={currentItem.card_name}
                  fill
                  sizes="200px"
                  className="object-contain p-2"
                  unoptimized
                />
              ) : (
                <div className="flex h-full w-full flex-col items-center justify-center p-3 text-center">
                  <span className="font-mono text-xs font-bold text-[var(--muted)]">
                    #{currentItem.collector_number}
                  </span>
                  <span className="mt-1 text-[11px] text-[var(--muted)]">
                    Geen foto
                  </span>
                </div>
              )}
            </div>

            {/* Quick Badges under art */}
            <div className="mt-3 flex flex-wrap justify-center gap-1.5 text-center">
              <span
                className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-black uppercase ${condBadge.colorClass}`}
              >
                {condBadge.label}
              </span>
              {variant !== "normal" && (
                <span className="rounded-md border border-purple-400/40 bg-purple-500/15 px-2 py-0.5 font-mono text-[10px] font-bold text-purple-700 dark:text-purple-300">
                  {variantLabel}
                </span>
              )}
            </div>

            {/* Navigational Links */}
            <div className="mt-4 flex w-full flex-col gap-2 font-mono text-[11px]">
              <Link
                href={`/cards/${encodeURIComponent(currentItem.card_id)}`}
                className="flex items-center justify-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-[var(--ink)] transition hover:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
              >
                <span>Catalogus profiel</span>
                <span aria-hidden="true">&rarr;</span>
              </Link>

              {currentItem.source_scan_id && (
                <Link
                  href={`/scan/${encodeURIComponent(currentItem.source_scan_id)}`}
                  className="flex items-center justify-center gap-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-sky-700 transition hover:bg-sky-500/20 dark:text-sky-300"
                >
                  <svg
                    className="h-3.5 w-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                  <span>Bronscan bekijken</span>
                </Link>
              )}
            </div>

            {/* Snapshot metadata */}
            <div className="mt-4 w-full border-t border-[var(--line)] pt-3 text-[10px] text-[var(--muted)] dark:border-white/10">
              <div className="flex justify-between py-0.5">
                <span>Set:</span>
                <span className="max-w-[120px] truncate font-semibold text-[var(--ink)]">
                  {currentItem.set_name}
                </span>
              </div>
              <div className="flex justify-between py-0.5">
                <span>Nummer:</span>
                <span className="font-mono font-bold text-[var(--ink)]">
                  #{currentItem.collector_number}
                </span>
              </div>
              <div className="flex justify-between py-0.5">
                <span>Taal:</span>
                <span className="font-mono font-bold uppercase text-[var(--ink)]">
                  {currentItem.language}
                </span>
              </div>
              <div className="flex justify-between py-0.5">
                <span>Versie:</span>
                <span className="font-mono text-[var(--ink)]">
                  v{currentItem.version}
                </span>
              </div>
            </div>
          </div>

          {/* Right Column: Editable form */}
          <form onSubmit={handleSave} className="mt-5 flex-1 md:mt-0">
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
              {/* Quantity adjustment with atomic +/- */}
              <div>
                <label
                  htmlFor="edit-quantity"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Aantal in bezit
                </label>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                    className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--paper)] text-base font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] active:scale-95 dark:border-white/15 dark:bg-vault-800"
                    aria-label="Verlaag aantal exemplaren"
                  >
                    −
                  </button>
                  <input
                    id="edit-quantity"
                    type="number"
                    min="1"
                    max="999"
                    value={quantity}
                    onChange={(e) =>
                      setQuantity(
                        Math.max(1, parseInt(e.target.value, 10) || 1)
                      )
                    }
                    className="h-10 w-20 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 text-center font-mono text-sm font-bold text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                  />
                  <button
                    type="button"
                    onClick={() => setQuantity((q) => q + 1)}
                    className="flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--paper)] text-base font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] active:scale-95 dark:border-white/15 dark:bg-vault-800"
                    aria-label="Verhoog aantal exemplaren"
                  >
                    +
                  </button>
                  {hasDuplicates && (
                    <span className="font-mono text-xs font-bold text-amber-600 dark:text-amber-400">
                      ★ {quantity - 1} dubbel{quantity > 2 ? "en" : ""}
                    </span>
                  )}
                </div>
              </div>

              {/* Condition & Variant row */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="edit-condition"
                    className="mb-1 block font-bold text-[var(--ink)]"
                  >
                    Conditie
                  </label>
                  <select
                    id="edit-condition"
                    value={condition}
                    onChange={(e) =>
                      setCondition(e.target.value as CollectionCondition)
                    }
                    className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-sans font-medium text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                  >
                    {CONDITION_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="edit-variant"
                    className="mb-1 block font-bold text-[var(--ink)]"
                  >
                    Drukvariant
                  </label>
                  <select
                    id="edit-variant"
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

              {/* Price & Currency */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="edit-price"
                    className="mb-1 block font-bold text-[var(--ink)]"
                  >
                    Aankoopprijs
                  </label>
                  <input
                    id="edit-price"
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={purchasePrice}
                    onChange={(e) => setPurchasePrice(e.target.value)}
                    className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-mono text-xs text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                  />
                </div>

                <div>
                  <label
                    htmlFor="edit-currency"
                    className="mb-1 block font-bold text-[var(--ink)]"
                  >
                    Valuta
                  </label>
                  <select
                    id="edit-currency"
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
                  htmlFor="edit-acquired"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Verkregen op
                </label>
                <input
                  id="edit-acquired"
                  type="date"
                  value={acquiredAt}
                  onChange={(e) => setAcquiredAt(e.target.value)}
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 font-sans text-xs text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                />
              </div>

              {/* Notes */}
              <div>
                <label
                  htmlFor="edit-notes"
                  className="mb-1 block font-bold text-[var(--ink)]"
                >
                  Notities
                </label>
                <textarea
                  id="edit-notes"
                  rows={2}
                  maxLength={500}
                  placeholder="Bijvoorbeeld: beursvondst, binder 2, mint kandidaat..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 font-sans text-xs text-[var(--ink)] outline-none focus:border-[var(--red)] dark:border-white/15 dark:bg-vault-800"
                />
              </div>
            </div>

            {/* Action Bar */}
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4 dark:border-white/10">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={saving || deleting}
                className="rounded-xl border border-rose-300/60 bg-rose-50 px-3.5 py-2 font-sans text-xs font-bold text-rose-700 transition hover:bg-rose-100 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300 dark:hover:bg-rose-950/70"
              >
                Verwijder uit collectie
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={saving || deleting}
                  className="rounded-xl border border-[var(--line)] bg-[var(--paper)] px-4 py-2 font-sans text-xs font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] dark:border-white/10 dark:bg-vault-800"
                >
                  Sluiten
                </button>
                <button
                  type="submit"
                  disabled={saving || deleting}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--red)] px-5 py-2 font-sans text-xs font-bold text-white shadow-md transition hover:brightness-110 active:scale-95 disabled:opacity-50"
                >
                  {saving ? (
                    <>
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      <span>Opslaan…</span>
                    </>
                  ) : (
                    <span>Wijzigingen opslaan</span>
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Nested Delete Confirmation Dialog */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center p-4"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-confirm-title"
          aria-describedby="delete-confirm-desc"
        >
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-sm"
            onClick={() => setShowDeleteConfirm(false)}
            aria-hidden="true"
          />
          <div className="relative z-10 w-full max-w-sm rounded-2xl border border-rose-300 bg-[var(--surface)] p-6 shadow-2xl dark:border-rose-900/80 dark:bg-vault-950">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-950/80 dark:text-rose-400">
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
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </div>
            <h3
              id="delete-confirm-title"
              className="mt-4 text-center text-sm font-bold text-[var(--ink)]"
            >
              Kaart verwijderen uit collectie?
            </h3>
            <p
              id="delete-confirm-desc"
              className="mt-2 text-center text-xs text-[var(--muted)]"
            >
              Weet je zeker dat je <strong>{currentItem.card_name}</strong> wilt
              verwijderen? Deze actie kan niet ongedaan worden gemaakt.
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
                className="rounded-xl border border-[var(--line)] bg-[var(--paper)] px-4 py-2 text-xs font-bold text-[var(--ink)] transition hover:bg-[var(--surface)] dark:border-white/10 dark:bg-vault-800"
              >
                Annuleren
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-rose-700 active:scale-95 disabled:opacity-50"
              >
                {deleting ? (
                  <>
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    <span>Verwijderen…</span>
                  </>
                ) : (
                  <span>Ja, verwijderen</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
