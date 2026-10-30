"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useState,
  useTransition,
} from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import CollectionCardTile, {
  formatConditionBadge,
  formatVariantLabel,
} from "@/components/CollectionCardTile";
import CollectionEditModal from "@/components/CollectionEditModal";
import CollectionStatsBar from "@/components/CollectionStatsBar";
import EmptyState from "@/components/EmptyState";
import { CardGridSkeleton } from "@/components/LoadingSkeleton";
import {
  CollectionCondition,
  CollectionItem,
  CollectionListResponse,
  CollectionStats,
  CollectionVariant,
  getCollection,
  getCollectionStats,
} from "@/lib/api";

const CONDITION_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Alle condities" },
  { value: "mint", label: "Mint (M)" },
  { value: "near_mint", label: "Near Mint (NM)" },
  { value: "lightly_played", label: "Lightly Played (LP)" },
  { value: "moderately_played", label: "Moderately Played (MP)" },
  { value: "heavily_played", label: "Heavily Played (HP)" },
  { value: "damaged", label: "Damaged (DMG)" },
];

const VARIANT_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Alle varianten" },
  { value: "normal", label: "Normaal" },
  { value: "holo", label: "Holo / Foil" },
  { value: "reverse_holo", label: "Reverse Holo" },
  { value: "first_edition", label: "1st Edition" },
  { value: "promo", label: "Promo" },
  { value: "masterball", label: "Master Ball Foil" },
  { value: "pokeball", label: "Poké Ball Foil" },
];

const LANGUAGE_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Alle talen" },
  { value: "en", label: "Engels (EN)" },
  { value: "nl", label: "Nederlands (NL)" },
  { value: "ja", label: "Japans (JA)" },
  { value: "de", label: "Duits (DE)" },
  { value: "fr", label: "Frans (FR)" },
];

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "recent", label: "Nieuwste toevoegingen" },
  { value: "name_asc", label: "Kaartnaam (A – Z)" },
  { value: "name_desc", label: "Kaartnaam (Z – A)" },
  { value: "set_asc", label: "Setnaam (A – Z)" },
  { value: "number_asc", label: "Kaartnummer (oplopend)" },
  { value: "quantity_desc", label: "Meeste exemplaren (dubbelen)" },
];

