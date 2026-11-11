/**
 * DexLens Administration and Abuse Protection API Client
 * Provides typed functions for managing users, quotas, beta codes,
 * audit trails, and reviewing abuse protection status.
 */

export interface AdminUserItem {
  id: string;
  email: string;
  role: string;
  status: "active" | "suspended" | "blocked" | string;
  is_active: boolean;
  verification_status: "verified" | "unverified" | "pending" | string;
  scan_quota_override: number | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminUserDetailsResponse {
  id: string;
  email: string;
  role: string;
  status: "active" | "suspended" | "blocked" | string;
  is_active: boolean;
  verification_status: "verified" | "unverified" | "pending" | string;
  scan_quota_override: number | null;
  created_at: string;
  updated_at: string;
  scans_count: number;
  active_sessions_count: number;
  collection_items_count: number;
  quota: {
    effective_daily_limit: number;
    effective_hourly_limit: number;
    has_override: boolean;
    user_override: number | null;
    global_daily_limit: number;
    global_hourly_limit: number;
    is_blocked_or_suspended: boolean;
  };
  recent_audit_events: Array<{
    id: string;
    action: string;
    actor_id: string | null;
    created_at: string;
    metadata: Record<string, unknown> | null;
  }>;
}

export interface GlobalQuotaResponse {
  daily_scan_limit: number;
  hourly_scan_limit: number;
  updated_at: string | null;
}

export interface BetaCodeResponse {
  id: string;
  code: string;
  code_prefix: string;
  label: string | null;
  invitation_email: string | null;
  max_uses: number;
  used_count: number;
  status: "active" | "exhausted" | "expired" | "revoked" | string;
  expires_at: string | null;
  created_at: string;
  created_by_user_id: string | null;
}

export interface BetaCodeListResponse {
  items: BetaCodeResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditLogResponse {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  metadata_json: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface AbuseStatusResponse {
  turnstile_enabled: boolean;
  site_key: string;
  burst_threshold_anonymous: number;
  burst_threshold_authenticated: number;
  hard_rate_limit: number;
}

export class AdminApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
    this.code = code;
  }
}

async function handleAdminResponse<T>(
  res: Response,
  defaultMessage: string
): Promise<T> {
  if (res.ok) {
    return (await res.json()) as T;
  }

  let errorMessage = `${defaultMessage} (HTTP ${res.status})`;
  let errorCode: string | undefined;

  try {
    const errorJson = await res.json();
    if (errorJson?.detail) {
      if (typeof errorJson.detail === "string") {
        errorMessage = errorJson.detail;
      } else if (
        typeof errorJson.detail === "object" &&
        errorJson.detail.message
      ) {
        errorMessage = errorJson.detail.message;
        errorCode = errorJson.detail.code;
      }
    } else if (errorJson?.message) {
      errorMessage = errorJson.message;
      errorCode = errorJson.code;
    }
  } catch {
    // Non-JSON error payload
  }

  throw new AdminApiError(errorMessage, res.status, errorCode);
}

const ADMIN_API_BASE = "/api/v1/admin";

/**
 * Fetch paginated users with optional search and filters.
 */
export async function listAdminUsers(params?: {
  q?: string;
  status?: string;
  role?: string;
  verification_status?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUserListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.q) searchParams.set("q", params.q);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.role) searchParams.set("role", params.role);
  if (params?.verification_status)
    searchParams.set("verification_status", params.verification_status);
  if (params?.limit !== undefined)
    searchParams.set("limit", params.limit.toString());
  if (params?.offset !== undefined)
    searchParams.set("offset", params.offset.toString());

