"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { getSets, PaginatedSetsResponse, SetSummary } from "@/lib/api";

export default function SetsPage() {
  const [setsData, setSetsData] = useState<PaginatedSetsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    getSets({ page, page_size: 24 })
      .then((data) => {
        if (mounted) {
          setSetsData(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load sets.");
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [page]);

  const totalPages = setsData
    ? Math.max(1, Math.ceil(setsData.total / setsData.page_size))
    : 1;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">
            Imported Sets
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Browse all Pokémon card sets imported into the local database index.
          </p>
        </div>
        <Link
          href="/cards"
          className="inline-flex items-center text-sm font-semibold text-red-600 hover:text-red-700"
        >
          &larr; Search All Cards
        </Link>
      </div>

      {error ? (
        <div className="mt-8 rounded-lg border border-red-200 bg-red-50 p-6 text-center text-red-700">
          <p className="font-semibold">{error}</p>
        </div>
      ) : loading ? (
        <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-44 animate-pulse rounded-xl bg-slate-200"
            />
          ))}
        </div>
      ) : setsData && setsData.items.length === 0 ? (
        <div className="mt-12 rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
          <span className="text-4xl">📦</span>
          <h3 className="mt-3 text-lg font-bold text-slate-900">
            No sets imported yet
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Run the card import command via CLI to populate physical sets into
            MariaDB.
          </p>
        </div>
      ) : setsData ? (
        <>
          <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {setsData.items.map((s: SetSummary) => (
              <Link
                key={s.id}
                href={`/sets/${s.id}`}
                className="group flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-400 hover:shadow-md"
              >
                <div>
                  <div className="flex h-16 items-center justify-center rounded-lg bg-slate-50 p-2">
                    {s.logo_url ? (
                      <div className="relative h-full w-full">
                        <Image
                          src={`${s.logo_url}.webp`}
                          alt={s.name}
                          fill
                          className="object-contain"
                          onError={(e) => {
                            // Fallback to plain url if extension fails
                            const target = e.currentTarget as HTMLImageElement;
                            if (target.src.endsWith(".webp") && s.logo_url) {
                              target.src = `${s.logo_url}.png`;
                            }
                          }}
                        />
                      </div>
                    ) : (
                      <span className="text-sm font-bold text-slate-400">
                        {s.name}
                      </span>
                    )}
                  </div>

                  <h3 className="mt-4 text-lg font-bold text-slate-900 group-hover:text-red-600">
                    {s.name}
                  </h3>

                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                    {s.series && (
                      <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                        Series: {s.series}
                      </span>
                    )}
                    {s.release_date && (
                      <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                        Released: {s.release_date}
                      </span>
                    )}
                  </div>
                </div>

                <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
                  <span className="font-semibold text-slate-700">
                    {s.local_card_count}{" "}
                    {s.local_card_count === 1 ? "card" : "cards"} indexed
                  </span>
                  <span className="font-bold text-red-600 group-hover:underline">
                    View Set Cards &rarr;
                  </span>
                </div>
              </Link>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="mt-10 flex items-center justify-between border-t border-slate-200 pt-6">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              >
                &larr; Previous
              </button>
              <span className="text-sm text-slate-600">
                Page{" "}
                <span className="font-semibold text-slate-900">{page}</span> of{" "}
                <span className="font-semibold text-slate-900">
                  {totalPages}
                </span>
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              >
                Next &rarr;
              </button>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
