import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  extractInvitationToken,
  sanitizeInvitationUrl,
  classifyInvitationError,
  validateInvitation,
} from "./invitation.ts";

describe("Invitation Utilities", () => {
  describe("extractInvitationToken", () => {
    test("extracts token from URL hash #token=xyz", () => {
      const token = extractInvitationToken("#token=my-secret-token", "");
      assert.equal(token, "my-secret-token");
    });

    test("extracts token from URL hash #invite=xyz", () => {
      const token = extractInvitationToken("#invite=invite-token-123", "");
      assert.equal(token, "invite-token-123");
    });

    test("falls back to searchParams when hash is empty", () => {
      const token = extractInvitationToken("", "?token=search-token-456");
      assert.equal(token, "search-token-456");
    });

    test("falls back to ?invite= in searchParams", () => {
      const token = extractInvitationToken("", "?invite=search-invite-789");
      assert.equal(token, "search-invite-789");
    });

    test("prioritizes hash over searchParams to avoid referrer leaks", () => {
      const token = extractInvitationToken(
        "#token=hash-priority",
        "?token=query-token"
      );
      assert.equal(token, "hash-priority");
    });

    test("returns null if no token is found", () => {
      assert.equal(extractInvitationToken("", ""), null);
      assert.equal(extractInvitationToken("#other=123", "?foo=bar"), null);
      assert.equal(extractInvitationToken("#token=", "?token="), null);
    });
  });

  describe("sanitizeInvitationUrl", () => {
    test("strips token from fragment", () => {
      const clean = sanitizeInvitationUrl(
        "https://example.com/invite#token=secret"
      );
      assert.equal(clean, "/invite");
    });

    test("strips token from query params", () => {
      const clean = sanitizeInvitationUrl(
        "https://example.com/invite?token=secret"
      );
      assert.equal(clean, "/invite");
    });

    test("strips both fragment and query token while preserving other params", () => {
      const clean = sanitizeInvitationUrl(
        "https://example.com/invite?ref=email&token=secret#invite=frag-token"
      );
      assert.equal(clean, "/invite?ref=email");
    });
  });

  describe("classifyInvitationError", () => {
    test("classifies expired invitation messages", () => {
      assert.equal(
        classifyInvitationError("Deze uitnodiging is verlopen"),
        "expired"
      );
      assert.equal(
        classifyInvitationError("Invitation has expired"),
        "expired"
      );
    });

    test("classifies revoked invitation messages", () => {
      assert.equal(
        classifyInvitationError("Deze uitnodiging is ingetrokken"),
        "revoked"
      );
      assert.equal(classifyInvitationError("Invitation revoked"), "revoked");
    });

    test("classifies already accepted / used messages", () => {
      assert.equal(
        classifyInvitationError("Deze uitnodiging is al gebruikt"),
        "already_used"
      );
      assert.equal(
        classifyInvitationError("Uitnodiging is al geaccepteerd"),
        "already_used"
      );
    });

    test("falls back to invalid for unknown or empty messages", () => {
      assert.equal(classifyInvitationError(null), "invalid");
      assert.equal(classifyInvitationError(""), "invalid");
      assert.equal(
        classifyInvitationError(
          "Uitnodigingstoken is ongeldig of niet gevonden"
        ),
        "invalid"
      );
    });
  });

  describe("validateInvitation", () => {
    test("sends POST request and parses valid response", async () => {
      const originalFetch = globalThis.fetch;
      globalThis.fetch = async (url, init) => {
        assert.equal(url, "/api/v1/auth/validate-invitation");
        assert.equal(init?.method, "POST");
        const body = JSON.parse(init?.body as string);
        assert.equal(body.token, "valid-token");
        return new Response(
          JSON.stringify({
            valid: true,
            masked_email: "j***@example.com",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      try {
        const result = await validateInvitation("valid-token");
        assert.equal(result.valid, true);
        assert.equal(result.masked_email, "j***@example.com");
      } finally {
        globalThis.fetch = originalFetch;
      }
    });

    test("handles non-ok response safely", async () => {
      const originalFetch = globalThis.fetch;
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({
            detail: { message: "Deze uitnodiging is verlopen" },
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      };

      try {
        const result = await validateInvitation("expired-token");
        assert.equal(result.valid, false);
        assert.equal(result.message, "Deze uitnodiging is verlopen");
      } finally {
        globalThis.fetch = originalFetch;
      }
    });
  });
});
