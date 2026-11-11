"use client";

import React from "react";
import type { AdminUserDetailsResponse, AdminUserItem } from "@/lib/admin";

interface UserDetailsModalProps {
  details: AdminUserDetailsResponse | null;
  onClose: () => void;
  onOpenStatusModal: (user: AdminUserItem) => void;
  onOpenQuotaModal: (user: AdminUserItem) => void;
}

export function UserDetailsModal({
  details,
  onClose,
  onOpenStatusModal,
  onOpenQuotaModal,
}: UserDetailsModalProps) {
  if (!details) return null;

  const asUserItem: AdminUserItem = {
    id: details.id,
    email: details.email,
    role: details.role,
    status: details.status,
    is_active: details.is_active,
    verification_status: details.verification_status,
    scan_quota_override: details.scan_quota_override,
    created_at: details.created_at,
    updated_at: details.updated_at,
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="user-details-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="relative max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
        <div className="flex items-start justify-between border-b border-[#f3efdf]/15 pb-4">
          <div>
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#f1ca53]">
              Accountdossier
            </span>
            <h2
              id="user-details-title"
              className="font-serif text-xl font-bold text-[#f3efdf]"
            >
              {details.email}
            </h2>
            <div className="font-mono text-xs text-[#b6bbaa]/70">
              {details.id}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded border border-[#f3efdf]/20 text-xs text-[#b6bbaa] hover:text-[#f3efdf]"
          >
            ✕
          </button>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-3">
          <div className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 text-center">
            <span className="font-mono text-[10px] uppercase text-[#b6bbaa]">
              Totaal Scans
            </span>
            <div className="font-serif text-xl font-bold text-[#f3efdf]">
              {details.scans_count}
            </div>
          </div>
          <div className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 text-center">
            <span className="font-mono text-[10px] uppercase text-[#b6bbaa]">
              Collectie
            </span>
            <div className="font-serif text-xl font-bold text-[#f3efdf]">
              {details.collection_items_count}
            </div>
          </div>
          <div className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 text-center">
            <span className="font-mono text-[10px] uppercase text-[#b6bbaa]">
              Actieve Sessies
            </span>
            <div className="font-serif text-xl font-bold text-[#f3efdf]">
              {details.active_sessions_count}
            </div>
          </div>
        </div>

        {/* Quota details */}
        <div className="mt-6 rounded border border-[#f3efdf]/10 bg-[#171c16] p-4 text-xs">
          <span className="font-mono text-[10px] font-bold uppercase text-[#f1ca53]">
            Effectieve Quota
          </span>
          <div className="mt-2 grid grid-cols-2 gap-2 text-[#b6bbaa]">
            <div>
              Dagelijkse limiet:{" "}
              <strong className="text-[#f3efdf]">
                {details.quota.effective_daily_limit} scans
              </strong>
            </div>
            <div>
              Uurlijkse limiet:{" "}
              <strong className="text-[#f3efdf]">
                {details.quota.effective_hourly_limit} scans
              </strong>
            </div>
            <div>
              Aangepaste override:{" "}
              <strong className="text-[#f3efdf]">
                {details.quota.has_override
                  ? `${details.quota.user_override} scans`
                  : "Geen (standaard)"}
              </strong>
            </div>
            <div>
              Blokkade actief:{" "}
              <strong className="text-[#f3efdf]">
                {details.quota.is_blocked_or_suspended ? "Ja" : "Nee"}
              </strong>
            </div>
          </div>
        </div>

        {/* Actions inside details modal */}
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => onOpenStatusModal(asUserItem)}
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
          >
            Status Wijzigen
          </button>
          <button
            type="button"
            onClick={() => onOpenQuotaModal(asUserItem)}
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
          >
            Quota Aanpassen
          </button>
        </div>

        {/* Recent audit events */}
        <div className="mt-6">
          <span className="font-mono text-[10px] font-bold uppercase text-[#b6bbaa]">
            Recente Beheerdersacties op dit account
          </span>
          {details.recent_audit_events.length === 0 ? (
            <p className="mt-2 text-xs text-[#b6bbaa]/50">
              Geen recente beheerdersacties geregistreerd.
            </p>
          ) : (
            <div className="mt-2 space-y-2">
              {details.recent_audit_events.map((event) => (
                <div
                  key={event.id}
                  className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-2.5 text-xs"
                >
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className="text-[#f1ca53]">{event.action}</span>
                    <span className="text-[#b6bbaa]">
                      {new Date(event.created_at).toLocaleString("nl-NL")}
                    </span>
                  </div>
                  {event.metadata && (
                    <pre className="mt-1 max-h-24 overflow-x-auto text-[10px] text-[#b6bbaa]/70">
                      {JSON.stringify(event.metadata, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
