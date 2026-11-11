"use client";

import React from "react";
import type { AdminUserItem } from "@/lib/admin";

interface UsersTabProps {
  users: AdminUserItem[];
  usersTotal: number;
  usersLoading: boolean;
  userQuery: string;
  setUserQuery: (val: string) => void;
  userStatusFilter: string;
  setUserStatusFilter: (val: string) => void;
  userRoleFilter: string;
  setUserRoleFilter: (val: string) => void;
  userVerificationFilter: string;
  setUserVerificationFilter: (val: string) => void;
  userPage: number;
  setUserPage: React.Dispatch<React.SetStateAction<number>>;
  onRefresh: () => void;
  onViewUserDetails: (userId: string) => void;
  onOpenStatusModal: (user: AdminUserItem) => void;
  onOpenQuotaModal: (user: AdminUserItem) => void;
}

export function UsersTab({
  users,
  usersTotal,
  usersLoading,
  userQuery,
  setUserQuery,
  userStatusFilter,
  setUserStatusFilter,
  userRoleFilter,
  setUserRoleFilter,
  userVerificationFilter,
  setUserVerificationFilter,
  userPage,
  setUserPage,
  onRefresh,
  onViewUserDetails,
  onOpenStatusModal,
  onOpenQuotaModal,
}: UsersTabProps) {
  return (
    <section className="mt-6 space-y-6" aria-label="Gebruikersbeheer">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-4 text-xs">
        <div className="min-w-[200px] flex-1">
          <input
            type="text"
            value={userQuery}
            onChange={(e) => {
              setUserQuery(e.target.value);
              setUserPage(0);
            }}
            placeholder="Zoek op e-mailadres of ID…"
            className="w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] placeholder:text-[#b6bbaa]/50 focus:border-[#f1ca53] focus:outline-none"
          />
        </div>
        <div>
          <select
            value={userStatusFilter}
            onChange={(e) => {
              setUserStatusFilter(e.target.value);
              setUserPage(0);
            }}
            aria-label="Filter op status"
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
          >
            <option value="">Alle statussen</option>
            <option value="active">Actief</option>
            <option value="suspended">Geschorst</option>
            <option value="blocked">Geblokkeerd</option>
          </select>
        </div>
        <div>
          <select
            value={userRoleFilter}
            onChange={(e) => {
              setUserRoleFilter(e.target.value);
              setUserPage(0);
            }}
            aria-label="Filter op rol"
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
          >
            <option value="">Alle rollen</option>
            <option value="user">Gebruiker</option>
            <option value="admin">Beheerder</option>
          </select>
        </div>
        <div>
          <select
            value={userVerificationFilter}
            onChange={(e) => {
              setUserVerificationFilter(e.target.value);
              setUserPage(0);
            }}
            aria-label="Filter op verificatiestatus"
            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
          >
            <option value="">Alle verificatie</option>
            <option value="verified">Geverifieerd</option>
            <option value="unverified">Niet geverifieerd</option>
            <option value="pending">In afwachting</option>
          </select>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 font-bold text-[#f3efdf] hover:border-[#f1ca53]"
        >
          Vernieuwen
        </button>
      </div>

      {/* Users Table */}
      <div className="overflow-x-auto rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f]">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-[#f3efdf]/15 bg-[#171c16] font-mono text-[10px] uppercase text-[#b6bbaa]">
            <tr>
              <th className="px-4 py-3">E-mail / ID</th>
              <th className="px-4 py-3">Rol</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Verificatie</th>
              <th className="px-4 py-3">Quota override</th>
              <th className="px-4 py-3">Aangemaakt</th>
              <th className="px-4 py-3 text-right">Acties</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#f3efdf]/10">
            {usersLoading ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-[#b6bbaa]"
                >
                  Gebruikers laden…
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-[#b6bbaa]"
                >
                  Geen gebruikers gevonden die voldoen aan de filters.
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className="hover:bg-[#1a1f19]/70">
                  <td className="px-4 py-3">
                    <div className="font-bold text-[#f3efdf]">{u.email}</div>
                    <div className="font-mono text-[10px] text-[#b6bbaa]/60">
                      {u.id}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${
                        u.role === "admin"
                          ? "border border-[#f1ca53]/40 bg-[#f1ca53]/20 text-[#f1ca53]"
                          : "bg-[#171c16] text-[#b6bbaa]"
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                        u.status === "active"
                          ? "border border-emerald-500/30 bg-emerald-950 text-emerald-300"
                          : u.status === "suspended"
                            ? "border border-amber-500/30 bg-amber-950 text-amber-300"
                            : "border border-rose-500/30 bg-rose-950 text-rose-300"
                      }`}
                    >
                      {u.status === "active"
                        ? "Actief"
                        : u.status === "suspended"
                          ? "Geschorst"
                          : "Geblokkeerd"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[#b6bbaa]">
                    {u.verification_status === "verified" ? (
                      <span className="text-emerald-400">✓ Geverifieerd</span>
                    ) : u.verification_status === "pending" ? (
                      <span className="text-amber-400">⌛ In afwachting</span>
                    ) : (
                      <span className="text-[#b6bbaa]">Niet geverifieerd</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px]">
                    {u.scan_quota_override !== null ? (
                      <span className="text-[#f1ca53]">
                        {u.scan_quota_override} / dag
                      </span>
                    ) : (
                      <span className="text-[#b6bbaa]/50">
                        Standaard (globaal)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-[10px] text-[#b6bbaa]">
                    {new Date(u.created_at).toLocaleDateString("nl-NL")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => onViewUserDetails(u.id)}
                        className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-2 py-1 text-[11px] font-semibold text-[#f3efdf] hover:border-[#f1ca53]"
                      >
                        Details
                      </button>
                      <button
                        type="button"
                        onClick={() => onOpenStatusModal(u)}
                        className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-2 py-1 text-[11px] font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                      >
                        Status
                      </button>
                      <button
                        type="button"
                        onClick={() => onOpenQuotaModal(u)}
                        className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-2 py-1 text-[11px] font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                      >
                        Quota
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-[#b6bbaa]">
        <span>Totaal: {usersTotal} accounts</span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={userPage === 0}
            onClick={() => setUserPage((p) => Math.max(0, p - 1))}
            className="rounded border border-[#f3efdf]/20 bg-[#20251f] px-3 py-1 font-bold disabled:opacity-40"
          >
            Vorige
          </button>
          <span className="py-1 font-mono">Pagina {userPage + 1}</span>
          <button
            type="button"
            disabled={(userPage + 1) * 20 >= usersTotal}
            onClick={() => setUserPage((p) => p + 1)}
            className="rounded border border-[#f3efdf]/20 bg-[#20251f] px-3 py-1 font-bold disabled:opacity-40"
          >
            Volgende
          </button>
        </div>
      </div>
    </section>
  );
}
