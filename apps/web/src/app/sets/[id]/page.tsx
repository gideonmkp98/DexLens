"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import CardImage from "@/components/CardImage";
import {
  CardListItem,
  getCards,
  getSet,
  PaginatedCardsResponse,
  SetDetail,
} from "@/lib/api";

export default function SetDetailPage() {
  const params = useParams();
  const setIdStr = Array.isArray(params.id) ? params.id[0] : params.id;

  const [setInfo, setSetInfo] = useState<SetDetail | null>(null);
  const [loadingSet, setLoadingSet] = useState(true);
  const [setErrorMsg, setSetErrorMsg] = useState<string | null>(null);

  const [cardsData, setCardsData] = useState<PaginatedCardsResponse | null>(
    null
  );
  const [cardPage, setCardPage] = useState(1);
  const [loadingCards, setLoadingCards] = useState(true);

  // 1. Fetch set metadata
  useEffect(() => {
    if (!setIdStr) {
      setSetErrorMsg("Invalid set identifier.");
      setLoadingSet(false);
      return;
    }

    let mounted = true;
    setLoadingSet(true);

    getSet(setIdStr)
      .then((data) => {
        if (mounted) {
          setSetInfo(data);
          setLoadingSet(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setSetErrorMsg(err instanceof Error ? err.message : "Set not found.");
          setLoadingSet(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [setIdStr]);

  // 2. Fetch cards in this set
  useEffect(() => {
    if (!setIdStr) return;

    let mounted = true;
    setLoadingCards(true);

    getCards({
      set_id: setIdStr,
      page: cardPage,
      page_size: 24,
    })
      .then((data) => {
        if (mounted) {
          setCardsData(data);
          setLoadingCards(false);
        }
      })
      .catch((err) => {
        console.error("Failed to load cards for set:", err);
        if (mounted) {
          setLoadingCards(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [setIdStr, cardPage]);

  if (loadingSet) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 text-center text-slate-500">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-300 border-t-slate-900" />
        <p className="mt-4 text-sm font-medium">Loading set details...</p>
      </div>
    );
  }

  if (setErrorMsg || !setInfo) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <span className="text-5xl">🚫</span>
        <h2 className="mt-4 text-2xl font-bold text-slate-900">
          Set Not Found
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          The requested set could not be found.
        </p>
        <Link
          href="/sets"
          className="mt-6 inline-block rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          &larr; Back to Sets
        </Link>
      </div>
    );
  }

  const totalPages = cardsData
    ? cardsData.total !== null
      ? Math.max(1, Math.ceil(cardsData.total / cardsData.page_size))
      : cardsData.has_more
        ? cardPage + 1
        : cardPage
    : 1;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <nav className="mb-6">
        <Link
          href="/sets"
          className="text-sm font-semibold text-slate-500 transition hover:text-slate-900"
        >
          &larr; Back to All Sets
        </Link>
      </nav>

      {/* Set Header Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-5">
            {setInfo.logo_url && (
              <div className="relative h-16 w-32 shrink-0">
                <Image
                  src={`${setInfo.logo_url}.webp`}
                  alt={setInfo.name}
                  fill
                  className="object-contain"
                  onError={(e) => {
                    const target = e.currentTarget as HTMLImageElement;
                    if (target.src.endsWith(".webp") && setInfo.logo_url) {
                      target.src = `${setInfo.logo_url}.png`;
                    }
                  }}
                />
              </div>
            )}
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
                {setInfo.name}
              </h1>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                {setInfo.series && (
                  <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                    Series: {setInfo.series}
                  </span>
                )}
                {setInfo.release_date && (
                  <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                    Released: {setInfo.release_date}
                  </span>
                )}
                <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                  ID: {setInfo.external_id}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-col items-start rounded-xl bg-slate-50 p-4 sm:items-end">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Cards in Set
            </span>
            <span className="text-2xl font-black text-slate-900">
              {setInfo.card_count ?? setInfo.local_card_count ?? 0}
              {setInfo.total ? (
                <span className="text-sm font-normal text-slate-400">
                  {" "}
                  / {setInfo.total} total
                </span>
              ) : null}
            </span>
          </div>
        </div>
      </div>

      {/* Cards in Set Section */}
      <div className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-900">
            Cards in this Set
          </h2>
          {cardsData && (
            <span className="text-sm text-slate-500">
              {cardsData.total !== null
                ? `Showing ${cardsData.items.length} of ${cardsData.total} cards`
                : `Showing ${cardsData.items.length} cards`}
            </span>
          )}
        </div>

        {loadingCards ? (
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 12 }).map((_, i) => (
              <div
                key={i}
                className="flex aspect-[2.5/3.5] animate-pulse rounded-lg bg-slate-200"
              />
            ))}
          </div>
        ) : cardsData && cardsData.items.length === 0 ? (
          <div className="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center text-slate-500">
            No cards found for this set.
          </div>
        ) : cardsData ? (
          <>
            <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {cardsData.items.map((card: CardListItem) => (
                <Link
                  key={card.external_id}
                  href={`/cards/${card.external_id}`}
                  className="group flex flex-col rounded-xl border border-slate-200 bg-white p-2.5 transition hover:border-slate-400 hover:shadow-md"
                >
                  <CardImage src={card.small_image_url} alt={card.name} />
                  <div className="mt-2.5 flex flex-col">
                    <span className="text-xs font-semibold text-slate-400">
                      #{card.local_id}
                    </span>
                    <span className="truncate text-sm font-bold text-slate-900 group-hover:text-red-600">
                      {card.name}
                    </span>
                  </div>
                </Link>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
                <button
                  type="button"
                  disabled={cardPage <= 1}
                  onClick={() => setCardPage((p) => p - 1)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  &larr; Previous
                </button>
                <span className="text-sm text-slate-600">
                  Page{" "}
                  <span className="font-semibold text-slate-900">
                    {cardPage}
                  </span>{" "}
                  of{" "}
                  <span className="font-semibold text-slate-900">
                    {totalPages}
                  </span>
                </span>
                <button
                  type="button"
                  disabled={cardPage >= totalPages}
                  onClick={() => setCardPage((p) => p + 1)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  Next &rarr;
                </button>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
