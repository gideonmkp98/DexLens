"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import CardImage from "@/components/CardImage";
import {
  CardDetail,
  CardEnrichmentResponse,
  getCard,
  getCardDetails,
} from "@/lib/api";

export default function CardDetailPage() {
  const params = useParams();
  const cardIdStr = Array.isArray(params.id) ? params.id[0] : params.id;
  const cardId = parseInt(cardIdStr || "", 10);

  const [card, setCard] = useState<CardDetail | null>(null);
  const [loadingCard, setLoadingCard] = useState(true);
  const [cardError, setCardError] = useState<string | null>(null);

  const [enrichment, setEnrichment] = useState<CardEnrichmentResponse | null>(
    null
  );
  const [loadingDetails, setLoadingDetails] = useState(true);

  // 1. Load local basic card data first
  useEffect(() => {
    if (isNaN(cardId)) {
      setCardError("Invalid card identifier.");
      setLoadingCard(false);
      return;
    }

    let mounted = true;
    setLoadingCard(true);

    getCard(cardId)
      .then((data) => {
        if (mounted) {
          setCard(data);
          setLoadingCard(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setCardError(
            err instanceof Error
              ? err.message
              : "Card not found in local index."
          );
          setLoadingCard(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [cardId]);

  // 2. Independently request additional details once local card is known
  useEffect(() => {
    if (!card || isNaN(cardId)) return;

    let mounted = true;
    setLoadingDetails(true);

    getCardDetails(cardId)
      .then((enrichRes) => {
        if (mounted) {
          setEnrichment(enrichRes);
          setLoadingDetails(false);
        }
      })
      .catch(() => {
        if (mounted) {
          // Graceful degradation: never crash or show tech stack trace
          setEnrichment({
            status: "unavailable",
            source: "tcgdex",
            fetched_at: null,
            details: null,
          });
          setLoadingDetails(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [card, cardId]);

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
          The requested card could not be found in the local index.
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

  const details = enrichment?.details;
  const isStale = enrichment?.status === "stale";
  const isUnavailable =
    !enrichment || enrichment.status === "unavailable" || !details;

  // Extract true variants
  const activeVariants =
    details?.variants && typeof details.variants === "object"
      ? Object.entries(details.variants)
          .filter(([, active]) => active === true)
          .map(([name]) => name)
      : [];

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

        {/* Right: Metadata & On-demand Details */}
        <div className="flex flex-col gap-6 md:col-span-7">
          {/* Basic Local Index Data */}
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

            <div className="mt-4 flex items-center gap-2 border-t border-slate-100 pt-4">
              <span className="text-sm text-slate-500">Set:</span>
              <Link
                href={`/sets/${card.set.id}`}
                className="text-sm font-bold text-red-600 hover:text-red-700"
              >
                {card.set.name} &rarr;
              </Link>
            </div>
          </div>

          {/* Additional Details (Independent Loading & Degradation) */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 className="text-lg font-bold text-slate-900">Card Details</h2>
              {isStale && (
                <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                  Cached data
                </span>
              )}
            </div>

            {loadingDetails ? (
              <div className="py-8 text-center text-slate-500">
                <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
                <p className="mt-2 text-xs">
                  Loading additional card details from TCGdex...
                </p>
              </div>
            ) : isUnavailable ? (
              <div className="py-6 text-center text-slate-500">
                <p className="text-sm font-medium">
                  Additional card details are temporarily unavailable.
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Local index browsing remains fully accessible.
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-6">
                {/* Stats & Attributes Grid */}
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  {details.category && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Category
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {details.category}
                      </span>
                    </div>
                  )}

                  {details.rarity && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Rarity
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {details.rarity}
                      </span>
                    </div>
                  )}

                  {details.hp !== undefined && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        HP
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {details.hp}
                      </span>
                    </div>
                  )}

                  {details.types && details.types.length > 0 && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Types
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {details.types.join(", ")}
                      </span>
                    </div>
                  )}

                  {details.illustrator && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Illustrator
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {details.illustrator}
                      </span>
                    </div>
                  )}

                  {details.regulationMark && (
                    <div className="rounded-lg bg-slate-50 p-3">
                      <span className="block text-[11px] font-semibold uppercase text-slate-400">
                        Regulation
                      </span>
                      <span className="text-sm font-bold text-slate-900">
                        {details.regulationMark}
                      </span>
                    </div>
                  )}
                </div>

                {/* Variants (only if known variants exist) */}
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
                {details.attacks && details.attacks.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Attacks
                    </h3>
                    <div className="mt-3 space-y-3">
                      {details.attacks.map((att, idx) => (
                        <div
                          key={idx}
                          className="rounded-lg border border-slate-100 bg-slate-50 p-3.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-bold text-slate-900">
                              {att.name}
                            </span>
                            {att.damage !== undefined && (
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
                {details.abilities && details.abilities.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Abilities
                    </h3>
                    <div className="mt-3 space-y-3">
                      {details.abilities.map((ab, idx) => (
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
