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
      <div className="mx-auto max-w-5xl px-4 py-16 text-center text-slate-500">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-300 border-t-slate-900" />
        <p className="mt-4 text-sm font-medium">Loading card...</p>
      </div>
    );
  }

  if (cardError || !card) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <span className="text-5xl">🚫</span>
        <h2 className="mt-4 text-2xl font-bold text-slate-900">
          Card Not Found
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          The requested card could not be found.
        </p>
        <Link
          href="/cards"
          className="mt-6 inline-block rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          &larr; Back to Card Catalog
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
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <nav className="mb-6">
        <Link
          href="/cards"
          className="text-sm font-semibold text-slate-500 transition hover:text-slate-900"
        >
          &larr; Back to Catalog
        </Link>
      </nav>

      <div className="grid grid-cols-1 gap-10 md:grid-cols-12">
        {/* Left: Card Image */}
        <div className="md:col-span-5">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <CardImage
              src={card.large_image_url || card.small_image_url}
              alt={card.name}
              priority
              className="w-full"
            />
          </div>
        </div>

        {/* Right: Metadata & Attributes */}
        <div className="flex flex-col gap-6 md:col-span-7">
          {/* Card Identity Card */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">
                #{card.local_id}
              </span>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Language: {card.language}
              </span>
            </div>

            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900">
              {card.name}
            </h1>

            {card.set && (
              <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-4">
                <span className="text-sm text-slate-500">Set:</span>
                <Link
                  href={`/sets/${card.set.external_id}`}
                  className="text-sm font-bold text-red-600 hover:text-red-700"
                >
                  {card.set.name} &rarr;
                </Link>
              </div>
            )}
          </div>

          {/* Gameplay Attributes */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 className="text-lg font-bold text-slate-900">Card Details</h2>
              {isStale && (
                <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                  Cached data
                </span>
              )}
            </div>

            {!hasDetails ? (
              <div className="py-6 text-center text-slate-500">
                <p className="text-sm font-medium">
                  No additional gameplay details available for this card.
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-6">
                {/* Stats & Attributes Grid */}
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  {card.category && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Category
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {card.category}
                      </span>
                    </div>
                  )}

                  {card.rarity && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Rarity
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {card.rarity}
                      </span>
                    </div>
                  )}

                  {card.hp !== undefined && card.hp !== null && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        HP
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {card.hp}
                      </span>
                    </div>
                  )}

                  {card.types && card.types.length > 0 && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Types
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {card.types.join(", ")}
                      </span>
                    </div>
                  )}

                  {card.illustrator && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Illustrator
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {card.illustrator}
                      </span>
                    </div>
                  )}

                  {regulationMark && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Regulation
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {regulationMark}
                      </span>
                    </div>
                  )}
                </div>

                {/* Variants */}
                {activeVariants.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Known Variants
                    </h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {activeVariants.map((v) => (
                        <span
                          key={v}
                          className="rounded-md border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize text-slate-700"
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
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Attacks
                    </h3>
                    <div className="mt-3 space-y-3">
                      {card.attacks.map((att, idx) => (
                        <div
                          key={idx}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-3.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-bold text-slate-900">
                              {att.name}
                            </span>
                            {att.damage !== undefined &&
                              att.damage !== null && (
                                <span className="text-sm font-extrabold text-red-600">
                                  {att.damage}
                                </span>
                              )}
                          </div>
                          {att.effect && (
                            <p className="mt-1.5 text-xs text-slate-600">
                              {att.effect}
                            </p>
                          )}
                          {att.cost && att.cost.length > 0 && (
                            <div className="mt-2 flex gap-1">
                              {att.cost.map((c, cIdx) => (
                                <span
                                  key={cIdx}
                                  className="shadow-xs rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-500"
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
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Abilities
                    </h3>
                    <div className="mt-3 space-y-3">
                      {card.abilities.map((ab, idx) => (
                        <div
                          key={idx}
                          className="rounded-lg border border-red-100 bg-red-50/50 p-3.5"
                        >
                          <div className="flex items-center gap-2">
                            <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">
                              {ab.type || "Ability"}
                            </span>
                            <span className="text-sm font-bold text-slate-900">
                              {ab.name}
                            </span>
                          </div>
                          {ab.effect && (
                            <p className="mt-1.5 text-xs text-slate-600">
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
