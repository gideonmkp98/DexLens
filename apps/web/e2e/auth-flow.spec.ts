import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

async function resetTestDatabaseSafely(request: APIRequestContext) {
  const resetRes = await request.post("/api/v1/testing/reset");
  if (!resetRes.ok()) {
    const body = await resetRes.text();
    throw new Error(
      `Failed to reset test database (status ${resetRes.status()}): ${body}`
    );
  }
}

test.describe("Authentication State & Lifecycle Regression Suite", () => {
  test.beforeEach(async ({ request }) => {
    await resetTestDatabaseSafely(request);
  });

  test("1. Anonymous visitor initial load displays Inloggen button without stale auth", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await expect(loginBtn).toBeVisible({ timeout: 5000 });

    const meRes = await request.get("/api/v1/auth/me");
    expect(meRes.status()).toBe(200);
    const meData = await meRes.json();
    expect(meData.is_authenticated).toBe(false);
    expect(meData.user).toBeNull();
  });

  test("2. Registration immediately transitions UI to authenticated state and persists reload", async ({
    page,
  }) => {
    const testEmail = `collector_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    // Click Inloggen to open modal
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await expect(loginBtn).toBeVisible();
    await loginBtn.click();

    // Modal is open
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();

    // Switch to Register tab
    const registerTab = modal.getByRole("button", { name: "Registreren" });
    await registerTab.click();

    // Fill form
    await modal.locator("#auth-email").fill(testEmail);
    await modal.locator("#auth-password").fill(testPassword);

    // Submit
    await modal.locator('button[type="submit"]').click();

    // Modal closes only after auth updates
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    // Inloggen button must be gone
    await expect(loginBtn).not.toBeVisible();

    // Authenticated state (Uitloggen and email badge) must appear immediately
    const logoutBtn = page.getByRole("button", { name: "Uitloggen" });
    await expect(logoutBtn).toBeVisible({ timeout: 5000 });
    await expect(page.locator(`[title*="${testEmail}"]`).first()).toBeVisible();

    // Verify /api/v1/auth/me via page context
    const meRes = await page.evaluate(async () => {
      const res = await fetch("/api/v1/auth/me", { credentials: "include" });
      return res.json();
    });
    expect(meRes.is_authenticated).toBe(true);
    expect(meRes.user?.email).toBe(testEmail);

    // Verify state persists across reload
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("button", { name: "Uitloggen" })).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: "Inloggen" })
    ).not.toBeVisible();
  });

  test("3. Logout invalidates session and updates header without full reload", async ({
    page,
  }) => {
    const testEmail = `logout_user_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    // Register first
    await page.goto("/");
    await page.getByRole("button", { name: "Inloggen" }).click();
    const modal = page.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();
    await modal.locator("#auth-email").fill(testEmail);
    await modal.locator("#auth-password").fill(testPassword);
    await modal.locator('button[type="submit"]').click();
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    const logoutBtn = page.getByRole("button", { name: "Uitloggen" });
    await expect(logoutBtn).toBeVisible();

    // Click Logout
    await logoutBtn.click();

    // Header immediately displays Inloggen without page reload
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await expect(loginBtn).toBeVisible({ timeout: 5000 });
    await expect(logoutBtn).not.toBeVisible();

    // Verify /auth/me returns anonymous
    const meRes = await page.evaluate(async () => {
      const res = await fetch("/api/v1/auth/me", { credentials: "include" });
      return res.json();
    });
    expect(meRes.is_authenticated).toBe(false);
    expect(meRes.user).toBeNull();

    // Reload confirms unauthenticated state remains intact
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("button", { name: "Inloggen" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Uitloggen" })
    ).not.toBeVisible();
  });

  test("4. Login with registered account updates header immediately and survives navigation", async ({
    page,
  }) => {
    const testEmail = `login_nav_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    // Register account via API first
    const regRes = await page.request.post("/api/v1/auth/register", {
      data: { email: testEmail, password: testPassword },
    });
    expect(regRes.status()).toBe(201);

    // Clear cookies so browser starts logged out
    await page.context().clearCookies();

    // Open home page
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await expect(loginBtn).toBeVisible();

    // Click Inloggen
    await loginBtn.click();
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();

    // Fill login credentials
    await modal.locator("#auth-email").fill(testEmail);
    await modal.locator("#auth-password").fill(testPassword);
    await modal.locator('button[type="submit"]').click();

    // Modal closes
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    // Header updates immediately
    const logoutBtn = page.getByRole("button", { name: "Uitloggen" });
    await expect(logoutBtn).toBeVisible({ timeout: 5000 });
    await expect(loginBtn).not.toBeVisible();

    // Navigate to /sets
    await page
      .getByRole("navigation", { name: "Hoofdnavigatie" })
      .getByRole("link", { name: "Sets" })
      .click();
    await page.waitForURL("**/sets");
    await expect(page.getByRole("button", { name: "Uitloggen" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Inloggen" })
    ).not.toBeVisible();

    // Reload on /sets
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("button", { name: "Uitloggen" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Inloggen" })
    ).not.toBeVisible();
  });

  test("5. Authenticated initial page load never flashes Inloggen button", async ({
    page,
  }) => {
    const testEmail = `noflash_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    // Register via API to set authenticated cookie
    const regRes = await page.request.post("/api/v1/auth/register", {
      data: { email: testEmail, password: testPassword },
    });
    expect(regRes.status()).toBe(201);

    // Track whether "Inloggen" button ever becomes visible during page load
    let flashedLoginButton = false;

    // Delay /api/v1/auth/me response by 500ms so initial loading state is observable
    await page.route("**/api/v1/auth/me", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.continue();
    });

    // Check DOM periodically as page loads
    const checkInterval = setInterval(async () => {
      try {
        const isLoginVisible = await page
          .getByRole("button", { name: "Inloggen" })
          .isVisible();
        if (isLoginVisible) {
          flashedLoginButton = true;
        }
      } catch {
        // Ignored during page navigation
      }
    }, 50);

    try {
      await page.goto("/");

      // While auth is resolving, the skeleton should be present
      const skeleton = page.locator(".header-auth-skeleton");
      // Either skeleton is visible or it quickly resolved to Uitloggen
      const logoutBtn = page.getByRole("button", { name: "Uitloggen" });
      await expect(logoutBtn).toBeVisible({ timeout: 10000 });

      // Inloggen must NEVER have flashed
      expect(flashedLoginButton).toBe(false);
      await expect(
        page.getByRole("button", { name: "Inloggen" })
      ).not.toBeVisible();
    } finally {
      clearInterval(checkInterval);
    }
  });

  test("6. Anonymous collection data is claimed upon user registration", async ({
    page,
  }) => {
    // 1. Visit card catalog as anonymous visitor and add to collection
    await page.goto("/cards/base1-2");
    await page.waitForLoadState("domcontentloaded");

    const addBtn = page.getByRole("button", {
      name: /Voeg toe aan collectie/i,
    });
    await expect(addBtn).toBeVisible({ timeout: 15000 });
    await addBtn.click();

    const addModal = page.locator('[role="dialog"]');
    await expect(addModal).toBeVisible({ timeout: 5000 });

    const createPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/collection") &&
        resp.request().method() === "POST" &&
        resp.status() === 201
    );
    await addModal
      .getByRole("button", { name: /Voeg toe aan collectie/i })
      .click();
    await createPromise;
    await expect(addModal).not.toBeVisible({ timeout: 5000 });

    // 2. View collection as anonymous visitor
    await page.goto("/collection");
    await page.waitForLoadState("domcontentloaded");
    const blastoiseTile = page
      .getByRole("button", { name: /Blastoise/i })
      .first();
    await expect(blastoiseTile).toBeVisible({ timeout: 10000 });

    // 3. Register user account via header modal
    const testEmail = `claimed_owner_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    await page.getByRole("button", { name: "Inloggen" }).click();
    const authModal = page.getByRole("dialog");
    await authModal.getByRole("button", { name: "Registreren" }).click();
    await authModal.getByLabel("E-mailadres").fill(testEmail);
    await authModal.getByLabel("Wachtwoord").fill(testPassword);
    await authModal.getByRole("button", { name: "Account Maken" }).click();
    await expect(authModal).not.toBeVisible({ timeout: 10000 });

    // 4. Verify user is authenticated in header
    await expect(page.getByRole("button", { name: "Uitloggen" })).toBeVisible();

    // 5. Verify the collection item remains available under the new account
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(blastoiseTile).toBeVisible({ timeout: 10000 });
  });

  test("7. Multi-tab synchronization updates state across tabs via BroadcastChannel", async ({
    context,
  }) => {
    const page1 = await context.newPage();
    const page2 = await context.newPage();

    // Open both tabs
    await page1.goto("/");
    await page2.goto("/collection");

    await expect(page1.getByRole("button", { name: "Inloggen" })).toBeVisible();
    await expect(page2.getByRole("button", { name: "Inloggen" })).toBeVisible();

    // Register / Log in in page1
    const testEmail = `multitab_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    await page1.getByRole("button", { name: "Inloggen" }).click();
    const modal = page1.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();
    await modal.locator("#auth-email").fill(testEmail);
    await modal.locator("#auth-password").fill(testPassword);
    await modal.locator('button[type="submit"]').click();
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    // Page 1 is authenticated
    await expect(
      page1.getByRole("button", { name: "Uitloggen" })
    ).toBeVisible();

    // Page 2 should automatically reflect authenticated state via broadcast
    await expect(page2.getByRole("button", { name: "Uitloggen" })).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page2.getByRole("button", { name: "Inloggen" })
    ).not.toBeVisible();

    // Now log out in page2
    await page2.getByRole("button", { name: "Uitloggen" }).click();
    await expect(page2.getByRole("button", { name: "Inloggen" })).toBeVisible();

    // Page 1 should automatically reflect unauthenticated state
    await expect(page1.getByRole("button", { name: "Inloggen" })).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page1.getByRole("button", { name: "Uitloggen" })
    ).not.toBeVisible();

    await page1.close();
    await page2.close();
  });

  test("8. Mobile viewport at 375px renders accessible auth button and functions properly", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    // Inloggen button must be visible on mobile
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await expect(loginBtn).toBeVisible({ timeout: 5000 });

    // Open modal on mobile
    await loginBtn.click();
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();

    const testEmail = `mobile_${Date.now()}@example.com`;
    const testPassword = "ValidPassword123!";

    await modal.getByRole("button", { name: "Registreren" }).click();
    await modal.locator("#auth-email").fill(testEmail);
    await modal.locator("#auth-password").fill(testPassword);
    await modal.locator('button[type="submit"]').click();

    await expect(modal).not.toBeVisible({ timeout: 10000 });

    // Uitloggen is visible on mobile
    const logoutBtn = page.getByRole("button", { name: "Uitloggen" });
    await expect(logoutBtn).toBeVisible({ timeout: 5000 });
    await expect(loginBtn).not.toBeVisible();

    // Log out on mobile
    await logoutBtn.click();
    await expect(page.getByRole("button", { name: "Inloggen" })).toBeVisible({
      timeout: 5000,
    });
  });

  test("9. Temporary auth bootstrap failure never presents the visitor as logged out", async ({
    page,
  }) => {
    let authMeCalls = 0;
    await page.route("**/api/v1/auth/me", async (route) => {
      authMeCalls++;
      if (authMeCalls === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Temporary outage" }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto("/");

    const retryButton = page.getByRole("button", { name: "Opnieuw" });
    await expect(retryButton).toBeVisible({ timeout: 5000 });
    await expect(
      page.getByRole("button", { name: "Inloggen" })
    ).not.toBeVisible();

    await retryButton.click();
    await expect(page.getByRole("button", { name: "Inloggen" })).toBeVisible({
      timeout: 5000,
    });
  });

  test("10. Failed logout preserves authenticated UI and reports the error", async ({
    page,
  }) => {
    const testEmail = `logout_failure_${Date.now()}@example.com`;
    const registerResponse = await page.request.post("/api/v1/auth/register", {
      data: { email: testEmail, password: "ValidPassword123!" },
    });
    expect(registerResponse.status()).toBe(201);

    await page.goto("/");
    const logoutButton = page.getByRole("button", { name: "Uitloggen" });
    await expect(logoutButton).toBeVisible({ timeout: 5000 });

    await page.route("**/api/v1/auth/logout", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Temporary outage" }),
      });
    });
    await logoutButton.click();

    await expect(logoutButton).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Inloggen" })
    ).not.toBeVisible();
    await expect(
      page.getByRole("alert").filter({ hasText: "Uitloggen is niet gelukt" })
    ).toBeVisible();
  });
});
