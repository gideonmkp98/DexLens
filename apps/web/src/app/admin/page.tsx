"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import {
  listAdminUsers,
  getAdminUserDetails,
  updateAdminUserStatus,
  updateAdminUserQuota,
  getGlobalQuota,
  updateGlobalQuota,
  listBetaCodes,
  createBetaCode,
  revokeBetaCode,
  listAuditLogs,
  getAbuseStatus,
  type AdminUserItem,
  type AdminUserDetailsResponse,
  type GlobalQuotaResponse,
  type BetaCodeResponse,
  type AuditLogResponse,
  type AbuseStatusResponse,
} from "@/lib/admin";

type TabType = "users" | "beta" | "quotas" | "audit" | "abuse";

export default function AdminPage() {
  const { status: authStatus, user: currentUser } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>("users");

  // Users state
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [usersTotal, setUsersTotal] = useState<number>(0);
  const [usersLoading, setUsersLoading] = useState<boolean>(false);
  const [userQuery, setUserQuery] = useState<string>("");
  const [userStatusFilter, setUserStatusFilter] = useState<string>("");
  const [userRoleFilter, setUserRoleFilter] = useState<string>("");
  const [userVerificationFilter, setUserVerificationFilter] = useState<string>("");
  const [userPage, setUserPage] = useState<number>(0);

  // User details modal state
  const [selectedUserDetails, setSelectedUserDetails] = useState<AdminUserDetailsResponse | null>(null);
  const [userDetailsLoading, setUserDetailsLoading] = useState<boolean>(false);

  // Status modal state
  const [statusTargetUser, setStatusTargetUser] = useState<AdminUserItem | null>(null);
  const [newStatus, setNewStatus] = useState<"active" | "suspended" | "blocked">("active");
  const [statusReason, setStatusReason] = useState<string>("");
  const [statusUpdating, setStatusUpdating] = useState<boolean>(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Quota modal state
  const [quotaTargetUser, setQuotaTargetUser] = useState<AdminUserItem | null>(null);
  const [userQuotaValue, setUserQuotaValue] = useState<string>("");
  const [quotaReason, setQuotaReason] = useState<string>("");
  const [quotaUpdating, setQuotaUpdating] = useState<boolean>(false);
  const [quotaError, setQuotaError] = useState<string | null>(null);

  // Beta codes state
  const [betaCodes, setBetaCodes] = useState<BetaCodeResponse[]>([]);
  const [betaTotal, setBetaTotal] = useState<number>(0);
  const [betaLoading, setBetaLoading] = useState<boolean>(false);
  const [betaSearch, setBetaSearch] = useState<string>("");
  const [betaStatusFilter, setBetaStatusFilter] = useState<string>("");

  // Create beta code modal state
  const [showCreateBetaModal, setShowCreateBetaModal] = useState<boolean>(false);
  const [newBetaLabel, setNewBetaLabel] = useState<string>("");
  const [newBetaEmail, setNewBetaEmail] = useState<string>("");
  const [newBetaMaxUses, setNewBetaMaxUses] = useState<number>(1);
  const [newBetaExpiresDays, setNewBetaExpiresDays] = useState<number>(30);
  const [creatingBeta, setCreatingBeta] = useState<boolean>(false);
  const [createBetaError, setCreateBetaError] = useState<string | null>(null);

  // Revoke beta code modal state
  const [revokeTargetCode, setRevokeTargetCode] = useState<BetaCodeResponse | null>(null);
  const [revokeReason, setRevokeReason] = useState<string>("");
  const [revokingCode, setRevokingCode] = useState<boolean>(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  // Global quota state
  const [globalQuota, setGlobalQuota] = useState<GlobalQuotaResponse | null>(null);
  const [globalDailyLimit, setGlobalDailyLimit] = useState<number>(100);
  const [globalHourlyLimit, setGlobalHourlyLimit] = useState<number>(30);
  const [globalQuotaReason, setGlobalQuotaReason] = useState<string>("");
  const [globalQuotaUpdating, setGlobalQuotaUpdating] = useState<boolean>(false);
  const [globalQuotaSuccess, setGlobalQuotaSuccess] = useState<string | null>(null);
  const [globalQuotaError, setGlobalQuotaError] = useState<string | null>(null);

  // Audit logs state
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [auditTotal, setAuditTotal] = useState<number>(0);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);
  const [auditActionFilter, setAuditActionFilter] = useState<string>("");
  const [selectedAuditLog, setSelectedAuditLog] = useState<AuditLogResponse | null>(null);

  // Abuse status state
  const [abuseStatus, setAbuseStatus] = useState<AbuseStatusResponse | null>(null);
  const [abuseLoading, setAbuseLoading] = useState<boolean>(false);

  // Global feedback message
  const [toastMessage, setToastMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const showToast = (text: string, type: "success" | "error" = "success") => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  // 1. Load users
  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      const res = await listAdminUsers({
        q: userQuery || undefined,
        status: userStatusFilter || undefined,
        role: userRoleFilter || undefined,
        verification_status: userVerificationFilter || undefined,
        limit: 20,
        offset: userPage * 20,
      });
      setUsers(res.items);
      setUsersTotal(res.total);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fout bij ophalen gebruikers", "error");
    } finally {
      setUsersLoading(false);
    }
  }, [userQuery, userStatusFilter, userRoleFilter, userVerificationFilter, userPage]);

  // 2. Load beta codes
  const loadBetaCodes = useCallback(async () => {
    setBetaLoading(true);
    try {
      const res = await listBetaCodes({
        search: betaSearch || undefined,
        status: betaStatusFilter || undefined,
        limit: 30,
        offset: 0,
      });
      setBetaCodes(res.items);
      setBetaTotal(res.total);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fout bij ophalen bètacodes", "error");
    } finally {
      setBetaLoading(false);
    }
  }, [betaSearch, betaStatusFilter]);

  // 3. Load global quota
  const loadGlobalQuota = useCallback(async () => {
    try {
      const res = await getGlobalQuota();
      setGlobalQuota(res);
      setGlobalDailyLimit(res.daily_scan_limit);
      setGlobalHourlyLimit(res.hourly_scan_limit);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fout bij ophalen quota", "error");
    }
  }, []);

  // 4. Load audit logs
  const loadAuditLogs = useCallback(async () => {
    setAuditLoading(true);
    try {
      const res = await listAuditLogs({
        action: auditActionFilter || undefined,
        limit: 50,
        offset: 0,
      });
      setAuditLogs(res.items);
      setAuditTotal(res.total);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fout bij ophalen auditlogboeken", "error");
    } finally {
      setAuditLoading(false);
    }
  }, [auditActionFilter]);

  // 5. Load abuse status
  const loadAbuseStatus = useCallback(async () => {
    setAbuseLoading(true);
    try {
      const res = await getAbuseStatus();
      setAbuseStatus(res);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fout bij ophalen misbruikstatus", "error");
    } finally {
      setAbuseLoading(false);
    }
  }, []);

  // Fetch based on active tab
  useEffect(() => {
    if (authStatus !== "authenticated" || currentUser?.role !== "admin") return;

    if (activeTab === "users") loadUsers();
    else if (activeTab === "beta") loadBetaCodes();
    else if (activeTab === "quotas") loadGlobalQuota();
    else if (activeTab === "audit") loadAuditLogs();
    else if (activeTab === "abuse") loadAbuseStatus();
  }, [activeTab, authStatus, currentUser, loadUsers, loadBetaCodes, loadGlobalQuota, loadAuditLogs, loadAbuseStatus]);

  // View user details
  const handleViewUserDetails = async (userId: string) => {
    setUserDetailsLoading(true);
    try {
      const details = await getAdminUserDetails(userId);
      setSelectedUserDetails(details);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fout bij ophalen details", "error");
    } finally {
      setUserDetailsLoading(false);
    }
  };

  // Open status modal
  const handleOpenStatusModal = (u: AdminUserItem) => {
    setStatusTargetUser(u);
    setNewStatus((u.status as "active" | "suspended" | "blocked") || "active");
    setStatusReason("");
    setStatusError(null);
  };

  // Submit status update
  const handleSubmitStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statusTargetUser) return;
    if (statusReason.trim().length < 3) {
      setStatusError("Geef een toelichting op van minimaal 3 tekens.");
      return;
    }

    setStatusUpdating(true);
    setStatusError(null);
    try {
      await updateAdminUserStatus(statusTargetUser.id, newStatus, statusReason.trim());
      showToast(`Status van ${statusTargetUser.email} gewijzigd naar '${newStatus}'.`);
      setStatusTargetUser(null);
      loadUsers();
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Bijwerken van status mislukt.");
    } finally {
      setStatusUpdating(false);
    }
  };

  // Open quota modal
  const handleOpenQuotaModal = (u: AdminUserItem) => {
    setQuotaTargetUser(u);
    setUserQuotaValue(u.scan_quota_override !== null ? String(u.scan_quota_override) : "");
    setQuotaReason("");
    setQuotaError(null);
  };

  // Submit quota update
  const handleSubmitQuota = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quotaTargetUser) return;
    if (quotaReason.trim().length < 3) {
      setQuotaError("Geef een toelichting op van minimaal 3 tekens.");
      return;
    }

    const overrideVal = userQuotaValue.trim() === "" ? null : parseInt(userQuotaValue, 10);
    if (overrideVal !== null && (isNaN(overrideVal) || overrideVal < 0)) {
      setQuotaError("Quota moet een positief getal zijn of leeg voor globaal standaard.");
      return;
    }

    setQuotaUpdating(true);
    setQuotaError(null);
    try {
      await updateAdminUserQuota(quotaTargetUser.id, overrideVal, quotaReason.trim());
      showToast(`Quota van ${quotaTargetUser.email} bijgewerkt.`);
      setQuotaTargetUser(null);
      loadUsers();
    } catch (err) {
      setQuotaError(err instanceof Error ? err.message : "Bijwerken van quota mislukt.");
    } finally {
      setQuotaUpdating(false);
    }
  };

  // Submit global quota update
  const handleUpdateGlobalQuota = async (e: React.FormEvent) => {
    e.preventDefault();
    if (globalQuotaReason.trim().length < 3) {
      setGlobalQuotaError("Geef een toelichting op van minimaal 3 tekens.");
      return;
    }
    if (globalDailyLimit <= 0 || globalHourlyLimit <= 0) {
      setGlobalQuotaError("Limieten moeten groter zijn dan 0.");
      return;
    }

    setGlobalQuotaUpdating(true);
    setGlobalQuotaError(null);
    setGlobalQuotaSuccess(null);
    try {
      const updated = await updateGlobalQuota(globalDailyLimit, globalHourlyLimit, globalQuotaReason.trim());
      setGlobalQuota(updated);
      setGlobalQuotaSuccess("Globale quota succesvol bijgewerkt!");
      setGlobalQuotaReason("");
      showToast("Globale quota bijgewerkt!");
    } catch (err) {
      setGlobalQuotaError(err instanceof Error ? err.message : "Bijwerken mislukt.");
    } finally {
      setGlobalQuotaUpdating(false);
    }
  };

  // Submit new beta code
  const handleCreateBetaCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingBeta(true);
    setCreateBetaError(null);
    try {
      await createBetaCode({
        label: newBetaLabel.trim() || undefined,
        invitation_email: newBetaEmail.trim() || undefined,
        max_uses: newBetaMaxUses,
        expires_days: newBetaExpiresDays,
      });
      showToast("Nieuwe bètacode succesvol aangemaakt!");
      setShowCreateBetaModal(false);
      setNewBetaLabel("");
      setNewBetaEmail("");
      loadBetaCodes();
    } catch (err) {
      setCreateBetaError(err instanceof Error ? err.message : "Aanmaken mislukt.");
    } finally {
      setCreatingBeta(false);
    }
  };

  // Submit revoke beta code
  const handleRevokeBetaCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!revokeTargetCode) return;
    if (revokeReason.trim().length < 3) {
      setRevokeError("Geef een toelichting op van minimaal 3 tekens.");
      return;
    }

    setRevokingCode(true);
    setRevokeError(null);
    try {
      await revokeBetaCode(revokeTargetCode.id, revokeReason.trim());
      showToast(`Bètacode '${revokeTargetCode.code}' ingetrokken.`);
      setRevokeTargetCode(null);
      loadBetaCodes();
    } catch (err) {
      setRevokeError(err instanceof Error ? err.message : "Intrekken mislukt.");
    } finally {
      setRevokingCode(false);
    }
  };

  // Access Control: Loading
  if (authStatus === "loading") {
    return (
      <main className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 rounded bg-[#20251f]" />
          <div className="h-12 w-full rounded bg-[#20251f]" />
          <div className="h-96 w-full rounded bg-[#20251f]" />
        </div>
      </main>
    );
  }

  // Access Control: Not admin or anonymous
  if (authStatus !== "authenticated" || currentUser?.role !== "admin") {
    return (
      <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4 text-center">
        <div className="rounded-[7px] border border-[#eb6b5d]/30 bg-[#20251f] p-8 shadow-[7px_7px_0_#10150f]">
          <span className="font-mono text-xs font-bold uppercase tracking-widest text-[#eb6b5d]">
            403 • Geen toegang
          </span>
          <h1 className="mt-2 font-serif text-2xl font-bold text-[#f3efdf]">
            Beheerderspaneel Vergrendeld
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-[#b6bbaa]">
            Dit gedeelte van DexLens is uitsluitend toegankelijk voor geverifieerde beheerders met beheerdersrechten.
          </p>
          <div className="mt-6 flex justify-center">
            <Link
              href="/"
              className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-[#f3efdf] transition hover:border-[#f1ca53]"
            >
              Terug naar start
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Toast Alert */}
      {toastMessage && (
        <div
          role="status"
          className={`fixed bottom-6 right-6 z-50 rounded-[4px] border px-4 py-3 text-xs font-bold shadow-lg transition-all ${
            toastMessage.type === "success"
              ? "border-emerald-500/50 bg-[#171c16] text-emerald-300"
              : "border-[#eb6b5d]/50 bg-[#171c16] text-[#ff9387]"
          }`}
        >
          {toastMessage.text}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col gap-4 border-b border-[#f3efdf]/15 pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="pokeball brand-ball !h-6 !w-6" aria-hidden="true" />
            <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-[#f1ca53]">
              DexLens Beheeromgeving
            </span>
          </div>
          <h1 className="mt-1 font-serif text-2xl font-bold tracking-tight text-[#f3efdf] sm:text-3xl">
            Systeem- & Gebruikersbeheer
          </h1>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-[#b6bbaa]">
          <span>Ingelogd als:</span>
          <span className="rounded bg-[#20251f] px-2 py-1 text-[#f3efdf] border border-[#f3efdf]/15">
            {currentUser.email}
          </span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mt-6 flex flex-wrap gap-2 border-b border-[#f3efdf]/10 pb-2">
        {(
          [
            ["users", "Gebruikers"],
            ["beta", "Bètacodes & Uitnodigingen"],
            ["quotas", "Scan-quota"],
            ["audit", "Auditlogboek"],
            ["abuse", "Misbruikpreventie"],
          ] as const
        ).map(([tab, label]) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`rounded px-3.5 py-2 text-xs font-bold transition ${
              activeTab === tab
                ? "bg-[#252923] text-[#f1ca53] shadow-[1px_1px_0_#10150f] border border-[#f3efdf]/20"
                : "text-[#b6bbaa] hover:text-[#f3efdf] hover:bg-[#1a1f19]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ======================================================== */}
      {/* TAB 1: USERS                                             */}
      {/* ======================================================== */}
      {activeTab === "users" && (
        <section className="mt-6 space-y-6" aria-label="Gebruikersbeheer">
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3 rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-4 text-xs">
            <div className="flex-1 min-w-[200px]">
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
              onClick={loadUsers}
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
                    <td colSpan={7} className="px-4 py-8 text-center text-[#b6bbaa]">
                      Gebruikers laden…
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#b6bbaa]">
                      Geen gebruikers gevonden die voldoen aan de filters.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="hover:bg-[#1a1f19]/70">
                      <td className="px-4 py-3">
                        <div className="font-bold text-[#f3efdf]">{u.email}</div>
                        <div className="font-mono text-[10px] text-[#b6bbaa]/60">{u.id}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${
                            u.role === "admin"
                              ? "bg-[#f1ca53]/20 text-[#f1ca53] border border-[#f1ca53]/40"
                              : "bg-[#171c16] text-[#b6bbaa]"
                          }`}
                        >
                          {u.role}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded px-2 py-0.5 font-bold text-[10px] ${
                            u.status === "active"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                              : u.status === "suspended"
                              ? "bg-amber-950 text-amber-300 border border-amber-500/30"
                              : "bg-rose-950 text-rose-300 border border-rose-500/30"
                          }`}
                        >
                          {u.status === "active" ? "Actief" : u.status === "suspended" ? "Geschorst" : "Geblokkeerd"}
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
                          <span className="text-[#f1ca53]">{u.scan_quota_override} / dag</span>
                        ) : (
                          <span className="text-[#b6bbaa]/50">Standaard (globaal)</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-[#b6bbaa] font-mono text-[10px]">
                        {new Date(u.created_at).toLocaleDateString("nl-NL")}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleViewUserDetails(u.id)}
                            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-2 py-1 text-[11px] font-semibold text-[#f3efdf] hover:border-[#f1ca53]"
                          >
                            Details
                          </button>
                          <button
                            type="button"
                            onClick={() => handleOpenStatusModal(u)}
                            className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-2 py-1 text-[11px] font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                          >
                            Status
                          </button>
                          <button
                            type="button"
                            onClick={() => handleOpenQuotaModal(u)}
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
      )}

      {/* ======================================================== */}
      {/* TAB 2: BETA CODES                                        */}
      {/* ======================================================== */}
      {activeTab === "beta" && (
        <section className="mt-6 space-y-6" aria-label="Bètacodes & Uitnodigingen">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <input
                type="text"
                value={betaSearch}
                onChange={(e) => setBetaSearch(e.target.value)}
                placeholder="Zoek code of label…"
                className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] placeholder:text-[#b6bbaa]/50 focus:border-[#f1ca53] focus:outline-none"
              />
              <select
                value={betaStatusFilter}
                onChange={(e) => setBetaStatusFilter(e.target.value)}
                aria-label="Filter op status"
                className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
              >
                <option value="">Alle statussen</option>
                <option value="active">Actief</option>
                <option value="exhausted">Opgebruikt</option>
                <option value="expired">Verlopen</option>
                <option value="revoked">Ingetrokken</option>
              </select>
              <button
                type="button"
                onClick={loadBetaCodes}
                className="rounded border border-[#f3efdf]/20 bg-[#20251f] px-3 py-2 font-bold text-[#f3efdf] hover:border-[#f1ca53]"
              >
                Vernieuwen
              </button>
            </div>
            <button
              type="button"
              onClick={() => setShowCreateBetaModal(true)}
              className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-3.5 py-2 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30"
            >
              + Nieuwe Bètacode
            </button>
          </div>

          {/* Beta Codes Table */}
          <div className="overflow-x-auto rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f]">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#f3efdf]/15 bg-[#171c16] font-mono text-[10px] uppercase text-[#b6bbaa]">
                <tr>
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Label</th>
                  <th className="px-4 py-3">Uitnodiging voor</th>
                  <th className="px-4 py-3">Gebruik</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Verloopt</th>
                  <th className="px-4 py-3 text-right">Actie</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f3efdf]/10">
                {betaLoading ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#b6bbaa]">
                      Bètacodes laden…
                    </td>
                  </tr>
                ) : betaCodes.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-[#b6bbaa]">
                      Geen bètacodes gevonden.
                    </td>
                  </tr>
                ) : (
                  betaCodes.map((code) => (
                    <tr key={code.id} className="hover:bg-[#1a1f19]/70">
                      <td className="px-4 py-3 font-mono font-bold text-[#f1ca53]">
                        {code.code}
                      </td>
                      <td className="px-4 py-3 text-[#f3efdf]">{code.label || "—"}</td>
                      <td className="px-4 py-3 text-[#b6bbaa]">{code.invitation_email || "Iedereen"}</td>
                      <td className="px-4 py-3 font-mono">
                        {code.used_count} / {code.max_uses}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded px-2 py-0.5 font-bold text-[10px] ${
                            code.status === "active"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-500/30"
                              : code.status === "revoked"
                              ? "bg-rose-950 text-rose-300 border border-rose-500/30"
                              : "bg-[#171c16] text-[#b6bbaa]"
                          }`}
                        >
                          {code.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono text-[10px] text-[#b6bbaa]">
                        {code.expires_at ? new Date(code.expires_at).toLocaleDateString("nl-NL") : "Onbeperkt"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {code.status === "active" && (
                          <button
                            type="button"
                            onClick={() => {
                              setRevokeTargetCode(code);
                              setRevokeReason("");
                              setRevokeError(null);
                            }}
                            className="rounded border border-[#eb6b5d]/30 bg-[#eb6b5d]/10 px-2 py-1 text-[11px] font-semibold text-[#ff9387] hover:bg-[#eb6b5d]/20"
                          >
                            Intrekken
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="text-xs text-[#b6bbaa]">Totaal: {betaTotal} codes</div>
        </section>
      )}

      {/* ======================================================== */}
      {/* TAB 3: QUOTA SETTINGS                                    */}
      {/* ======================================================== */}
      {activeTab === "quotas" && (
        <section className="mt-6 max-w-2xl space-y-6" aria-label="Quota-instellingen">
          <div className="rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-6">
            <h2 className="font-serif text-lg font-bold text-[#f3efdf]">
              Globale Scan-quota Limieten
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-[#b6bbaa]">
              Deze limieten bepalen het maximum aantal scans per dag en per uur voor gewone verzamelaars.
              Individuele accounts kunnen een specifieke overschrijving hebben.
            </p>

            <form onSubmit={handleUpdateGlobalQuota} className="mt-6 space-y-4">
              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Dagelijkse scanlimiet per gebruiker
                </label>
                <input
                  type="number"
                  min={1}
                  value={globalDailyLimit}
                  onChange={(e) => setGlobalDailyLimit(parseInt(e.target.value, 10) || 0)}
                  required
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-sm text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Uurlijkse scanlimiet per gebruiker
                </label>
                <input
                  type="number"
                  min={1}
                  value={globalHourlyLimit}
                  onChange={(e) => setGlobalHourlyLimit(parseInt(e.target.value, 10) || 0)}
                  required
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-sm text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Reden voor wijziging (verplicht voor auditlog)
                </label>
                <input
                  type="text"
                  value={globalQuotaReason}
                  onChange={(e) => setGlobalQuotaReason(e.target.value)}
                  placeholder="Bijv. Uitbreiding pilotfase capaciteit"
                  required
                  minLength={3}
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-sm text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              {globalQuotaError && (
                <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2.5 text-xs text-[#ff9387]">
                  {globalQuotaError}
                </div>
              )}

              {globalQuotaSuccess && (
                <div className="rounded border border-emerald-500/40 bg-emerald-950/40 p-2.5 text-xs text-emerald-300">
                  {globalQuotaSuccess}
                </div>
              )}

              <button
                type="submit"
                disabled={globalQuotaUpdating}
                className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-4 py-2.5 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30 disabled:opacity-50"
              >
                {globalQuotaUpdating ? "Opslaan…" : "Globale Quota Bijwerken"}
              </button>
            </form>

            {globalQuota?.updated_at && (
              <p className="mt-4 font-mono text-[10px] text-[#b6bbaa]/50">
                Laatst bijgewerkt op: {new Date(globalQuota.updated_at).toLocaleString("nl-NL")}
              </p>
            )}
          </div>
        </section>
      )}

      {/* ======================================================== */}
      {/* TAB 4: AUDIT LOGS                                        */}
      {/* ======================================================== */}
      {activeTab === "audit" && (
        <section className="mt-6 space-y-6" aria-label="Auditlogboek">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <select
                value={auditActionFilter}
                onChange={(e) => setAuditActionFilter(e.target.value)}
                aria-label="Filter op actie"
                className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
              >
                <option value="">Alle acties</option>
                <option value="user.status_change">user.status_change</option>
                <option value="user.quota_override">user.quota_override</option>
                <option value="quota.update_global">quota.update_global</option>
                <option value="beta.create_code">beta.create_code</option>
                <option value="beta.revoke_code">beta.revoke_code</option>
              </select>
              <button
                type="button"
                onClick={loadAuditLogs}
                className="rounded border border-[#f3efdf]/20 bg-[#20251f] px-3 py-2 font-bold text-[#f3efdf] hover:border-[#f1ca53]"
              >
                Vernieuwen
              </button>
            </div>
            <div className="text-xs text-[#b6bbaa]">Totaal geregistreerd: {auditTotal}</div>
          </div>

          <div className="overflow-x-auto rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f]">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#f3efdf]/15 bg-[#171c16] font-mono text-[10px] uppercase text-[#b6bbaa]">
                <tr>
                  <th className="px-4 py-3">Tijdstip</th>
                  <th className="px-4 py-3">Actie</th>
                  <th className="px-4 py-3">Beheerder</th>
                  <th className="px-4 py-3">Doelobject</th>
                  <th className="px-4 py-3">Metadata</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#f3efdf]/10">
                {auditLoading ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-[#b6bbaa]">
                      Auditlogboeken laden…
                    </td>
                  </tr>
                ) : auditLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-[#b6bbaa]">
                      Geen auditlogboeken gevonden.
                    </td>
                  </tr>
                ) : (
                  auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-[#1a1f19]/70">
                      <td className="px-4 py-3 font-mono text-[10px] text-[#b6bbaa]">
                        {new Date(log.created_at).toLocaleString("nl-NL")}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-[#171c16] px-2 py-0.5 font-mono text-[10px] text-[#f1ca53] border border-[#f1ca53]/20">
                          {log.action}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-bold text-[#f3efdf]">{log.actor_email || "Systeem"}</div>
                        {log.actor_id && (
                          <div className="font-mono text-[9px] text-[#b6bbaa]/50">{log.actor_id}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-[11px] text-[#b6bbaa]">
                        <span className="text-[#f3efdf]">{log.target_type}</span>: {log.target_id || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => setSelectedAuditLog(log)}
                          className="rounded border border-[#f3efdf]/20 bg-[#171c16] px-2 py-1 font-mono text-[10px] text-[#b6bbaa] hover:text-[#f3efdf]"
                        >
                          Bekijk details
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ======================================================== */}
      {/* TAB 5: ABUSE PROTECTION                                  */}
      {/* ======================================================== */}
      {activeTab === "abuse" && (
        <section className="mt-6 space-y-6" aria-label="Misbruikpreventiestatus">
          {abuseLoading ? (
            <div className="text-sm text-[#b6bbaa]">Misbruikpreventiestatus laden…</div>
          ) : abuseStatus ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-5">
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Cloudflare Turnstile
                </span>
                <div className="mt-2 flex items-center gap-2">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      abuseStatus.turnstile_enabled ? "bg-emerald-400" : "bg-rose-500"
                    }`}
                  />
                  <span className="font-serif text-lg font-bold text-[#f3efdf]">
                    {abuseStatus.turnstile_enabled ? "Actief & Ingeschakeld" : "Uitgeschakeld"}
                  </span>
                </div>
                <p className="mt-2 text-xs text-[#b6bbaa]">
                  Modus: Managed mode met server-side Siteverify verificatie en replay-bescherming.
                </p>
                <div className="mt-3 font-mono text-[10px] text-[#b6bbaa]/70 truncate">
                  Site Key: {abuseStatus.site_key}
                </div>
              </div>

              <div className="rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-5">
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Piekdetectie Drempel
                </span>
                <div className="mt-2 font-serif text-lg font-bold text-[#f3efdf]">
                  {abuseStatus.burst_threshold_anonymous} scans / 15 sec
                </div>
                <p className="mt-2 text-xs text-[#b6bbaa]">
                  Anonieme gebruikers die deze drempel overschrijden krijgen adaptief een Turnstile challenge.
                </p>
                <div className="mt-3 font-mono text-[10px] text-[#b6bbaa]/70">
                  Geauthenticeerde marge: {abuseStatus.burst_threshold_authenticated} scans / 15 sec
                </div>
              </div>

              <div className="rounded-[6px] border border-[#f3efdf]/15 bg-[#20251f] p-5">
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-[#b6bbaa]">
                  Harde Rate Limit Plafond
                </span>
                <div className="mt-2 font-serif text-lg font-bold text-[#f3efdf]">
                  {abuseStatus.hard_rate_limit} verzoeken / minuut
                </div>
                <p className="mt-2 text-xs text-[#b6bbaa]">
                  Onafhankelijk backend-plafond per IP-adres. Verzoeken boven deze limiet ontvangen HTTP 429.
                </p>
                <div className="mt-3 font-mono text-[10px] text-[#b6bbaa]/70">
                  Proxy: Alleen vertrouwde proxies gerespecteerd
                </div>
              </div>
            </div>
          ) : null}
        </section>
      )}

      {/* ======================================================== */}
      {/* MODAL: USER DETAILS                                      */}
      {/* ======================================================== */}
      {selectedUserDetails && (
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
                <h2 id="user-details-title" className="font-serif text-xl font-bold text-[#f3efdf]">
                  {selectedUserDetails.email}
                </h2>
                <div className="font-mono text-xs text-[#b6bbaa]/70">{selectedUserDetails.id}</div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedUserDetails(null)}
                className="flex h-8 w-8 items-center justify-center rounded border border-[#f3efdf]/20 text-xs text-[#b6bbaa] hover:text-[#f3efdf]"
              >
                ✕
              </button>
            </div>

            <div className="mt-6 grid grid-cols-3 gap-3">
              <div className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 text-center">
                <span className="font-mono text-[10px] uppercase text-[#b6bbaa]">Totaal Scans</span>
                <div className="font-serif text-xl font-bold text-[#f3efdf]">
                  {selectedUserDetails.scans_count}
                </div>
              </div>
              <div className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 text-center">
                <span className="font-mono text-[10px] uppercase text-[#b6bbaa]">Collectie</span>
                <div className="font-serif text-xl font-bold text-[#f3efdf]">
                  {selectedUserDetails.collection_items_count}
                </div>
              </div>
              <div className="rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 text-center">
                <span className="font-mono text-[10px] uppercase text-[#b6bbaa]">Actieve Sessies</span>
                <div className="font-serif text-xl font-bold text-[#f3efdf]">
                  {selectedUserDetails.active_sessions_count}
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
                    {selectedUserDetails.quota.effective_daily_limit} scans
                  </strong>
                </div>
                <div>
                  Uurlijkse limiet:{" "}
                  <strong className="text-[#f3efdf]">
                    {selectedUserDetails.quota.effective_hourly_limit} scans
                  </strong>
                </div>
                <div>
                  Aangepaste override:{" "}
                  <strong className="text-[#f3efdf]">
                    {selectedUserDetails.quota.has_override
                      ? `${selectedUserDetails.quota.user_override} scans`
                      : "Geen (standaard)"}
                  </strong>
                </div>
                <div>
                  Blokkade actief:{" "}
                  <strong className="text-[#f3efdf]">
                    {selectedUserDetails.quota.is_blocked_or_suspended ? "Ja" : "Nee"}
                  </strong>
                </div>
              </div>
            </div>

            {/* Recent audit events */}
            <div className="mt-6">
              <span className="font-mono text-[10px] font-bold uppercase text-[#b6bbaa]">
                Recente Beheerdersacties op dit account
              </span>
              {selectedUserDetails.recent_audit_events.length === 0 ? (
                <p className="mt-2 text-xs text-[#b6bbaa]/50">Geen recente beheerdersacties geregistreerd.</p>
              ) : (
                <div className="mt-2 space-y-2">
                  {selectedUserDetails.recent_audit_events.map((event) => (
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
      )}

      {/* ======================================================== */}
      {/* MODAL: UPDATE USER STATUS (CONFIRMATION FLOW)            */}
      {/* ======================================================== */}
      {statusTargetUser && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="status-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
        >
          <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
            <h2 id="status-modal-title" className="font-serif text-xl font-bold text-[#f3efdf]">
              Status Wijzigen: {statusTargetUser.email}
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-[#b6bbaa]">
              Schorsen of blokkeren leidt ertoe dat alle actieve browsersessies van deze gebruiker onmiddellijk
              worden beëindigd.
            </p>

            <form onSubmit={handleSubmitStatus} className="mt-5 space-y-4">
              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Nieuwe Accountstatus
                </label>
                <select
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value as "active" | "suspended" | "blocked")}
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                >
                  <option value="active">Actief (volledige toegang)</option>
                  <option value="suspended">Geschorst (tijdelijk geblokkeerd)</option>
                  <option value="blocked">Geblokkeerd (permanente uitsluiting)</option>
                </select>
              </div>

              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Reden voor statuswijziging (verplicht)
                </label>
                <textarea
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  placeholder="Bijv. Verdacht burst-patroon of verzoek van gebruiker…"
                  required
                  rows={3}
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              {statusError && (
                <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2 text-xs text-[#ff9387]">
                  {statusError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setStatusTargetUser(null)}
                  className="rounded border border-[#f3efdf]/20 px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                >
                  Annuleren
                </button>
                <button
                  type="submit"
                  disabled={statusUpdating}
                  className="rounded border border-[#c6372e] bg-[#c6372e] px-4 py-1.5 text-xs font-bold text-[#fffcf5] hover:brightness-110 disabled:opacity-50"
                >
                  {statusUpdating ? "Bezig…" : "Bevestigen & Toepassen"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL: UPDATE USER QUOTA                                 */}
      {/* ======================================================== */}
      {quotaTargetUser && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="quota-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
        >
          <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
            <h2 id="quota-modal-title" className="font-serif text-xl font-bold text-[#f3efdf]">
              Scan-quota: {quotaTargetUser.email}
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-[#b6bbaa]">
              Stel een individuele dagelijkse scanlimiet in voor deze gebruiker. Laat het veld leeg om terug te keren
              naar de globale limiet.
            </p>

            <form onSubmit={handleSubmitQuota} className="mt-5 space-y-4">
              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Dagelijkse scanlimiet override (of leeg voor globaal)
                </label>
                <input
                  type="number"
                  min={0}
                  value={userQuotaValue}
                  onChange={(e) => setUserQuotaValue(e.target.value)}
                  placeholder="Bijv. 250 (leeg = standaard)"
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Reden voor aanpassing (verplicht)
                </label>
                <input
                  type="text"
                  value={quotaReason}
                  onChange={(e) => setQuotaReason(e.target.value)}
                  placeholder="Bijv. Verzoek van reviewer / power user test…"
                  required
                  minLength={3}
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              {quotaError && (
                <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2 text-xs text-[#ff9387]">
                  {quotaError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setQuotaTargetUser(null)}
                  className="rounded border border-[#f3efdf]/20 px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                >
                  Annuleren
                </button>
                <button
                  type="submit"
                  disabled={quotaUpdating}
                  className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-4 py-1.5 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30 disabled:opacity-50"
                >
                  {quotaUpdating ? "Opslaan…" : "Quota Toepassen"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL: CREATE BETA CODE                                  */}
      {/* ======================================================== */}
      {showCreateBetaModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-beta-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
        >
          <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
            <h2 id="create-beta-modal-title" className="font-serif text-xl font-bold text-[#f3efdf]">
              Nieuwe Bètacode Aanmaken
            </h2>

            <form onSubmit={handleCreateBetaCode} className="mt-5 space-y-4">
              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Label / Omschrijving
                </label>
                <input
                  type="text"
                  value={newBetaLabel}
                  onChange={(e) => setNewBetaLabel(e.target.value)}
                  placeholder="Bijv. Early Tester Cohort #2"
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Gekoppeld E-mailadres (optioneel)
                </label>
                <input
                  type="email"
                  value={newBetaEmail}
                  onChange={(e) => setNewBetaEmail(e.target.value)}
                  placeholder="verzamelaar@voorbeeld.nl"
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                    Max. gebruik
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={newBetaMaxUses}
                    onChange={(e) => setNewBetaMaxUses(parseInt(e.target.value, 10) || 1)}
                    className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                    Geldigheid (dagen)
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={newBetaExpiresDays}
                    onChange={(e) => setNewBetaExpiresDays(parseInt(e.target.value, 10) || 30)}
                    className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                  />
                </div>
              </div>

              {createBetaError && (
                <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2 text-xs text-[#ff9387]">
                  {createBetaError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateBetaModal(false)}
                  className="rounded border border-[#f3efdf]/20 px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                >
                  Annuleren
                </button>
                <button
                  type="submit"
                  disabled={creatingBeta}
                  className="rounded border border-[#f1ca53] bg-[#f1ca53]/20 px-4 py-1.5 text-xs font-bold text-[#f1ca53] hover:bg-[#f1ca53]/30 disabled:opacity-50"
                >
                  {creatingBeta ? "Bezig…" : "Code Aanmaken"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL: REVOKE BETA CODE                                  */}
      {/* ======================================================== */}
      {revokeTargetCode && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="revoke-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
        >
          <div className="relative w-full max-w-md rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
            <h2 id="revoke-modal-title" className="font-serif text-xl font-bold text-[#f3efdf]">
              Bètacode Intrekken: {revokeTargetCode.code}
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-[#b6bbaa]">
              Deze code kan na intrekking niet meer worden verzilverd door verzamelaars.
            </p>

            <form onSubmit={handleRevokeBetaCode} className="mt-5 space-y-4">
              <div>
                <label className="block font-mono text-[10px] font-bold uppercase tracking-wider text-[#d8dacd]">
                  Reden voor intrekking (verplicht)
                </label>
                <input
                  type="text"
                  value={revokeReason}
                  onChange={(e) => setRevokeReason(e.target.value)}
                  placeholder="Bijv. Vroegtijdige sluiting actie…"
                  required
                  minLength={3}
                  className="mt-1 w-full rounded border border-[#f3efdf]/20 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] focus:border-[#f1ca53] focus:outline-none"
                />
              </div>

              {revokeError && (
                <div className="rounded border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2 text-xs text-[#ff9387]">
                  {revokeError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setRevokeTargetCode(null)}
                  className="rounded border border-[#f3efdf]/20 px-3 py-1.5 text-xs font-semibold text-[#b6bbaa] hover:text-[#f3efdf]"
                >
                  Annuleren
                </button>
                <button
                  type="submit"
                  disabled={revokingCode}
                  className="rounded border border-[#c6372e] bg-[#c6372e] px-4 py-1.5 text-xs font-bold text-[#fffcf5] hover:brightness-110 disabled:opacity-50"
                >
                  {revokingCode ? "Bezig…" : "Code Definitief Intrekken"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* MODAL: AUDIT LOG METADATA DETAIL                         */}
      {/* ======================================================== */}
      {selectedAuditLog && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="audit-detail-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm sm:p-6"
        >
          <div className="relative max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
            <div className="flex items-start justify-between border-b border-[#f3efdf]/15 pb-3">
              <div>
                <span className="font-mono text-[10px] font-bold uppercase text-[#f1ca53]">
                  Audit Detail
                </span>
                <h2 id="audit-detail-title" className="font-mono text-sm font-bold text-[#f3efdf]">
                  {selectedAuditLog.action}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedAuditLog(null)}
                className="flex h-7 w-7 items-center justify-center rounded border border-[#f3efdf]/20 text-xs text-[#b6bbaa] hover:text-[#f3efdf]"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-2 text-xs">
              <div>
                <span className="text-[#b6bbaa]">Doel: </span>
                <span className="font-mono text-[#f3efdf]">
                  {selectedAuditLog.target_type} ({selectedAuditLog.target_id || "geen"})
                </span>
              </div>
              <div>
                <span className="text-[#b6bbaa]">Uitgevoerd door: </span>
                <span className="font-mono text-[#f3efdf]">
                  {selectedAuditLog.actor_email || selectedAuditLog.actor_id || "Systeem"}
                </span>
              </div>
              <div>
                <span className="text-[#b6bbaa]">Tijdstip: </span>
                <span className="font-mono text-[#f3efdf]">
                  {new Date(selectedAuditLog.created_at).toLocaleString("nl-NL")}
                </span>
              </div>

              <div className="mt-4">
                <span className="font-mono text-[10px] font-bold uppercase text-[#b6bbaa]">
                  Geregistreerde Metadata
                </span>
                <pre className="mt-1.5 max-h-60 overflow-x-auto rounded border border-[#f3efdf]/10 bg-[#171c16] p-3 font-mono text-[11px] text-[#f3efdf]">
                  {selectedAuditLog.metadata_json
                    ? JSON.stringify(JSON.parse(selectedAuditLog.metadata_json), null, 2)
                    : "Geen metadata"}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
