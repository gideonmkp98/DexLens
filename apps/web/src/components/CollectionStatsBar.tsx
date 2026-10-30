"use client";

import { CollectionStats } from "@/lib/api";

interface CollectionStatsBarProps {
  stats: CollectionStats | null;
  loading: boolean;
}

export default function CollectionStatsBar({
  stats,
  loading,
}: CollectionStatsBarProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 dark:border-white/10"
          >
            <div className="h-3 w-16 rounded bg-[var(--paper)]" />
            <div className="mt-2 h-7 w-20 rounded bg-[var(--paper)]" />
          </div>
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const statItems = [
    {
      label: "Fysieke kaarten",
      value: stats.total_cards,
      sub: "Totaal aantal exemplaren",
      icon: (
        <svg
          className="h-4 w-4 text-[var(--red)]"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          />
        </svg>
      ),
    },
    {
      label: "Unieke kaarten",
      value: stats.unique_cards,
      sub: "Verschillende kaarten",
      icon: (
        <svg
          className="h-4 w-4 text-sky-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
    {
      label: "Sets vertegenwoordigd",
      value: stats.total_sets,
      sub: "Uitbreidingen in collectie",
      icon: (
        <svg
          className="h-4 w-4 text-purple-500"
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
      ),
    },
    {
      label: "Dubbele kaarten",
      value: stats.duplicate_count,
      sub: "Ruilmateriaal / trade binder",
      highlight: stats.duplicate_count > 0,
      icon: (
        <svg
          className="h-4 w-4 text-amber-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
          />
        </svg>
      ),
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
      {statItems.map((item, idx) => (
        <div
          key={idx}
          className={`card-slab flex flex-col justify-between rounded-2xl border bg-[var(--surface)] p-4 shadow-sm transition hover:shadow-md dark:border-white/10 ${
            item.highlight
              ? "border-amber-500/40 bg-gradient-to-br from-[var(--surface)] to-amber-500/5 dark:to-amber-500/10"
              : "border-[var(--line)]"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[var(--muted)]">
              {item.label}
            </span>
            <div className="rounded-lg bg-[var(--paper)] p-1.5 dark:bg-vault-800">
              {item.icon}
            </div>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono text-2xl font-black text-[var(--ink)] sm:text-3xl">
              {item.value.toLocaleString("nl-NL")}
            </span>
            {item.highlight && (
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] font-bold text-amber-700 dark:text-amber-300">
                Ruilbaar
              </span>
            )}
          </div>
          <p className="mt-1 font-mono text-[10px] text-[var(--muted)]">
            {item.sub}
          </p>
        </div>
      ))}
    </div>
  );
}
