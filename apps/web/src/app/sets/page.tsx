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
            err instanceof Error
              ? "De setcatalogus is tijdelijk niet bereikbaar. Controleer de verbinding en probeer het opnieuw."
              : "De sets konden niet worden geladen."
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
    <main className="content-page catalog-page">
      {/* Header */}
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            <span className="red-square" /> DE VERZAMELMAP / POKÉMON TCG
          </p>
          <h1>Ontdek de sets</h1>
          <p className="page-intro">
            Blader door uitbreidingen en ontdek de kaarten uit elke generatie.
          </p>
        </div>

        <Link href="/cards" className="text-link quiet">
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
          <div className="set-grid">
            {setsData.items.map((s: SetSummary) => {
              const cardCount = s.card_count ?? s.local_card_count ?? 0;
              return (
                <Link
                  key={s.external_id}
                  href={`/sets/${encodeURIComponent(s.external_id)}`}
                  className="set-ticket card-slab group"
                >
                  <div>
                    {/* Top row: Symbol and card count pill */}
                    <div className="set-ticket-top">
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
                        <span className="set-series">
                          {s.series || "Expansion"}
                        </span>
                      </div>

                      <span className="set-count">{cardCount} kaarten</span>
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

                    <h3>{s.name}</h3>

                    {s.release_date && (
                      <p className="set-date">Uitgebracht: {s.release_date}</p>
                    )}
                  </div>

                  <div className="set-ticket-footer">
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
        <div className="pagination">
          <button
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => setPage(page - 1)}
            className="ink-button secondary small"
          >
            &larr; Vorige
          </button>

          <span>
            Pagina {page} van {totalPages}
          </span>

          <button
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() => setPage(page + 1)}
            className="ink-button secondary small"
          >
            Volgende &rarr;
          </button>
        </div>
      )}
    </main>
  );
}
