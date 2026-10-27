"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import CardImage from "@/components/CardImage";
import { CardDetail, getCard } from "@/lib/api";

export default function CardDetailPage() {
  const params = useParams();
  const cardIdStr = Array.isArray(params.id) ? params.id[0] : params.id;

  const [card, setCard] = useState<CardDetail | null>(null);
  const [loadingCard, setLoadingCard] = useState(true);
  const [cardError, setCardError] = useState<string | null>(null);

  useEffect(() => {
    if (!cardIdStr) {
      setCardError("Invalid card identifier.");
      setLoadingCard(false);
      return;
    }

    let mounted = true;
    setLoadingCard(true);

    getCard(cardIdStr)
      .then((data) => {
        if (mounted) {
          setCard(data);
          setLoadingCard(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setCardError(err instanceof Error ? err.message : "Card not found.");
          setLoadingCard(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [cardIdStr]);

  if (loadingCard) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-5xl flex-col items-center justify-center px-4 py-16 text-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900 dark:border-zinc-800 dark:border-t-white" />
        <p className="mt-4 font-mono text-xs text-zinc-500">
          Loading specimen profile...
        </p>
      </div>
    );
  }

  if (cardError || !card) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-zinc-200 bg-zinc-50 text-zinc-500 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-400">
          <svg
            className="h-6 w-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
        </div>
        <h2 className="mt-4 text-base font-bold text-zinc-900 dark:text-white">
          Card Specimen Not Found
        </h2>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          The requested identifier does not match any card in the indexed
          database.
        </p>
        <Link
          href="/cards"
          className="mt-6 inline-block rounded-xl bg-zinc-900 px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-zinc-800 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200"
        >
          &larr; Back to Catalog
        </Link>
      </div>
    );
  }

  const isStale = card.status === "stale";
  const regulationMark = card.regulation_mark || card.regulationMark;

  const activeVariants =
    card.variants && typeof card.variants === "object"
      ? Object.entries(card.variants)
          .filter(([, active]) => active === true)
          .map(([name]) => name)
      : [];

  const hasDetails =
    Boolean(card.category) ||
    Boolean(card.rarity) ||
    (card.hp !== undefined && card.hp !== null) ||
    (card.types && card.types.length > 0) ||
    Boolean(card.illustrator) ||
    Boolean(regulationMark) ||
    activeVariants.length > 0 ||
    (card.attacks && card.attacks.length > 0) ||
    (card.abilities && card.abilities.length > 0);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Navigation Breadcrumb */}
      <nav className="mb-6 flex items-center gap-2 font-mono text-xs font-medium text-zinc-500 dark:text-zinc-400">
        <Link
          href="/cards"
          className="hover:text-zinc-900 dark:hover:text-white"
        >
          Catalog
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">/</span>
        {card.set ? (
          <Link
            href={`/sets/${card.set.external_id}`}
            className="hover:text-zinc-900 dark:hover:text-white"
          >
            {card.set.name}
          </Link>
        ) : (
          <span>Expansion</span>
        )}
        <span className="text-zinc-300 dark:text-zinc-700">/</span>
        <span className="truncate text-zinc-900 dark:text-white">
          {card.name} #{card.local_id}
        </span>
      </nav>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-12 lg:gap-12">
        {/* Left: Card Artwork in Slab Holder */}
        <div className="md:col-span-5 lg:col-span-5">
          <div className="sticky top-24 flex flex-col items-center">
            <div className="card-slab relative aspect-card w-full max-w-[340px] overflow-hidden rounded-2xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-obsidian-900">
              <CardImage
                src={card.large_image_url || card.small_image_url}
                alt={card.name}
                priority
                className="w-full"
              />
            </div>

            {/* Quick action shortcuts under card */}
            <div className="mt-4 flex w-full max-w-[340px] gap-2">
              <Link
                href="/scan"
                className="flex-1 rounded-xl bg-zinc-900 py-2.5 text-center text-xs font-semibold text-white transition hover:bg-zinc-800 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200"
              >
                Scan This Card
              </Link>
              <button
                type="button"
                onClick={() => {
                  if (typeof navigator !== "undefined" && navigator.clipboard) {
                    navigator.clipboard.writeText(window.location.href);
                    alert("Specimen link copied to clipboard");
                  }
                }}
                className="flex items-center justify-center rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-200 dark:hover:bg-obsidian-800"
                aria-label="Copy link"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.75}
                    d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Right: Card Details & Specimen Sheet */}
        <div className="flex flex-col gap-6 md:col-span-7 lg:col-span-7">
          {/* Card Identity Slab */}
          <div className="card-slab rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-obsidian-900 sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="rounded-md border border-zinc-200 bg-zinc-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-zinc-700 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-300">
                  #{card.local_id}
                </span>
                {card.rarity && (
                  <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-700 dark:text-amber-400">
                    {card.rarity}
                  </span>
                )}
              </div>
              {card.hp !== undefined && card.hp !== null && (
                <span className="font-mono text-sm font-bold text-rose-600 dark:text-rose-400">
                  {card.hp} HP
                </span>
              )}
            </div>

            <h1 className="mt-3 text-2xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-3xl">
              {card.name}
            </h1>

            {card.set && (
              <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-4 dark:border-zinc-800">
                <div className="flex items-center gap-2 font-mono text-xs">
                  <span className="text-zinc-400">Set:</span>
                  <Link
                    href={`/sets/${card.set.external_id}`}
                    className="font-semibold text-zinc-900 hover:underline dark:text-white"
                  >
                    {card.set.name} &rarr;
                  </Link>
                </div>
                <span className="font-mono text-[11px] font-semibold text-zinc-400">
                  {card.language?.toUpperCase() || "EN"}
                </span>
              </div>
            )}
          </div>

          {/* Gameplay & Technical Specifications */}
          <div className="card-slab rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-obsidian-900 sm:p-7">
            <div className="flex items-center justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
              <h2 className="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                Collector Specifications
              </h2>
              {isStale && (
                <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-700 dark:text-amber-400">
                  Cached
                </span>
              )}
            </div>

            {!hasDetails ? (
              <div className="py-6 text-center font-mono text-xs text-zinc-500">
                No extra technical metadata recorded for this specimen.
              </div>
            ) : (
              <div className="mt-5 space-y-6">
                {/* Attributes Grid */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {card.category && (
                    <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-obsidian-850">
                      <span className="block font-mono text-[10px] uppercase text-zinc-400">
                        Category
                      </span>
                      <span className="mt-0.5 block text-xs font-semibold text-zinc-900 dark:text-white">
                        {card.category}
                      </span>
                    </div>
                  )}

                  {card.rarity && (
                    <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-obsidian-850">
                      <span className="block font-mono text-[10px] uppercase text-zinc-400">
                        Rarity
                      </span>
                      <span className="mt-0.5 block text-xs font-semibold text-zinc-900 dark:text-white">
                        {card.rarity}
                      </span>
                    </div>
                  )}

                  {card.types && card.types.length > 0 && (
                    <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-obsidian-850">
                      <span className="block font-mono text-[10px] uppercase text-zinc-400">
                        Type
                      </span>
                      <span className="mt-0.5 block text-xs font-semibold text-zinc-900 dark:text-white">
                        {card.types.join(", ")}
                      </span>
                    </div>
                  )}

                  {card.illustrator && (
                    <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-obsidian-850">
                      <span className="block font-mono text-[10px] uppercase text-zinc-400">
                        Illustrator
                      </span>
                      <span className="mt-0.5 block text-xs font-semibold text-zinc-900 dark:text-white">
                        {card.illustrator}
                      </span>
                    </div>
                  )}

                  {regulationMark && (
                    <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-3 dark:border-zinc-800 dark:bg-obsidian-850">
                      <span className="block font-mono text-[10px] uppercase text-zinc-400">
                        Regulation
                      </span>
                      <span className="mt-0.5 block font-mono text-xs font-semibold text-zinc-900 dark:text-white">
                        {regulationMark}
                      </span>
                    </div>
                  )}
                </div>

                {/* Print Variants */}
                {activeVariants.length > 0 && (
                  <div>
                    <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                      Print Variations
                    </h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {activeVariants.map((v) => (
                        <span
                          key={v}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-1 font-mono text-[11px] font-semibold capitalize text-zinc-700 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-300"
                        >
                          {v.replace(/([A-Z])/g, " $1")}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Attacks */}
                {card.attacks && card.attacks.length > 0 && (
                  <div>
                    <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                      Combat Attacks
                    </h3>
                    <div className="mt-3 space-y-3">
                      {card.attacks.map((att, idx) => (
                        <div
                          key={idx}
                          className="rounded-xl border border-zinc-100 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-obsidian-850"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-zinc-900 dark:text-white">
                              {att.name}
                            </span>
                            {att.damage !== undefined &&
                              att.damage !== null && (
                                <span className="font-mono text-xs font-bold text-rose-600 dark:text-rose-400">
                                  {att.damage}
                                </span>
                              )}
                          </div>
                          {att.effect && (
                            <p className="mt-1.5 text-xs leading-relaxed text-zinc-600 dark:text-zinc-300">
                              {att.effect}
                            </p>
                          )}
                          {att.cost && att.cost.length > 0 && (
                            <div className="mt-2 flex gap-1">
                              {att.cost.map((c, cIdx) => (
                                <span
                                  key={cIdx}
                                  className="dark:border-zinc-750 rounded border border-zinc-200 bg-white px-1.5 py-0.5 font-mono text-[9px] font-semibold text-zinc-600 dark:bg-obsidian-900 dark:text-zinc-300"
                                >
                                  {c}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Abilities */}
                {card.abilities && card.abilities.length > 0 && (
                  <div>
                    <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                      Special Abilities
                    </h3>
                    <div className="mt-3 space-y-3">
                      {card.abilities.map((ab, idx) => (
                        <div
                          key={idx}
                          className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-obsidian-850"
                        >
                          <div className="flex items-center gap-2">
                            <span className="rounded bg-zinc-900 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase text-white dark:bg-white dark:text-obsidian-950">
                              {ab.type || "Ability"}
                            </span>
                            <span className="text-xs font-bold text-zinc-900 dark:text-white">
                              {ab.name}
                            </span>
                          </div>
                          {ab.effect && (
                            <p className="mt-2 text-xs leading-relaxed text-zinc-600 dark:text-zinc-300">
                              {ab.effect}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