  const query = searchParams.toString();
  const url = `${ADMIN_API_BASE}/users${query ? `?${query}` : ""}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
  });

  return handleAdminResponse<AdminUserListResponse>(
    res,
    "Ophalen van gebruikers mislukt"
  );
}

/**
 * Fetch detailed user record including scan counts, active sessions, and recent audit logs.
 */
export async function getAdminUserDetails(
  userId: string
): Promise<AdminUserDetailsResponse> {
  const url = `${ADMIN_API_BASE}/users/${encodeURIComponent(userId)}`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
  });

  return handleAdminResponse<AdminUserDetailsResponse>(
    res,
    "Ophalen van gebruikersdetails mislukt"
  );
}

/**
 * Update user status (active, suspended, blocked) with mandatory audit reason.
 * Changing to suspended/blocked terminates all active sessions immediately.
 */
export async function updateAdminUserStatus(
  userId: string,
  status: "active" | "suspended" | "blocked",
  reason: string
): Promise<AdminUserItem> {
  const url = `${ADMIN_API_BASE}/users/${encodeURIComponent(userId)}/status`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ status, reason }),
  });

  return handleAdminResponse<AdminUserItem>(
    res,
    "Bijwerken van gebruikersstatus mislukt"
  );
}

/**
 * Update user custom scan quota override. Pass null to reset to global default.
 */
export async function updateAdminUserQuota(
  userId: string,
  scan_quota_override: number | null,
  reason: string
): Promise<AdminUserItem> {
  const url = `${ADMIN_API_BASE}/users/${encodeURIComponent(userId)}/quota`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ scan_quota_override, reason }),
  });

  return handleAdminResponse<AdminUserItem>(
    res,
    "Bijwerken van gebruikersquota mislukt"
  );
}

/**
 * Fetch the global scan quota limits.
 */
export async function getGlobalQuota(): Promise<GlobalQuotaResponse> {
  const url = `${ADMIN_API_BASE}/settings/quota`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
  });

  return handleAdminResponse<GlobalQuotaResponse>(
    res,
    "Ophalen van globale quota mislukt"
  );
}

/**
 * Update global scan quota limits with confirmation reason.
 */
export async function updateGlobalQuota(
  daily_scan_limit: number,
  hourly_scan_limit: number,
  reason: string
): Promise<GlobalQuotaResponse> {
  const url = `${ADMIN_API_BASE}/settings/quota`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ daily_scan_limit, hourly_scan_limit, reason }),
  });

  return handleAdminResponse<GlobalQuotaResponse>(
    res,
    "Bijwerken van globale quota mislukt"
  );
}

/**
 * List beta access codes with optional filtering.
 */
export async function listBetaCodes(params?: {
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<BetaCodeListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.search) searchParams.set("search", params.search);
  if (params?.limit !== undefined)
    searchParams.set("limit", params.limit.toString());
  if (params?.offset !== undefined)
    searchParams.set("offset", params.offset.toString());

  const query = searchParams.toString();
  const url = `${ADMIN_API_BASE}/beta/codes${query ? `?${query}` : ""}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
  });

  return handleAdminResponse<BetaCodeListResponse>(
    res,
    "Ophalen van bètacodes mislukt"
  );
}

/**
 * Create a new beta access code or personalized invitation.
 */
export async function createBetaCode(payload: {
  code?: string;
  label?: string;
  invitation_email?: string;
  max_uses?: number;
  expires_days?: number;
}): Promise<BetaCodeResponse> {
  const url = `${ADMIN_API_BASE}/beta/codes`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    credentials: "include",
    body: JSON.stringify(payload),
  });

  return handleAdminResponse<BetaCodeResponse>(
    res,
    "Aanmaken van bètacode mislukt"
  );
}

/**
 * Revoke an active beta access code.
 */
export async function revokeBetaCode(
  codeId: string,
  reason: string
): Promise<BetaCodeResponse> {
  const url = `${ADMIN_API_BASE}/beta/codes/${encodeURIComponent(codeId)}/revoke`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ reason }),
  });

  return handleAdminResponse<BetaCodeResponse>(
    res,
    "Intrekken van bètacode mislukt"
  );
}

/**
 * List append-only audit trail logs with filtering.
 */
export async function listAuditLogs(params?: {
  action?: string;
  target_type?: string;
  target_id?: string;
  actor_id?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditLogListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.action) searchParams.set("action", params.action);
  if (params?.target_type) searchParams.set("target_type", params.target_type);
  if (params?.target_id) searchParams.set("target_id", params.target_id);
  if (params?.actor_id) searchParams.set("actor_id", params.actor_id);
  if (params?.limit !== undefined)
    searchParams.set("limit", params.limit.toString());
  if (params?.offset !== undefined)
    searchParams.set("offset", params.offset.toString());

  const query = searchParams.toString();
  const url = `${ADMIN_API_BASE}/audit-logs${query ? `?${query}` : ""}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
  });

  return handleAdminResponse<AuditLogListResponse>(
    res,
    "Ophalen van auditlogboeken mislukt"
  );
}

/**
 * Retrieve active configuration for abuse protection and rate limits.
 */
export async function getAbuseStatus(): Promise<AbuseStatusResponse> {
  const url = `${ADMIN_API_BASE}/abuse/status`;
  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    cache: "no-store",
  });

  return handleAdminResponse<AbuseStatusResponse>(
    res,
    "Ophalen van misbruikpreventiestatus mislukt"
  );
}
