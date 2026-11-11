/**
 * Safe invitation token handling & verification utility.
 * Strictly enforces:
 * - Zero token leakage into analytics, error tracking, console logs, or referrer headers.
 * - Fragment-first token extraction with searchParams fallback.
 * - History cleanup: strips sensitive tokens from the browser URL immediately upon extraction.
 * - Dutch error classification for non-enumerating invitation validation responses.
 */

export interface ValidateInvitationResponse {
  valid: boolean;
  masked_email?: string | null;
  message?: string | null;
}

export type InvitationInvalidReason =
  | "expired"
  | "revoked"
  | "already_used"
  | "invalid";

/**
 * Extract the invitation token safely from URL fragment (#token=... or #invite=...)
 * with fallback to query search parameters (?token=... or ?invite=...).
 */
export function extractInvitationToken(
  hash: string,
  search: string
): string | null {
  if (hash) {
    const cleanHash = hash.replace(/^[#?]/, "");
    const hashParams = new URLSearchParams(cleanHash);
    const tokenFromHash = hashParams.get("token") || hashParams.get("invite");
    if (tokenFromHash && tokenFromHash.trim().length > 0) {
      return tokenFromHash.trim();
    }
  }

  if (search) {
    const cleanSearch = search.replace(/^[?]/, "");
    const searchParams = new URLSearchParams(cleanSearch);
    const tokenFromSearch =
      searchParams.get("token") || searchParams.get("invite");
    if (tokenFromSearch && tokenFromSearch.trim().length > 0) {
      return tokenFromSearch.trim();
    }
  }

  return null;
}

/**
 * Clean up the URL by stripping the fragment and invitation token query parameters
 * so the token is not persisted in browser history or sent in referrer headers.
 */
export function sanitizeInvitationUrl(currentUrl: string): string {
  try {
    const url = new URL(currentUrl, "http://localhost");
    url.hash = "";
    url.searchParams.delete("token");
    url.searchParams.delete("invite");
    const search = url.search;
    return `${url.pathname}${search && search !== "?" ? search : ""}`;
  } catch {
    return "/invite";
  }
}

/**
 * Classify backend validation message into one of the distinct Dutch user-facing states.
 */
export function classifyInvitationError(
  message?: string | null
): InvitationInvalidReason {
  if (!message) return "invalid";
  const lower = message.toLowerCase();
  if (lower.includes("verlopen") || lower.includes("expired")) {
    return "expired";
  }
  if (lower.includes("ingetrokken") || lower.includes("revoked")) {
    return "revoked";
  }
  if (
    lower.includes("al gebruikt") ||
    lower.includes("already") ||
    lower.includes("geaccepteerd")
  ) {
    return "already_used";
  }
  return "invalid";
}

/**
 * Validate an invitation token with the non-enumerating backend endpoint.
 * Never logs or persists the raw token.
 */
export async function validateInvitation(
  token: string
): Promise<ValidateInvitationResponse> {
  const response = await fetch("/api/v1/auth/validate-invitation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });

  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    const message =
      errJson.detail?.message ||
      errJson.detail ||
      errJson.message ||
      "Uitnodigingstoken kon niet worden geverifieerd.";
    return {
      valid: false,
      message: typeof message === "string" ? message : "Ongeldige uitnodiging.",
    };
  }

  return response.json();
}
