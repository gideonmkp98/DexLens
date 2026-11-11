import { describe, it, before, after, mock } from "node:test";
import assert from "node:assert/strict";
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
  AdminApiError,
} from "./admin.ts";

describe("Admin API Client", () => {
  const originalFetch = globalThis.fetch;

  after(() => {
    globalThis.fetch = originalFetch;
  });

  it("listAdminUsers formats query parameters and parses response", async () => {
    let capturedUrl = "";
    let capturedHeaders: Record<string, string> = {};

    globalThis.fetch = (async (
      url: string | URL | Request,
      init?: RequestInit
    ) => {
      capturedUrl = String(url);
      capturedHeaders = (init?.headers || {}) as Record<string, string>;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items: [
            {
              id: "usr_1",
              email: "admin@example.com",
              role: "admin",
              status: "active",
              is_active: true,
              verification_status: "verified",
              scan_quota_override: null,
              created_at: "2026-11-11T12:00:00Z",
              updated_at: "2026-11-11T12:00:00Z",
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      } as Response;
    }) as typeof fetch;

    const res = await listAdminUsers({
      q: "admin",
      status: "active",
      role: "admin",
      verification_status: "verified",
      limit: 20,
      offset: 0,
    });

    assert.ok(capturedUrl.includes("/api/v1/admin/users"));
    assert.ok(capturedUrl.includes("q=admin"));
    assert.ok(capturedUrl.includes("status=active"));
    assert.ok(capturedUrl.includes("role=admin"));
    assert.ok(capturedUrl.includes("verification_status=verified"));
    assert.equal(res.items.length, 1);
    assert.equal(res.items[0]?.email, "admin@example.com");
  });

  it("getAdminUserDetails fetches user dossier", async () => {
    globalThis.fetch = (async () => {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "usr_2",
          email: "user@example.com",
          role: "user",
          status: "active",
          is_active: true,
          verification_status: "unverified",
          scan_quota_override: 150,
          created_at: "2026-11-11T12:00:00Z",
          updated_at: "2026-11-11T12:00:00Z",
          scans_count: 42,
          active_sessions_count: 2,
          collection_items_count: 10,
          quota: {
            effective_daily_limit: 150,
            effective_hourly_limit: 30,
            has_override: true,
            user_override: 150,
            global_daily_limit: 100,
            global_hourly_limit: 30,
            is_blocked_or_suspended: false,
          },
          recent_audit_events: [],
        }),
      } as Response;
    }) as typeof fetch;

    const details = await getAdminUserDetails("usr_2");
    assert.equal(details.id, "usr_2");
    assert.equal(details.scans_count, 42);
    assert.equal(details.quota.effective_daily_limit, 150);
  });

  it("updateAdminUserStatus submits status and reason payload", async () => {
    let capturedBody = "";
    globalThis.fetch = (async (
      url: string | URL | Request,
      init?: RequestInit
    ) => {
      capturedBody = String(init?.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "usr_2",
          email: "user@example.com",
          role: "user",
          status: "suspended",
          is_active: false,
          verification_status: "verified",
          scan_quota_override: null,
          created_at: "2026-11-11T12:00:00Z",
          updated_at: "2026-11-11T12:00:00Z",
        }),
      } as Response;
    }) as typeof fetch;

    const res = await updateAdminUserStatus(
      "usr_2",
      "suspended",
      "Spam activity detected"
    );
    const parsed = JSON.parse(capturedBody);
    assert.equal(parsed.status, "suspended");
    assert.equal(parsed.reason, "Spam activity detected");
    assert.equal(res.status, "suspended");
  });

  it("updateAdminUserQuota submits scan_quota_override", async () => {
    let capturedBody = "";
    globalThis.fetch = (async (
      url: string | URL | Request,
      init?: RequestInit
    ) => {
      capturedBody = String(init?.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: "usr_2",
          email: "user@example.com",
          role: "user",
          status: "active",
          is_active: true,
          verification_status: "verified",
          scan_quota_override: 500,
          created_at: "2026-11-11T12:00:00Z",
          updated_at: "2026-11-11T12:00:00Z",
        }),
      } as Response;
    }) as typeof fetch;

    const res = await updateAdminUserQuota("usr_2", 500, "Approved VIP quota");
    const parsed = JSON.parse(capturedBody);
    assert.equal(parsed.scan_quota_override, 500);
    assert.equal(parsed.reason, "Approved VIP quota");
    assert.equal(res.scan_quota_override, 500);
  });

  it("getGlobalQuota and updateGlobalQuota handle global limits", async () => {
    globalThis.fetch = (async (
      url: string | URL | Request,
      init?: RequestInit
    ) => {
      if (init?.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        return {
          ok: true,
          status: 200,
          json: async () => ({
            daily_scan_limit: body.daily_scan_limit,
            hourly_scan_limit: body.hourly_scan_limit,
            updated_at: "2026-11-11T14:00:00Z",
          }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          daily_scan_limit: 100,
          hourly_scan_limit: 30,
          updated_at: "2026-11-11T12:00:00Z",
        }),
      } as Response;
    }) as typeof fetch;

    const current = await getGlobalQuota();
    assert.equal(current.daily_scan_limit, 100);

    const updated = await updateGlobalQuota(
      250,
      50,
      "Increased global pilot limit"
    );
    assert.equal(updated.daily_scan_limit, 250);
    assert.equal(updated.hourly_scan_limit, 50);
  });

  it("listBetaCodes, createBetaCode, revokeBetaCode work properly", async () => {
    globalThis.fetch = (async (
      url: string | URL | Request,
      init?: RequestInit
    ) => {
      const urlStr = String(url);
      if (urlStr.includes("/revoke")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "code_1",
            code: "BETA-REVOKED",
            code_prefix: "BETA-",
            label: "Test Code",
            invitation_email: null,
            max_uses: 1,
            used_count: 0,
            status: "revoked",
            expires_at: null,
            created_at: "2026-11-11T12:00:00Z",
            created_by_user_id: "usr_1",
          }),
        } as Response;
      } else if (init?.method === "POST") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "code_1",
            code: "BETA-NEWCODE",
            code_prefix: "BETA-",
            label: "Test Code",
            invitation_email: null,
            max_uses: 5,
            used_count: 0,
            status: "active",
            expires_at: null,
            created_at: "2026-11-11T12:00:00Z",
            created_by_user_id: "usr_1",
          }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items: [],
          total: 0,
          limit: 30,
          offset: 0,
        }),
      } as Response;
    }) as typeof fetch;

    const list = await listBetaCodes();
    assert.equal(list.total, 0);

    const created = await createBetaCode({ max_uses: 5 });
    assert.equal(created.code, "BETA-NEWCODE");
    assert.equal(created.status, "active");

    const revoked = await revokeBetaCode("code_1", "Test revoke");
    assert.equal(revoked.status, "revoked");
  });

  it("listAuditLogs and getAbuseStatus parse responses correctly", async () => {
    globalThis.fetch = (async (url: string | URL | Request) => {
      const urlStr = String(url);
      if (urlStr.includes("/abuse/status")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            turnstile_enabled: true,
            site_key: "0x4AAAAAAtest",
            burst_threshold_anonymous: 5,
            burst_threshold_authenticated: 20,
            hard_rate_limit: 30,
          }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items: [
            {
              id: "aud_1",
              actor_id: "usr_1",
              actor_email: "admin@example.com",
              action: "user.status_change",
              target_type: "user",
              target_id: "usr_2",
              metadata_json: JSON.stringify({
                old_status: "active",
                new_status: "suspended",
              }),
              created_at: "2026-11-11T12:00:00Z",
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      } as Response;
    }) as typeof fetch;

    const logs = await listAuditLogs({ action: "user.status_change" });
    assert.equal(logs.items.length, 1);
    assert.equal(logs.items[0]?.action, "user.status_change");

    const abuse = await getAbuseStatus();
    assert.equal(abuse.turnstile_enabled, true);
    assert.equal(abuse.burst_threshold_anonymous, 5);
  });

  it("throws AdminApiError on 403 Forbidden", async () => {
    globalThis.fetch = (async () => {
      return {
        ok: false,
        status: 403,
        json: async () => ({
          detail: {
            code: "FORBIDDEN",
            message: "Administrator role required for this action.",
          },
        }),
      } as Response;
    }) as typeof fetch;

    await assert.rejects(
      async () => {
        await listAdminUsers();
      },
      (err: unknown) => {
        assert.ok(err instanceof AdminApiError);
        assert.equal(err.status, 403);
        assert.equal(err.code, "FORBIDDEN");
        assert.equal(
          err.message,
          "Administrator role required for this action."
        );
        return true;
      }
    );
  });
});
