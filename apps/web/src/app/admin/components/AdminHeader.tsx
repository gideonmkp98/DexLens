"use client";

import React from "react";

export type TabType = "users" | "beta" | "quotas" | "audit" | "abuse";

interface AdminHeaderProps {
  currentUserEmail: string;
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
}

const TABS: Array<[TabType, string]> = [
  ["users", "Gebruikers"],
  ["beta", "Bètacodes & Uitnodigingen"],
  ["quotas", "Scan-quota"],
  ["audit", "Auditlogboek"],
  ["abuse", "Misbruikpreventie"],
];

export function AdminHeader({
  currentUserEmail,
  activeTab,
  setActiveTab,
}: AdminHeaderProps) {
  return (
    <>
      <div className="flex flex-col gap-4 border-b border-[#f3efdf]/15 pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="pokeball brand-ball !h-6 !w-6"
              aria-hidden="true"
            />
            <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-[#f1ca53]">
              DexLens Beheeromgeving
            </span>
          </div>
          <h1 className="mt-1 font-serif text-2xl font-bold tracking-tight text-[#f3efdf] sm:text-3xl">
            Systeem- &amp; Gebruikersbeheer
          </h1>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-[#b6bbaa]">
          <span>Ingelogd als:</span>
          <span className="rounded border border-[#f3efdf]/15 bg-[#20251f] px-2 py-1 text-[#f3efdf]">
            {currentUserEmail}
          </span>
        </div>
      </div>

      <nav
        aria-label="Beheeronderdelen"
        className="mt-6 flex flex-wrap gap-2 border-b border-[#f3efdf]/10 pb-2"
      >
        {TABS.map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`rounded px-3.5 py-2 text-xs font-bold transition ${
              activeTab === tab
                ? "border border-[#f3efdf]/20 bg-[#252923] text-[#f1ca53] shadow-[1px_1px_0_#10150f]"
                : "text-[#b6bbaa] hover:bg-[#1a1f19] hover:text-[#f3efdf]"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
    </>
  );
}