function CollectionBrowser() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

  // URL query params
  const currentQuery = searchParams.get("q") || "";
  const currentSetId = searchParams.get("set_id") || "";
  const currentCondition = searchParams.get("condition") || "";
  const currentLanguage = searchParams.get("language") || "";
  const currentVariant = searchParams.get("variant") || "";
  const currentSort = searchParams.get("sort") || "recent";
  const currentPage = parseInt(searchParams.get("page") || "1", 10) || 1;

  // Local inputs
  const [searchInput, setSearchInput] = useState<string>(currentQuery);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // Data states
  const [collectionData, setCollectionData] =
    useState<CollectionListResponse | null>(null);
  const [stats, setStats] = useState<CollectionStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [statsLoading, setStatsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState<number>(0);

  // Edit modal state
  const [selectedItem, setSelectedItem] = useState<CollectionItem | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);

  // Synchronize search input if URL changes externally
  useEffect(() => {
    setSearchInput(currentQuery);
  }, [currentQuery]);

  // Load stats once on mount or when refreshed
  const loadStats = useCallback(() => {
    setStatsLoading(true);
    getCollectionStats()
      .then((data) => {
        setStats(data);
      })
      .catch((err) => {
        console.error("Fout bij laden van collectiestatistieken:", err);
      })
      .finally(() => {
        setStatsLoading(false);
      });
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats, retryCount]);

  // Fetch paginated & filtered items
  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await getCollection({
        q: currentQuery || undefined,
        set_id: currentSetId || undefined,
        condition: currentCondition || undefined,
        language: currentLanguage || undefined,
        variant: currentVariant || undefined,
        sort: currentSort,
        page: currentPage,
        page_size: 24,
      });
      setCollectionData(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(
          "Kan de collectie niet laden. Controleer de verbinding en probeer het opnieuw."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [
    currentQuery,
    currentSetId,
    currentCondition,
    currentLanguage,
    currentVariant,
    currentSort,
    currentPage,
  ]);

  useEffect(() => {
    void fetchItems();
  }, [fetchItems, retryCount]);

  // URL Query Updater helper
  const updateParams = (newParams: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams.toString());

    Object.entries(newParams).forEach(([key, value]) => {
      if (value === null || value === "") {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    });

    startTransition(() => {
      const qs = params.toString();
      router.push(`${pathname}${qs ? `?${qs}` : ""}`);
    });
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateParams({ q: searchInput.trim(), page: "1" });
  };

  const handleResetFilters = () => {
    setSearchInput("");
    startTransition(() => {
      router.push(pathname);
    });
  };

  const hasActiveFilters = Boolean(
    currentQuery ||
    currentSetId ||
    currentCondition ||
    currentLanguage ||
    currentVariant ||
    currentSort !== "recent"
  );

  const isCollectionEmpty =
    !hasActiveFilters && stats !== null && stats.total_cards === 0;

  const totalPages = collectionData
    ? Math.max(1, Math.ceil(collectionData.total / collectionData.page_size))
    : 1;

  // Card click handler opens edit modal
  const handleCardClick = (item: CollectionItem) => {
    setSelectedItem(item);
    setIsEditModalOpen(true);
  };

  // Item updated in modal
  const handleItemUpdated = (updated: CollectionItem) => {
    if (!collectionData) return;
    setCollectionData({
      ...collectionData,
      items: collectionData.items.map((it) =>
        it.id === updated.id ? updated : it
      ),
    });
    loadStats();
  };

  // Item deleted in modal
  const handleItemDeleted = (deletedId: string) => {
    if (!collectionData) return;
    setCollectionData({
      ...collectionData,
      total: Math.max(0, collectionData.total - 1),
      items: collectionData.items.filter((it) => it.id !== deletedId),
    });
    loadStats();
  };

  // Dynamic set options from stats
  const setOptions = stats?.set_distribution || [];

  return (
    <main className="content-page collection-page">
      {/* Top Heading & Actions */}
      <div className="page-heading flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="eyebrow">
            <span className="red-square" /> PERSOONLIJKE VERZAMELING / DEXLENS
          </p>
          <h1>Mijn Collectie</h1>
          <p className="page-intro">
            Beheer al je fysieke Pokémon kaarten, condities, drukvarianten en
            dubbelen.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Link href="/scan" className="ink-button red small">
            Scan een kaart <span aria-hidden="true">↗</span>
          </Link>
          <Link href="/cards" className="ink-button secondary small">
            Catalogus <span aria-hidden="true">&rarr;</span>
          </Link>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="mb-8 mt-2">
        <CollectionStatsBar stats={stats} loading={statsLoading} />
      </div>

      {/* If completely empty collection (no filters active and 0 cards in stats) */}
      {isCollectionEmpty && !loading ? (
        <div className="card-slab my-8 rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-8 text-center dark:border-white/10 sm:p-12">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border-2 border-[var(--ink)] bg-[var(--yellow)] shadow-[3px_3px_0_var(--shadow)]">
            <span className="pokeball brand-ball h-9 w-9" aria-hidden="true" />
          </div>
          <h2 className="mt-6 text-2xl font-black tracking-tight text-[var(--ink)] sm:text-3xl">
            Je collectie is nog leeg
          </h2>
          <p className="mx-auto mt-2 max-w-md font-sans text-sm text-[var(--muted)]">
            Begin met verzamelen! Maak een foto van een echte Pokémon kaart met
            de scanner, of blader door de catalogus en voeg kaarten handmatig
            toe.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-4">
            <Link href="/scan" className="ink-button red">
              Scan je eerste kaart <span aria-hidden="true">↗</span>
            </Link>
            <Link href="/cards" className="ink-button secondary">
              Blader door de catalogus &rarr;
            </Link>
          </div>
        </div>
      ) : (
        <>
          {/* Collection Filter & Toolbar */}
          <div className="card-slab mb-6 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 shadow-sm dark:border-white/10 sm:p-5">
            {/* Search Input and View Mode */}
            <form
              onSubmit={handleSearchSubmit}
              className="flex flex-col gap-3 sm:flex-row sm:items-center"
            >
              <div className="relative flex-1">
                <input
                  type="text"
                  placeholder="Zoek op kaartnaam, setnaam of nummer (bv. Charizard, Base Set, 4/102)..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] py-2.5 pl-10 pr-4 font-sans text-xs text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
                />
                <svg
                  className="absolute left-3.5 top-3 h-4 w-4 text-[var(--muted)]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <circle cx="11" cy="11" r="8" strokeWidth={2} />
                  <path
                    strokeLinecap="round"
                    strokeWidth={2}
                    d="m21 21-4.3-4.3"
                  />
                </svg>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="submit"
                  className="rounded-xl bg-[var(--red)] px-4 py-2.5 font-sans text-xs font-bold text-white shadow-sm transition hover:brightness-110 active:scale-95"
                >
                  Zoeken
                </button>

                {/* Grid / List View Toggle */}
                <div
                  className="flex items-center rounded-xl border border-[var(--line)] bg-[var(--paper)] p-1 dark:border-white/10 dark:bg-vault-800"
                  role="group"
                  aria-label="Weergavemodus"
                >
                  <button
                    type="button"
                    onClick={() => setViewMode("grid")}
                    className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
                      viewMode === "grid"
                        ? "bg-[var(--surface)] text-[var(--red)] shadow-sm dark:bg-vault-700"
                        : "text-[var(--muted)] hover:text-[var(--ink)]"
                    }`}
                    aria-label="Rasterweergave"
                    title="Rasterweergave"
                  >
                    <svg
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode("list")}
                    className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
                      viewMode === "list"
                        ? "bg-[var(--surface)] text-[var(--red)] shadow-sm dark:bg-vault-700"
                        : "text-[var(--muted)] hover:text-[var(--ink)]"
                    }`}
                    aria-label="Lijstweergave"
                    title="Lijstweergave"
                  >
                    <svg
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 6h16M4 12h16M4 18h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            </form>

            {/* Filter Dropdowns Row */}
            <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-5">
              {/* Set Filter */}
              <div>
                <select
                  value={currentSetId}
                  onChange={(e) =>
                    updateParams({ set_id: e.target.value, page: "1" })
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] px-2.5 py-2 font-sans text-xs text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
                  aria-label="Filter op set"
                >
                  <option value="">Alle sets ({setOptions.length})</option>
                  {setOptions.map((set) => (
                    <option key={set.set_id} value={set.set_id}>
                      {set.set_name} ({set.count})
                    </option>
                  ))}
                </select>
              </div>

              {/* Condition Filter */}
              <div>
                <select
                  value={currentCondition}
                  onChange={(e) =>
                    updateParams({ condition: e.target.value, page: "1" })
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] px-2.5 py-2 font-sans text-xs text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
                  aria-label="Filter op conditie"
                >
                  {CONDITION_FILTER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Variant Filter */}
              <div>
                <select
                  value={currentVariant}
                  onChange={(e) =>
                    updateParams({ variant: e.target.value, page: "1" })
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] px-2.5 py-2 font-sans text-xs text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
                  aria-label="Filter op variant"
                >
                  {VARIANT_FILTER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Language Filter */}
              <div>
                <select
                  value={currentLanguage}
                  onChange={(e) =>
                    updateParams({ language: e.target.value, page: "1" })
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] px-2.5 py-2 font-sans text-xs text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
                  aria-label="Filter op taal"
                >
                  {LANGUAGE_FILTER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Sort Order */}
              <div>
                <select
                  value={currentSort}
                  onChange={(e) =>
                    updateParams({ sort: e.target.value, page: "1" })
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-[var(--paper)] px-2.5 py-2 font-sans text-xs font-semibold text-[var(--ink)] outline-none transition focus:border-[var(--red)] dark:border-white/10 dark:bg-vault-800"
                  aria-label="Sorteer collectie"
                >
                  {SORT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Results status line and Clear Filter button */}
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--line)] pt-3 text-xs text-[var(--muted)] dark:border-white/10">
              <span className="font-mono">
                {collectionData
                  ? `${collectionData.total} kaart${collectionData.total === 1 ? "" : "en"} in selectie`
                  : "Kaarten laden…"}
              </span>

              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={handleResetFilters}
                  className="inline-flex items-center gap-1 font-bold text-[var(--red)] hover:underline"
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
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                  <span>Wis alle filters</span>
                </button>
              )}
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div
              role="alert"
              className="mb-6 flex items-center justify-between gap-3 rounded-2xl border border-rose-300 bg-rose-50 p-4 text-xs font-medium text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200"
            >
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setRetryCount((c) => c + 1)}
                className="rounded-lg bg-rose-600 px-3 py-1 font-bold text-white transition hover:bg-rose-700"
              >
                Opnieuw proberen
              </button>
            </div>
          )}

          {/* Loading Skeleton */}
          {loading ? (
            <div className="py-8">
              <CardGridSkeleton count={12} />
            </div>
          ) : collectionData && collectionData.items.length === 0 ? (
            /* Empty Filter Results State */
            <EmptyState
              title="Geen kaarten gevonden"
              description="Er zijn geen kaarten in je collectie die voldoen aan de huidige filters of zoekterm."
              actionLabel="Wis filters"
              onAction={handleResetFilters}
            />
          ) : collectionData && collectionData.items.length > 0 ? (
            /* Items List or Grid */
            viewMode === "grid" ? (
              <div className="card-grid">
                {collectionData.items.map((item, idx) => (
                  <CollectionCardTile
                    key={item.id}
                    item={item}
                    onClick={handleCardClick}
                    priority={idx < 6}
                  />
                ))}
              </div>
            ) : (
              /* List / Tabular View */
              <div className="overflow-x-auto rounded-2xl border border-[var(--line)] bg-[var(--surface)] shadow-sm dark:border-white/10">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-[var(--line)] bg-[var(--paper)] font-mono text-[10px] font-bold uppercase tracking-wider text-[var(--muted)] dark:border-white/10">
                    <tr>
                      <th className="py-3 pl-4 pr-2">Kaart</th>
                      <th className="px-3 py-3">Set</th>
                      <th className="px-3 py-3">Conditie</th>
                      <th className="px-3 py-3">Variant</th>
                      <th className="px-3 py-3 text-center">Aantal</th>
                      <th className="px-3 py-3">Prijs</th>
                      <th className="px-3 py-3 pr-4 text-right">Actie</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--line)] font-sans dark:divide-white/10">
                    {collectionData.items.map((item) => {
                      const condBadge = formatConditionBadge(item.condition);
                      const variantLabel = formatVariantLabel(item.variant);
                      const hasDuplicates = item.quantity > 1;

                      return (
                        <tr
                          key={item.id}
                          className="hover:bg-[var(--paper)]/60 cursor-pointer transition"
                          onClick={() => handleCardClick(item)}
                        >
                          {/* Card Thumbnail & Name */}
                          <td className="py-3 pl-4 pr-2">
                            <div className="flex items-center gap-3">
                              {item.card_image_url ? (
                                <div className="relative h-12 w-9 flex-shrink-0 overflow-hidden rounded border border-black/10">
                                  <Image
                                    src={item.card_image_url}
                                    alt={item.card_name}
                                    fill
                                    sizes="36px"
                                    className="object-contain"
                                    unoptimized
                                  />
                                </div>
                              ) : (
                                <div className="flex h-12 w-9 flex-shrink-0 items-center justify-center rounded border border-[var(--line)] bg-[var(--paper)] font-mono text-[9px] text-[var(--muted)]">
                                  #{item.collector_number}
                                </div>
                              )}
                              <div>
                                <span className="block font-bold text-[var(--ink)]">
                                  {item.card_name}
                                </span>
                                <span className="font-mono text-[11px] text-[var(--muted)]">
                                  #{item.collector_number}
                                </span>
                              </div>
                            </div>
                          </td>

                          {/* Set */}
                          <td className="px-3 py-3">
                            <span className="font-medium text-[var(--ink)]">
                              {item.set_name}
                            </span>
                          </td>

                          {/* Condition */}
                          <td className="px-3 py-3">
                            <span
                              className={`inline-block rounded-md border px-2 py-0.5 font-mono text-[10px] font-black uppercase ${condBadge.colorClass}`}
                            >
                              {condBadge.label}
                            </span>
                          </td>

                          {/* Variant */}
                          <td className="px-3 py-3">
                            <span className="font-mono text-xs text-[var(--muted)]">
                              {variantLabel}
                            </span>
                          </td>

                          {/* Quantity */}
                          <td className="px-3 py-3 text-center">
                            <span
                              className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-black ${
                                hasDuplicates
                                  ? "bg-amber-400 text-slate-950 dark:bg-amber-500"
                                  : "bg-[var(--paper)] text-[var(--ink)]"
                              }`}
                            >
                              ×{item.quantity}
                            </span>
                          </td>

                          {/* Price */}
                          <td className="px-3 py-3">
                            <span className="font-mono text-xs text-[var(--muted)]">
                              {item.purchase_price !== null
                                ? `${item.currency || "EUR"} ${Number(item.purchase_price).toFixed(2)}`
                                : "—"}
                            </span>
                          </td>

                          {/* Action */}
                          <td className="px-3 py-3 pr-4 text-right">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCardClick(item);
                              }}
                              className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--ink)] transition hover:border-[var(--red)] hover:text-[var(--red)] dark:border-white/10"
                            >
                              Bewerken
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : null}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-8 flex items-center justify-between border-t border-[var(--line)] pt-6 dark:border-white/10">
              <button
                type="button"
                disabled={currentPage <= 1}
                onClick={() => updateParams({ page: String(currentPage - 1) })}
                className="ink-button secondary small disabled:opacity-40"
              >
                &larr; Vorige
              </button>

              <span className="font-mono text-xs text-[var(--muted)]">
                Pagina {currentPage} van {totalPages}
              </span>

              <button
                type="button"
                disabled={currentPage >= totalPages}
                onClick={() => updateParams({ page: String(currentPage + 1) })}
                className="ink-button secondary small disabled:opacity-40"
              >
                Volgende &rarr;
              </button>
            </div>
          )}
        </>
      )}

      {/* Edit Item Modal */}
      <CollectionEditModal
        item={selectedItem}
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        onUpdated={handleItemUpdated}
        onDeleted={handleItemDeleted}
      />
    </main>
  );
}

export default function CollectionPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
          <CardGridSkeleton count={12} />
        </div>
      }
    >
      <CollectionBrowser />
    </Suspense>
  );
}
