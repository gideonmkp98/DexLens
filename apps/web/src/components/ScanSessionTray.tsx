"use client";

import { useState } from "react";
import Image from "next/image";
import type {
  ScanSessionDetailResponse,
  ScanSessionItemResponse,
} from "@/lib/api";

export interface ScanSessionTrayProps {
  session: ScanSessionDetailResponse | null;
  items: ScanSessionItemResponse[];
  onSelectScan?: (item: ScanSessionItemResponse) => void;
  onCompleteSession?: () => void;
  isCompleting?: boolean;
  className?: string;
}

export default function ScanSessionTray({
  session,
  items,
  onSelectScan,
  onCompleteSession,
  isCompleting = false,
  className = "",
}: ScanSessionTrayProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const totalCount = items.length || session?.total_scans || 0;

  if (totalCount === 0) {
    return null;
  }

  return (
    <aside
      aria-label="Huidige scansessie"
      className={`fixed inset-x-0 bottom-0 z-30 flex flex-col transition-transform duration-300 ${
        isExpanded ? "translate-y-0" : ""
      } ${className}`}
    >
      {/* Floating Pill Bar */}
      <div className="mx-auto mb-2 flex w-[calc(100%-2rem)] max-w-lg items-center justify-between gap-2 rounded-2xl border border-white/20 bg-slate-950/85 px-4 py-2.5 text-white shadow-2xl backdrop-blur-md">
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex flex-1 items-center gap-2.5 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
          aria-expanded={isExpanded}
          aria-controls="scan-session-tray-drawer"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/20 text-[11px] font-bold text-emerald-300">
            {totalCount}
          </span>
          <div className="flex flex-col">
            <span className="font-bold tracking-tight">
              {totalCount === 1
                ? "1 kaart gescand"
                : `${totalCount} kaarten gescand`}
            </span>
            <span className="text-[10px] text-slate-400">
              {isExpanded ? "Tik om te verkleinen" : "Tik om lijst te bekijken"}
            </span>
          </div>
          <svg
            className={`ml-auto h-4 w-4 text-slate-400 transition-transform duration-200 ${
              isExpanded ? "rotate-180" : ""
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 15l7-7 7 7"
            />
          </svg>
        </button>

        {onCompleteSession && (
          <button
            type="button"
            onClick={onCompleteSession}
            disabled={isCompleting}
            className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition hover:bg-emerald-500 active:scale-95 disabled:opacity-50"
          >
            {isCompleting ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                <span>Afronden…</span>
              </>
            ) : (
              <>
                <span>Afronden</span>
                <span aria-hidden="true">✓</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* Expanded Horizontal Card Drawer */}
      {isExpanded && (
        <div
          id="scan-session-tray-drawer"
          className="border-t border-white/10 bg-slate-950/95 p-4 shadow-2xl backdrop-blur-xl"
        >
          <div className="mx-auto max-w-4xl">
            <div className="mb-2 flex items-center justify-between text-xs text-slate-300">
              <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                Sessiegeschiedenis ({items.length})
              </span>
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                className="text-xs text-slate-400 hover:text-white"
              >
                Sluiten ✕
              </button>
            </div>

            <div className="scrollbar-thin flex gap-3 overflow-x-auto pb-2 pt-1">
              {items.map((item, idx) => {
                const img = item.crop_image_url || item.image_url;
                const name = item.best_match?.name || "Onbekende kaart";
                const setInfo =
                  item.best_match?.set_name || "Scan #" + (idx + 1);

                return (
                  <button
                    key={item.scan_id || idx}
                    type="button"
                    onClick={() => onSelectScan?.(item)}
                    className="group relative flex w-24 flex-shrink-0 flex-col items-center rounded-xl border border-white/10 bg-slate-900/80 p-1.5 text-left text-white transition hover:border-emerald-400/60 hover:bg-slate-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                  >
                    {/* Thumbnail */}
                    <div className="relative aspect-card w-full overflow-hidden rounded-lg bg-slate-950">
                      {img ? (
                        <Image
                          src={img}
                          alt={name}
                          fill
                          sizes="96px"
                          className="object-cover transition group-hover:scale-105"
                          unoptimized
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center font-mono text-[9px] text-slate-500">
                          Geen foto
                        </div>
                      )}

                      {/* Collection status badge */}
                      {item.in_collection && (
                        <span
                          className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-[9px] font-bold text-white shadow"
                          title="In collectie"
                        >
                          ✓
                        </span>
                      )}
                    </div>

                    {/* Metadata */}
                    <div className="mt-1.5 w-full">
                      <p className="truncate text-[11px] font-bold leading-tight">
                        {name}
                      </p>
                      <p className="truncate font-mono text-[9px] text-slate-400">
                        {setInfo}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
