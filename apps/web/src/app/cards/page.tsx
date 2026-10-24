"use client";

import { Suspense, useEffect, useState, useTransition } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import CardImage from "@/components/CardImage";
import {
  CardListItem,
  getCards,
  getSets,
  PaginatedCardsResponse,
  SetSummary,
} from "@/lib/api";

function CardsSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const currentName = searchParams.get("name") || "";
  const currentNumber = searchParams.get("number") || "";
  const currentSetId = searchParams.get("set_id") || "";
  const currentPage = parseInt(searchParams.get("page") || "1", 10) || 1;

  const [nameInput, setNameInput] = useState(currentName);
  const [numberInput, setNumberInput] = useState(currentNumber);
  const [setIdInput, setSetIdInput] = useState(currentSetId);

  const [sets, setSets] = useState<SetSummary[]>([]);
  const [cardData, setCardData] = useState<PaginatedCardsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sync inputs if URL params change externally (e.g. back navigation)
  useEffect(() => {
    setNameInput(currentName);
    setNumberInput(currentNumber);
    setSetIdInput(currentSetId);
  }, [currentName, currentNumber, currentSetId]);

  // Load imported sets for the set filter dropdown
  useEffect(() => {
    let mounted = true;
    getSets({ page_size: 100 })
      .then((res) => {
        if (mounted) setSets(res.items);
      })
      .catch((err) => {
        console.error("Failed to fetch sets dropdown list:", err);
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Fetch cards whenever URL search parameters change
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);

    const parsedSetId = currentSetId ? parseInt(currentSetId, 10) : undefined;

    getCards({
      name: currentName || undefined,
      number: currentNumber || undefined,
      set_id: parsedSetId && !isNaN(parsedSetId) ? parsedSetId : undefined,
      page: currentPage,
      page_size: 24,
    })
      .then((data) => {
        if (mounted) {
          setCardData(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(
            err instanceof Error ? err.message : "Failed to load cards."
          );
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [currentName, currentNumber, currentSetId, currentPage]);

  const updateSearch = (
    newName: string,
    newNumber: string,
    newSetId: string,
    newPage: number = 1
  ) => {
    const params = new URLSearchParams();
    if (newName.trim()) params.set("name", newName.trim());
    if (newNumber.trim()) params.set("number", newNumber.trim());
    if (newSetId) params.set("set_id", newSetId);
    if (newPage > 1) params.set("page", newPage.toString());

    startTransition(() => {
      const qs = params.toString();
      router.push(`${pathname}${qs ? `?${qs}` : ""}`);
    });
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateSearch(nameInput, numberInput, setIdInput, 1);
  };

  const handleReset = () => {
    setNameInput("");
    setNumberInput("");
    setSetIdInput("");
    startTransition(() => {
      router.push(pathname);
    });
  };

  const totalPages = cardData
    ? Math.max(1, Math.ceil(cardData.total / cardData.page_size))
    : 1;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">
            Card Catalog
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Search locally imported Pokémon cards by name, number, and set.
          </p>
        </div>
        <Link
          href="/sets"
          className="inline-flex items-center text-sm font-semibold text-red-600 hover:text-red-700"
        >
          Browse Sets &rarr;
        </Link>
      </div>

      {/* Filter and Search Form */}
      <form
        onSubmit={handleSearchSubmit}
        className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label
              htmlFor="card-name"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
            >
              Card Name
            </label>
            <input
              id="card-name"
              type="text"
              placeholder="e.g. Pikachu, Charizard"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:outline-none"
            />
          </div>

          <div>
            <label
              htmlFor="card-number"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
            >
              Card Number
            </label>
            <input
              id="card-number"
              type="text"
              placeholder="e.g. 58, 001"
              value={numberInput}
              onChange={(e) => setNumberInput(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:outline-none"
            />
          </div>

          <div>
            <label
              htmlFor="set-filter"
              className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
            >
              Set
            </label>
            <select
              id="set-filter"
              value={setIdInput}
              onChange={(e) => setSetIdInput(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            >
              <option value="">All Imported Sets</option>
              {sets.map((s) => (
                <option key={s.id} value={s.id.toString()}>
                  {s.name} ({s.local_card_count} cards)
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={handleReset}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            Reset
          </button>
          <button
            type="submit"
            className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Search
          </button>
        </div>
      </form>

      {/* Results Section */}
      <div className="mt-8">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-slate-600">
            {loading ? (
              "Loading cards..."
            ) : cardData ? (
              <>
                Found{" "}
                <span className="font-bold text-slate-900">
                  {cardData.total}
                </span>{" "}
                card{cardData.total === 1 ? "" : "s"}
              </>
            ) : null}
          </span>
        </div>

        {error ? (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-6 text-center text-red-700">
            <p className="font-semibold">{error}</p>
            <button
              onClick={() =>
                updateSearch(
                  currentName,
                  currentNumber,
                  currentSetId,
                  currentPage
                )
              }
              className="mt-3 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
            >
              Try Again
            </button>
          </div>
        ) : loading ? (
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 12 }).map((_, i) => (
              <div
                key={i}
                className="flex aspect-[2.5/3.5] animate-pulse flex-col rounded-lg bg-slate-200"
              />
            ))}
          </div>
        ) : cardData && cardData.items.length === 0 ? (
          <div className="mt-12 rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
            <span className="text-4xl">🔍</span>
            <h3 className="mt-3 text-lg font-bold text-slate-900">
              No cards found
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Try adjusting your search criteria or clear filters to view all
              imported cards.
            </p>
            <button
              type="button"
              onClick={handleReset}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              Clear Filters
            </button>
          </div>
        ) : cardData ? (
          <>
            <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {cardData.items.map((card: CardListItem) => (
                <Link
                  key={card.id}
                  href={`/cards/${card.id}`}
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
                    <span className="truncate text-xs text-slate-500">
                      {card.set_name || "Unknown Set"}
                    </span>
                  </div>
                </Link>
              ))}
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
                <button
                  type="button"
                  disabled={currentPage <= 1 || isPending}
                  onClick={() =>
                    updateSearch(
                      currentName,
                      currentNumber,
                      currentSetId,
                      currentPage - 1
                    )
                  }
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  &larr; Previous
                </button>
                <span className="text-sm text-slate-600">
                  Page{" "}
                  <span className="font-semibold text-slate-900">
                    {currentPage}
                  </span>{" "}
                  of{" "}
                  <span className="font-semibold text-slate-900">
                    {totalPages}
                  </span>
                </span>
                <button
                  type="button"
                  disabled={currentPage >= totalPages || isPending}
                  onClick={() =>
                    updateSearch(
                      currentName,
                      currentNumber,
                      currentSetId,
                      currentPage + 1
                    )
                  }
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

export default function CardsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-12 text-center text-slate-500">
          Loading catalog...
        </div>
      }
    >
      <CardsSearch />
    </Suspense>
  );
}
