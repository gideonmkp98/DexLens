"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import CardTile from "@/components/CardTile";
import { CardGridSkeleton } from "@/components/LoadingSkeleton";
import EmptyState from "@/components/EmptyState";
import { getCards, getSet, PaginatedCardsResponse, SetDetail } from "@/lib/api";

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
      <div className="mx-auto flex min-h-[60vh] max-w-7xl flex-col items-center justify-center px-4 py-16 text-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900 dark:border-zinc-800 dark:border-t-white" />
        <p className="mt-4 font-mono text-xs text-zinc-500">
          Loading expansion checklist...
        </p>
      </div>
    );
  }

  if (setErrorMsg || !setInfo) {
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
          Expansion Set Not Found
        </h2>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          The requested set could not be found in the catalog index.
        </p>
        <Link
          href="/sets"
          className="mt-6 inline-block rounded-xl bg-zinc-900 px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-zinc-800 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200"
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
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Breadcrumb */}
      <nav className="mb-6 flex items-center gap-2 font-mono text-xs font-medium text-zinc-500 dark:text-zinc-400">
        <Link
          href="/sets"
          className="hover:text-zinc-900 dark:hover:text-white"
        >
          Expansions
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700">/</span>
        <span className="truncate text-zinc-900 dark:text-white">
          {setInfo.name}
        </span>
      </nav>

      {/* Set Header Hero Banner */}
      <div className="card-slab rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-obsidian-900 sm:p-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
            {setInfo.logo_url && (
              <div className="relative h-16 w-32 shrink-0 rounded-xl border border-zinc-100 bg-zinc-50/60 p-2 dark:border-zinc-800/80 dark:bg-obsidian-950">
                <Image
                  src={`${setInfo.logo_url}.webp`}
                  alt={setInfo.name}
                  fill
                  className="object-contain p-1"
                  onError={(e) => {
                    const target = e.currentTarget as HTMLImageElement;
                    if (target.src.endsWith(".webp") && setInfo.logo_url) {
                      target.src = `${setInfo.logo_url}.png`;
                    }
                  }}
                  unoptimized
                />
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span className="rounded-md border border-zinc-200 bg-zinc-100 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-zinc-700 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-300">
                  {setInfo.series || "Expansion Set"}
                </span>
                <span className="font-mono text-xs text-zinc-400">
                  ID: {setInfo.external_id}
                </span>
              </div>

              <h1 className="mt-2 text-2xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-3xl">
                {setInfo.name}
              </h1>

              {setInfo.release_date && (
                <p className="mt-1 font-mono text-xs text-zinc-500">
                  Released {setInfo.release_date}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 sm:flex-col sm:items-end">
            <div className="rounded-xl border border-zinc-100 bg-zinc-50/80 px-5 py-3 text-left dark:border-zinc-800/60 dark:bg-obsidian-850 sm:text-right">
              <span className="block font-mono text-[10px] uppercase text-zinc-400">
                Indexed Cards
              </span>
              <span className="font-mono text-2xl font-bold text-zinc-900 dark:text-white">
                {setInfo.card_count ?? setInfo.local_card_count ?? 0}
                {setInfo.total ? (
                  <span className="text-xs font-normal text-zinc-400">
                    {" "}
                    / {setInfo.total}
                  </span>
                ) : null}
              </span>
            </div>

            <Link
              href="/scan"
              className="inline-flex items-center gap-2 rounded-xl bg-zinc-900 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-zinc-800 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200"
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
                  d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.75}
                  d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"
                />
              </svg>
              <span>Scan From Set</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Cards in Set Section */}
      <div className="mt-10">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold tracking-tight text-zinc-900 dark:text-white">
              Cards in this Expansion
            </h2>
            <p className="font-mono text-xs text-zinc-500">
              Checklist of indexed specimens released in {setInfo.name}
            </p>
          </div>
        </div>

        {/* Card Grid */}
        <div className="mt-6">
          {loadingCards ? (
            <CardGridSkeleton count={12} />
          ) : cardsData && cardsData.items.length > 0 ? (
            <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              {cardsData.items.map((card) => (
                <CardTile key={card.external_id || card.id} card={card} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No cards in set yet"
              description="Cards from this set have not been imported or indexed yet."
              actionHref="/cards"
              actionLabel="Search All Cards"
            />
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-10 flex items-center justify-center gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
            <button
              type="button"
              disabled={cardPage <= 1 || loadingCards}
              onClick={() => setCardPage(cardPage - 1)}
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-800 dark:bg-obsidian-900 dark:text-zinc-200 dark:hover:bg-obsidian-850"
            >
              &larr; Previous
            </button>

            <span className="font-mono text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Page {cardPage} of {totalPages}
            </span>

            <button
              type="button"
              disabled={cardPage >= totalPages || loadingCards}
              onClick={() => setCardPage(cardPage + 1)}
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-800 dark:bg-obsidian-900 dark:text-zinc-200 dark:hover:bg-obsidian-850"
            >
              Next &rarr;
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
