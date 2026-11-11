import { test, expect } from "@playwright/test";

test.describe("Phase 9 Account Security & Modern Password Policy E2E", () => {
  const timestamp = Date.now();
  const validUsername = `trainer_${timestamp}`.slice(0, 25);
  const validEmail = `trainer_${timestamp}@example.com`;
  const validPassphrase = "DexLensUnpwnedPassword2026!";

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
  });

  test("1. Registration modal presents modern password policy hint and extended fields", async ({
    page,
  }) => {
    // Open auth modal
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await expect(loginBtn).toBeVisible();
    await loginBtn.click();

    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();

    // Switch to register tab
    const registerTab = modal.getByRole("button", { name: "Registreren" });
    await registerTab.click();

    // Verify extended fields are visible
    await expect(modal.locator("#auth-username")).toBeVisible();
    await expect(modal.locator("#auth-email")).toBeVisible();
    await expect(modal.locator("#auth-password")).toBeVisible();
    await expect(modal.locator("#auth-password-confirm")).toBeVisible();
    await expect(modal.locator("#auth-policies")).toBeVisible();

    // Verify password policy helper hint
    const hint = modal.locator("#password-policy-hint");
    await expect(hint).toBeVisible();
    await expect(hint).toContainText("15 tekens");
  });

  test("2. Rejects passwords shorter than 15 characters with accessible Dutch error", async ({
    page,
  }) => {
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await loginBtn.click();

    const modal = page.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();

    await modal.locator("#auth-email").fill("short_pass@example.com");
    await modal.locator("#auth-password").fill("ShortPass1234");
    await modal.locator("#auth-password-confirm").fill("ShortPass1234");

    await modal.locator('button[type="submit"]').click();

    const alert = modal.locator('[role="alert"][aria-live="assertive"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(
      "Wachtwoord moet minimaal 15 tekens bevatten."
    );
  });

  test("3. Rejects password confirmation mismatch with accessible Dutch error", async ({
    page,
  }) => {
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await loginBtn.click();

    const modal = page.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();

    await modal.locator("#auth-email").fill("mismatch@example.com");
    await modal.locator("#auth-password").fill(validPassphrase);
    await modal.locator("#auth-password-confirm").fill("DifferentSecret2026!");

    await modal.locator('button[type="submit"]').click();

    const alert = modal.locator('[role="alert"][aria-live="assertive"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("Wachtwoorden komen niet overeen.");
  });

  test("4. Rejects unaccepted site policies with accessible Dutch error", async ({
    page,
  }) => {
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await loginBtn.click();

    const modal = page.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();

    await modal.locator("#auth-email").fill("unaccepted@example.com");
    await modal.locator("#auth-password").fill(validPassphrase);
    await modal.locator("#auth-password-confirm").fill(validPassphrase);

    // Uncheck terms and privacy policy
    const policyCheckbox = modal.locator("#auth-policies");
    await policyCheckbox.uncheck();

    await modal.locator('button[type="submit"]').click();

    const alert = modal.locator('[role="alert"][aria-live="assertive"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(
      "gebruiksvoorwaarden en het privacybeleid"
    );
  });

  test("5. Rejects invalid username format", async ({ page }) => {
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await loginBtn.click();

    const modal = page.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();

    await modal.locator("#auth-username").fill("bad.user.name!");
    await modal.locator("#auth-email").fill("baduser@example.com");
    await modal.locator("#auth-password").fill(validPassphrase);
    await modal.locator("#auth-password-confirm").fill(validPassphrase);

    await modal.locator('button[type="submit"]').click();

    const alert = modal.locator('[role="alert"][aria-live="assertive"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("tussen 3 en 30 tekens");
  });

  test("6. Successful registration with extended fields displays username and establishes session", async ({
    page,
  }) => {
    const loginBtn = page.getByRole("button", { name: "Inloggen" });
    await loginBtn.click();

    const modal = page.getByRole("dialog");
    await modal.getByRole("button", { name: "Registreren" }).click();

    await modal.locator("#auth-username").fill(validUsername);
    await modal.locator("#auth-email").fill(validEmail);
    await modal.locator("#auth-password").fill(validPassphrase);
    await modal.locator("#auth-password-confirm").fill(validPassphrase);

    await modal.locator('button[type="submit"]').click();

    // Modal closes
    await expect(modal).not.toBeVisible({ timeout: 10000 });

    // Header updates with @username
    const logoutBtn = page.getByRole("button", { name: "Uitloggen" });
    await expect(logoutBtn).toBeVisible({ timeout: 5000 });

    const userBadge = page.locator(`[title*="${validEmail}"]`).first();
    await expect(userBadge).toBeVisible();
    await expect(userBadge).toContainText(`@${validUsername.toLowerCase()}`);

    // Verify session persists across reload
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(logoutBtn).toBeVisible({ timeout: 5000 });
    await expect(
      page.locator(`[title*="${validEmail}"]`).first()
    ).toBeVisible();
  });
});
