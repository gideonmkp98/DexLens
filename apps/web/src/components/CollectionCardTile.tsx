"use client";

import Image from "next/image";
import {
  CollectionCondition,
  CollectionItem,
  CollectionVariant,
} from "@/lib/api";

interface CollectionCardTileProps {
  item: CollectionItem;
  onClick: (item: CollectionItem) => void;
  priority?: boolean;
}

export function formatConditionBadge(condition: CollectionCondition): {
  code: string;
  label: string;
  colorClass: string;
} {
  switch (condition) {
    case "mint":
      return {
        code: "M",
        label: "Mint",
        colorClass:
          "bg-emerald-500/15 text-emerald-600 border-emerald-500/40 dark:text-emerald-300",
      };
    case "near_mint":
      return {
        code: "NM",
        label: "Near Mint",
        colorClass:
          "bg-teal-500/15 text-teal-600 border-teal-500/40 dark:text-teal-300",
      };
    case "lightly_played":
      return {
        code: "LP",
        label: "Lightly Played",
        colorClass:
          "bg-sky-500/15 text-sky-600 border-sky-500/40 dark:text-sky-300",
      };
    case "moderately_played":
      return {
        code: "MP",
        label: "Moderately Played",
        colorClass:
          "bg-amber-500/15 text-amber-700 border-amber-500/40 dark:text-amber-300",
      };
    case "heavily_played":
      return {
        code: "HP",
        label: "Heavily Played",
        colorClass:
          "bg-orange-500/15 text-orange-700 border-orange-500/40 dark:text-orange-300",
      };
    case "damaged":
      return {
        code: "DMG",
        label: "Damaged",
        colorClass:
          "bg-rose-500/15 text-rose-700 border-rose-500/40 dark:text-rose-300",
      };
    default:
      return {
        code: "??",
        label: condition,
        colorClass:
          "bg-slate-500/15 text-slate-700 border-slate-500/40 dark:text-slate-300",
      };
  }
}

export function formatVariantLabel(variant: CollectionVariant): string {
  switch (variant) {
    case "normal":
      return "Normaal";
    case "holo":
      return "Holo";
    case "reverse_holo":
      return "Rev. Holo";
    case "first_edition":
      return "1st Edition";
    case "promo":
      return "Promo";
    case "masterball":
      return "Master Ball";
    case "pokeball":
      return "Poké Ball";
    default:
      return variant;
  }
}

export default function CollectionCardTile({
  item,
  onClick,
  priority = false,
}: CollectionCardTileProps) {
  const condBadge = formatConditionBadge(item.condition);
  const variantLabel = formatVariantLabel(item.variant);
  const hasDuplicates = item.quantity > 1;

  return (
    <button
      type="button"
      onClick={() => onClick(item)}
      className="card-slab collection-card-tile group relative flex flex-col text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--red)] focus-visible:ring-offset-2"
    >
      {/* Card Artwork container */}
      <div className="card-tile-art relative aspect-[2.5/3.5] w-full overflow-hidden rounded-md bg-[var(--paper)]">
        {item.card_image_url ? (
          <Image
            src={item.card_image_url}
            alt={item.card_name}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
            className="object-contain p-2 transition-transform duration-200 group-hover:scale-105"
            priority={priority}
            unoptimized
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center p-3 text-center">
            <span className="font-mono text-xs font-bold text-[var(--muted)]">
              #{item.collector_number}
            </span>
            <span className="mt-1 text-[11px] text-[var(--muted)]">
              Geen afbeelding
            </span>
          </div>
        )}

        {/* Top Badges (Quantity & Scan Origin) */}
        <div className="absolute left-2 top-2 flex flex-wrap items-center gap-1.5">
          {/* Quantity Badge */}
          <span
            className={`inline-flex items-center rounded-md px-2 py-0.5 font-mono text-xs font-black shadow-sm ${
              hasDuplicates
                ? "border border-amber-500/80 bg-amber-400 text-slate-950 shadow-amber-500/30 dark:bg-amber-500"
                : "border border-black/20 bg-black/75 text-white backdrop-blur-sm dark:border-white/20"
            }`}
            title={
              hasDuplicates
                ? `${item.quantity} exemplaren in collectie (${item.quantity - 1} dubbel)`
                : "1 exemplaar"
            }
          >
            ×{item.quantity}
          </span>

          {/* Scan Origin Pill */}
          {item.source_scan_id && (
            <span
              className="inline-flex items-center gap-1 rounded-md border border-sky-400/50 bg-sky-500/90 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white shadow-sm backdrop-blur-sm"
              title="Toegevoegd via DexLens fotoscan"
            >
              <svg
                className="h-3 w-3"
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
              <span>SCAN</span>
            </span>
          )}
        </div>

        {/* Bottom Badges (Condition & Variant) */}
        <div className="absolute bottom-2 right-2 flex flex-wrap items-center gap-1">
          {item.variant !== "normal" && (
            <span className="rounded-md border border-purple-400/40 bg-purple-500/80 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-white shadow-sm backdrop-blur-sm">
              {variantLabel}
            </span>
          )}
          <span
            className={`rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-black uppercase tracking-wider shadow-sm backdrop-blur-sm ${condBadge.colorClass}`}
            title={`Conditie: ${condBadge.label}`}
          >
            {condBadge.code}
          </span>
        </div>
      </div>

      {/* Card Info */}
      <div className="flex flex-1 flex-col justify-between p-2.5">
        <div>
          <h3 className="truncate font-sans text-sm font-bold text-[var(--ink)] transition-colors group-hover:text-[var(--red)]">
            {item.card_name}
          </h3>
          <div className="card-tile-meta mt-1 flex items-center justify-between font-mono text-[11px] text-[var(--muted)]">
            <span className="truncate" title={item.set_name}>
              {item.set_name}
            </span>
            <span className="flex-shrink-0 font-bold">
              #{item.collector_number}
            </span>
          </div>
        </div>

        {/* Price / Note indicator row */}
        {(item.purchase_price !== null || item.notes) && (
          <div className="mt-2 flex items-center justify-between border-t border-[var(--line)] pt-1.5 text-[10px] text-[var(--muted)] dark:border-white/10">
            {item.purchase_price !== null ? (
              <span className="font-mono font-semibold">
                {item.currency || "EUR"}{" "}
                {Number(item.purchase_price).toFixed(2)}
              </span>
            ) : (
              <span />
            )}
            {item.notes && (
              <span
                className="max-w-[120px] truncate italic"
                title={item.notes}
              >
                &ldquo;{item.notes}&rdquo;
              </span>
            )}
          </div>
        )}
      </div>
    </button>
  );
}
