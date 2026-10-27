"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { SetGridSkeleton } from "@/components/LoadingSkeleton";
import EmptyState from "@/components/EmptyState";
import { getSets, PaginatedSetsResponse, SetSummary } from "@/lib/api";

export default function SetsPage() {
  const [setsData, setSetsData] = useState<PaginatedSetsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);

    getSets({ page, page_size: 24 })
      .then((data) => {
        if (mounted) {
          setSetsData(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(
            err instanceof Error ? err.message : "Sets laden lukt niet."
          );
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [page, retry]);

  const totalPages = setsData
    ? Math.max(1, Math.ceil(setsData.total / setsData.page_size))
    : 1;

  return (
    <div className="catalog-page mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md border border-zinc-200 bg-zinc-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-zinc-600 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-400">
              DE VERZAMELMAP
            </span>
            <span className="font-mono text-xs text-zinc-400">POKÉMON TCG</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-3xl">
            Ontdek de sets
          </h1>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400 sm:text-sm">
            Blader door uitbreidingen en ontdek de kaarten uit elke generatie.
          </p>
        </div>

        <Link
          href="/cards"
          className="font-mono text-xs font-semibold text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
        >
          Bekijk alle kaarten &rarr;
        </Link>
      </div>

      {/* Grid or States */}
      <div className="mt-8">
        {loading ? (
          <SetGridSkeleton count={9} />
        ) : error ? (
          <EmptyState
            title="Sets laden lukt niet"
            description={error}
            actionLabel="Opnieuw proberen"
            onAction={() => setRetry((n) => n + 1)}
          />
        ) : setsData && setsData.items.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {setsData.items.map((s: SetSummary) => {
              const cardCount = s.card_count ?? s.local_card_count ?? 0;
              return (
                <Link
                  key={s.external_id}
                  href={`/sets/${encodeURIComponent(s.external_id)}`}
                  className="card-slab group flex flex-col justify-between rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-obsidian-900"
                >
                  <div>
                    {/* Top row: Symbol and card count pill */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        {s.symbol_url ? (
                          <div className="relative h-7 w-7 shrink-0 overflow-hidden rounded-md border border-zinc-200 bg-zinc-50 p-1 dark:border-zinc-800 dark:bg-obsidian-850">
                            <Image
                              src={s.symbol_url}
                              alt={s.name}
                              fill
                              className="object-contain"
                              unoptimized
                            />
                          </div>
                        ) : (
                          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 bg-zinc-50 font-mono text-xs font-bold text-zinc-500 dark:border-zinc-800 dark:bg-obsidian-850">
                            S
                          </div>
                        )}
                        <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                          {s.series || "Expansion"}
                        </span>
                      </div>

                      <span className="rounded border border-zinc-200 bg-zinc-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-zinc-700 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-300">
                        {cardCount} kaarten
                      </span>
                    </div>

                    {/* Logo display if available */}
                    {s.logo_url && (
                      <div className="relative mt-4 flex h-14 w-full items-center justify-center rounded-xl border border-zinc-100 bg-zinc-50/60 p-2 dark:border-zinc-800/80 dark:bg-obsidian-950">
                        <Image
                          src={
                            /\.(webp|png)$/i.test(s.logo_url)
                              ? s.logo_url
                              : `${s.logo_url}.webp`
                          }
                          alt={s.name}
                          fill
                          className="object-contain p-1"
                          onError={(e) => {
                            const target = e.currentTarget as HTMLImageElement;
                            if (target.src.endsWith(".webp") && s.logo_url) {
                              target.src =
                                s.logo_url.replace(/\.(webp|png)$/i, "") +
                                ".png";
                            }
                          }}
                          unoptimized
                        />
                      </div>
                    )}

                    <h3 className="mt-3 text-base font-bold text-zinc-900 transition group-hover:text-zinc-600 dark:text-white dark:group-hover:text-zinc-300">
                      {s.name}
                    </h3>

                    {s.release_date && (
                      <p className="mt-0.5 font-mono text-xs text-zinc-400">
                        Uitgebracht: {s.release_date}
                      </p>
                    )}
                  </div>

                  <div className="mt-5 flex items-center justify-between border-t border-zinc-100 pt-3 font-mono text-xs font-semibold text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                    <span>Bekijk de kaarten</span>
                    <span className="transition group-hover:translate-x-1">
                      &rarr;
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="Geen sets gevonden"
            description="Er zijn momenteel geen sets beschikbaar."
            actionHref="/cards"
            actionLabel="Bekijk kaarten"
          />
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-10 flex items-center justify-center gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
          <button
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage(page - 1)}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-800 dark:bg-obsidian-900 dark:text-zinc-200 dark:hover:bg-obsidian-850"
          >
            &larr; Vorige
          </button>

          <span className="font-mono text-xs font-medium text-zinc-500 dark:text-zinc-400">
            Pagina {page} van {totalPages}
          </span>

          <button
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() => setPage(page + 1)}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-800 dark:bg-obsidian-900 dark:text-zinc-200 dark:hover:bg-obsidian-850"
          >
            Volgende &rarr;
          </button>
        </div>
      )}
    </div>
  );
}

