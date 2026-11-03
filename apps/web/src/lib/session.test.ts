import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  ensureBrowserSession,
  refreshBrowserSession,
  resetBrowserSessionBootstrap,
  onUnauthorized,
  notifyUnauthorized,
  type BrowserSessionState,
} from "./session.ts";

describe("Browser Session Manager", () => {
  beforeEach(() => {
    (globalThis as any).window = globalThis;
    resetBrowserSessionBootstrap();
  });

  test("ensureBrowserSession single-flights concurrent calls", async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    const mockState: BrowserSessionState = {
      is_authenticated: false,
      user: null,
      session_id: "anon-session-123",
      session_type: "anonymous",
    };

    globalThis.fetch = async () => {
      callCount++;
      return new Response(JSON.stringify(mockState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    try {
      const [res1, res2, res3] = await Promise.all([
        ensureBrowserSession(),
        ensureBrowserSession(),
        ensureBrowserSession(),
      ]);

      assert.equal(callCount, 1, "Only one fetch call should be initiated");
      assert.equal(res1.session_id, "anon-session-123");
      assert.equal(res2.session_id, "anon-session-123");
      assert.equal(res3.session_id, "anon-session-123");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("refreshBrowserSession invalidates stale cache and fetches new state", async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    const anonState: BrowserSessionState = {
      is_authenticated: false,
      user: null,
      session_id: "anon-123",
      session_type: "anonymous",
    };
    const authState: BrowserSessionState = {
      is_authenticated: true,
      user: { id: "u-1", email: "test@example.com", role: "user" },
      session_id: "auth-456",
      session_type: "authenticated",
    };

    globalThis.fetch = async () => {
      callCount++;
      const data = callCount === 1 ? anonState : authState;
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    try {
      const initial = await ensureBrowserSession();
      assert.equal(initial.is_authenticated, false);
      assert.equal(callCount, 1);

      // ensureBrowserSession returns cached result if called again
      const cached = await ensureBrowserSession();
      assert.equal(cached.is_authenticated, false);
      assert.equal(callCount, 1);

      // refreshBrowserSession invalidates cache and triggers new fetch
      const refreshed = await refreshBrowserSession();
      assert.equal(refreshed.is_authenticated, true);
      assert.equal(refreshed.user?.email, "test@example.com");
      assert.equal(callCount, 2);

      // Subsequent ensureBrowserSession receives the refreshed authenticated state
      const nextEnsure = await ensureBrowserSession();
      assert.equal(nextEnsure.is_authenticated, true);
      assert.equal(callCount, 2);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("refreshBrowserSession single-flights concurrent refreshes", async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    const mockState: BrowserSessionState = {
      is_authenticated: true,
      user: { id: "u-1", email: "test@example.com", role: "user" },
      session_id: "auth-456",
      session_type: "authenticated",
    };

    globalThis.fetch = async () => {
      callCount++;
      await new Promise((resolve) => setTimeout(resolve, 5));
      return new Response(JSON.stringify(mockState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    try {
      const [first, second, third] = await Promise.all([
        refreshBrowserSession(),
        refreshBrowserSession(),
        refreshBrowserSession(),
      ]);
      assert.equal(callCount, 1);
      assert.equal(first.session_id, "auth-456");
      assert.equal(second.session_id, "auth-456");
      assert.equal(third.session_id, "auth-456");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("forced refresh prevents an older anonymous response from winning", async () => {
    const originalFetch = globalThis.fetch;
    let resolveAnonymous!: (response: Response) => void;
    let resolveAuthenticated!: (response: Response) => void;
    let callCount = 0;

    globalThis.fetch = () => {
      callCount++;
      return new Promise<Response>((resolve) => {
        if (callCount === 1) resolveAnonymous = resolve;
        else resolveAuthenticated = resolve;
      });
    };

    const anonymousState: BrowserSessionState = {
      is_authenticated: false,
      user: null,
      session_id: "anon-old",
      session_type: "anonymous",
    };
    const authenticatedState: BrowserSessionState = {
      is_authenticated: true,
      user: { id: "u-2", email: "fresh@example.com", role: "user" },
      session_id: "auth-new",
      session_type: "authenticated",
    };

    try {
      const oldRequest = ensureBrowserSession();
      const freshRequest = refreshBrowserSession({ force: true });

      resolveAuthenticated(
        new Response(JSON.stringify(authenticatedState), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
      const freshState = await freshRequest;
      assert.equal(freshState.session_id, "auth-new");

      resolveAnonymous(
        new Response(JSON.stringify(anonymousState), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );
      await assert.rejects(oldRequest, {
        name: "SessionRequestSupersededError",
      });

      const cachedState = await ensureBrowserSession();
      assert.equal(cachedState.session_id, "auth-new");
      assert.equal(callCount, 2);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("resetBrowserSessionBootstrap clears cache", async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    const mockState: BrowserSessionState = {
      is_authenticated: false,
      user: null,
      session_id: "anon-123",
      session_type: "anonymous",
    };

    globalThis.fetch = async () => {
      callCount++;
      return new Response(JSON.stringify(mockState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    try {
      await ensureBrowserSession();
      assert.equal(callCount, 1);

      resetBrowserSessionBootstrap();

      await ensureBrowserSession();
      assert.equal(callCount, 2);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("onUnauthorized and notifyUnauthorized notify registered listeners", () => {
    let calledCount = 0;
    const unsubscribe = onUnauthorized(() => {
      calledCount++;
    });

    notifyUnauthorized();
    assert.equal(calledCount, 1);

    notifyUnauthorized();
    assert.equal(calledCount, 2);

    unsubscribe();
    notifyUnauthorized();
    assert.equal(calledCount, 2);
  });
});
