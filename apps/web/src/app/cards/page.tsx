"use client";

import { Suspense, useEffect, useState, useTransition } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import CardTile from "@/components/CardTile";
import { CardGridSkeleton } from "@/components/LoadingSkeleton";
import EmptyState from "@/components/EmptyState";
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
  const [, startTransition] = useTransition();

  const currentName = searchParams.get("name") || "";
  const currentNumber = searchParams.get("number") || "";
  const currentSetId = searchParams.get("set_id") || "";
  const currentPage = parseInt(searchParams.get("page") || "1", 10) || 1;

  const [nameInput, setNameInput] = useState(currentName);
  const [numberInput, setNumberInput] = useState(currentNumber);
  const [setIdInput, setSetIdInput] = useState(currentSetId);

  const [sets, setSets] = useState<SetSummary[]>([]);
  const [cardData, setCardData] = useState<PaginatedCardsResponse | null>(null);
  const [loading, setLoading] = useState(true); const [retry, setRetry] = useState(0);
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

    getCards({
      name: currentName || undefined,
      number: currentNumber || undefined,
      set_id: currentSetId || undefined,
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
  }, [currentName, currentNumber, currentSetId, currentPage, retry]);

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

  const hasFilters = Boolean(currentName || currentNumber || currentSetId);

  const totalPages =
    cardData && cardData.total !== null
      ? Math.max(1, Math.ceil(cardData.total / cardData.page_size))
      : null;

  return (
    <div className="catalog-page mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-zinc-200 bg-zinc-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-zinc-600 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-400">
              HET KAARTENARCHIEF
            </span>
            <span className="font-mono text-xs text-zinc-400">POKÉMON TCG</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-3xl">
            De kaartencatalogus
          </h1>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400 sm:text-sm">
            Vind je favoriet. Zoek op naam, kaartnummer of uitbreiding.
          </p>
        </div>

        <Link
          href="/scan"
          className="inline-flex items-center gap-2 self-start rounded-xl bg-zinc-900 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-zinc-800 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200 sm:self-auto"
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
          <span>Scan een kaart</span>
        </Link>
      </div>

      {/* Modern Filter & Search Bar */}
      <form
        onSubmit={handleSearchSubmit}
        className="card-slab mt-6 rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-obsidian-900 sm:p-5"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-12">
          {/* Card Name */}
          <div className="relative sm:col-span-5">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-zinc-400">
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <circle cx="11" cy="11" r="8" strokeWidth="2" />
                <path
                  d="m21 21-4.3-4.3"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <input
              id="card-name"
              aria-label="Kaartnaam"
              type="text"
              placeholder="Kaartnaam, bijv. Charizard"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              className="w-full rounded-xl border border-zinc-200 bg-zinc-50/80 py-2.5 pl-10 pr-4 text-xs font-medium text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:bg-white focus:outline-none dark:border-zinc-800 dark:bg-obsidian-850 dark:text-white dark:focus:border-zinc-400 sm:text-sm"
            />
          </div>

          {/* Card Number */}
          <div className="sm:col-span-3">
            <input
              id="card-number"
              aria-label="Kaartnummer"
              type="text"
              placeholder="Kaartnummer, bijv. 025"
              value={numberInput}
              onChange={(e) => setNumberInput(e.target.value)}
              className="w-full rounded-xl border border-zinc-200 bg-zinc-50/80 px-3.5 py-2.5 text-xs font-medium text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:bg-white focus:outline-none dark:border-zinc-800 dark:bg-obsidian-850 dark:text-white dark:focus:border-zinc-400 sm:text-sm"
            />
          </div>

          {/* Set Dropdown */}
          <div className="sm:col-span-4">
            <select
              id="set-filter"
              aria-label="Set"
              value={setIdInput}
              onChange={(e) => setSetIdInput(e.target.value)}
              className="w-full rounded-xl border border-zinc-200 bg-zinc-50/80 px-3.5 py-2.5 text-xs font-medium text-zinc-900 focus:border-zinc-500 focus:bg-white focus:outline-none dark:border-zinc-800 dark:bg-obsidian-850 dark:text-white dark:focus:border-zinc-400 sm:text-sm"
            >
              <option value="">Alle sets</option>
              {sets.map((s) => (
                <option key={s.external_id} value={s.external_id}>
                  {s.name} ({s.card_count || s.total || 0} kaarten)
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Buttons row */}
        <div className="mt-3.5 flex items-center justify-between border-t border-zinc-100 pt-3 dark:border-zinc-800/80">
          <div className="flex items-center gap-2">
            {hasFilters && (
              <button
                type="button"
                onClick={handleReset}
                className="font-mono text-xs font-semibold text-zinc-500 transition hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                Wis filters
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-xl bg-zinc-900 px-5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-zinc-800 dark:bg-white dark:text-obsidian-950 dark:hover:bg-zinc-200"
            >
              <span>Zoek kaarten</span>
            </button>
          </div>
        </div>
      </form>

      {/* Results Header */}
      <div className="mt-8 flex items-center justify-between">
        <span className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
          {loading ? (
            "Kaarten zoeken…"
          ) : !error && cardData ? (
            cardData.total !== null ? (
              <>
                Gevonden:{" "}
                <span className="font-bold text-zinc-900 dark:text-white">
                  {cardData.total}
                </span>{" "}
                kaarten
              </>
            ) : (
              <>
                Op deze pagina:{" "}
                <span className="font-bold text-zinc-900 dark:text-white">
                  {cardData.items.length}
                </span>{" "}
                kaarten
              </>
            )
          ) : null}
        </span>

        {/* Link to sets */}
        <Link
          href="/sets"
          className="font-mono text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          Bekijk alle sets &rarr;
        </Link>
      </div>

      {/* Main Grid / Skeletons / Empty State */}
      <div className="mt-4">
        {loading ? (
          <CardGridSkeleton count={12} />
        ) : error ? (
          <EmptyState
            title="Kaarten laden lukt niet"
            description={error}
            actionLabel="Opnieuw proberen"
            onAction={() => setRetry((n) => n + 1)}
          />
        ) : cardData && cardData.items.length > 0 ? (
          <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 sm:gap-4 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {cardData.items.map((card) => (
              <CardTile key={card.external_id || card.id} card={card} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="Geen kaarten gevonden"
            description="Probeer een andere naam of een ander kaartnummer."
            actionLabel="Wis filters"
            onAction={handleReset}
          />
        )}
      </div>

      {/* Pagination Controls */}
      {cardData &&
        (totalPages !== null ? totalPages > 1 : currentPage > 1 || cardData.has_more) && (
          <div className="mt-10 flex items-center justify-center gap-3 border-t border-slate-200/80 pt-6 dark:border-slate-800/80">
            <button
              type="button"
              disabled={currentPage <= 1 || loading}
              onClick={() =>
                updateSearch(
                  currentName,
                  currentNumber,
                  currentSetId,
                  currentPage - 1
                )
              }
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              &larr; Vorige
            </button>

            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
              Pagina {currentPage} {totalPages ? `van ${totalPages}` : ""}
            </span>

            <button
              type="button"
              disabled={
                (totalPages !== null ? currentPage >= totalPages : !cardData.has_more) || loading
              }
              onClick={() =>
                updateSearch(
                  currentName,
                  currentNumber,
                  currentSetId,
                  currentPage + 1
                )
              }
              className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Volgende &rarr;
            </button>
          </div>
        )}
    </div>
  );
}

export default function CardsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
          <CardGridSkeleton count={12} />
        </div>
      }
    >
      <CardsSearch />
    </Suspense>
  );
}

