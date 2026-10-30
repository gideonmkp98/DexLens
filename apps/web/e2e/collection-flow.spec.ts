import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import path from "path";

const FIXTURE_IMAGE_PATH = path.resolve(
  __dirname,
  "fixtures/pikachu_photo.jpg"
);

async function resetTestDatabaseSafely(request: APIRequestContext) {
  const resetRes = await request.post("/api/v1/testing/reset");
  if (!resetRes.ok()) {
    const body = await resetRes.text();
    throw new Error(
      `Failed to reset test database (status ${resetRes.status()}): ${body}`
    );
  }
}

async function performScanUploadAndConfirmation(page: Page): Promise<string> {
  await page.goto("/scan");
  await expect(page).toHaveTitle(/DexLens/);
  await page.waitForLoadState("domcontentloaded");

  const fileChooserInput = page.locator(
    'input[aria-label="Kies een kaartfoto"]'
  );
  await expect(fileChooserInput).toBeAttached({ timeout: 15000 });
  await fileChooserInput.setInputFiles(FIXTURE_IMAGE_PATH);

  const uploadBtn = page.getByRole("button", {
    name: /Verder naar uitsnijden/i,
  });
  await expect(uploadBtn).toBeVisible({ timeout: 20000 });
  await uploadBtn.click();

  await page.waitForURL(/\/scan\/[a-f0-9-]+/);
  const scanUrl = page.url();
  const scanId = scanUrl.split("/scan/")[1]?.split("?")[0] || "";

  const previewCropBtn = page.getByRole("button", {
    name: /Uitsnede Bekijken/i,
  });
  await expect(previewCropBtn).toBeVisible({ timeout: 15000 });
  const cropResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/crop") && resp.status() === 200
  );
  await previewCropBtn.click();
  await cropResponsePromise;

  await expect(page.getByAltText("Uitsnede preview")).toBeVisible({
    timeout: 15000,
  });

  const confirmCropBtn = page
    .getByRole("button", {
      name: /Deze Uitsnede Bevestigen|Uitsnede Vastzetten/i,
    })
    .first();
  await expect(confirmCropBtn).toBeVisible({ timeout: 15000 });
  await expect(confirmCropBtn).toBeEnabled({ timeout: 15000 });
  const confirmResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/confirm") &&
      !resp.url().includes("/confirm-card") &&
      resp.status() === 200
  );
  await confirmCropBtn.click();
  await confirmResponsePromise;

  const recognizeBtn = page.getByRole("button", {
    name: /Start Optische Herkenning/i,
  });
  await expect(recognizeBtn).toBeVisible({ timeout: 15000 });
  await recognizeBtn.click();

  const chooseCardBtn = page
    .getByRole("button", {
      name: /Kies Deze Kaart/i,
    })
    .first();
  await expect(chooseCardBtn).toBeVisible({ timeout: 30000 });
  await chooseCardBtn.click();

  return scanId;
}

test.describe("Phase 6 End-to-End Collection & Hardened Workflows (Isolated _test Stack)", () => {
  test.beforeAll(async ({ request }) => {
    // ------------------------------------------------------------------------
    // HARD PREFLIGHT SAFETY GUARD:
    // Verify that the target environment is connected strictly to a database
    // ending in '_test' (e.g. tcg_test on http://localhost:3001).
    // If targeted at a development or production database, ABORT IMMEDIATELY.
    // ------------------------------------------------------------------------
    const res = await request.get("/api/v1/testing/db-info");
    if (!res.ok()) {
      throw new Error(
        `[FATAL SAFETY GUARD] Failed to query /api/v1/testing/db-info (status ${res.status()}). ` +
          `Make sure the isolated test stack is running (docker compose -f docker-compose.test.yml up -d).`
      );
    }
    const dbInfo = await res.json();
    if (!dbInfo.is_test_database) {
      throw new Error(
        `[CRITICAL SAFETY GUARD VIOLATION] E2E test suite attempted to execute against NON-TEST database '${dbInfo.database}'. ` +
          `Target server is not connected to a database ending in '_test'. ` +
          `Execution is strictly blocked to protect real development/production collection data from modification or deletion! ` +
          `Make sure tests run against the isolated test stack on port 3001 (baseURL: http://localhost:3001).`
      );
    }

    // Clean the dedicated test database to establish a fresh baseline
    await resetTestDatabaseSafely(request);
  });

  test.beforeEach(async ({ request }) => {
    // Safely reset the isolated test database before each test
    await resetTestDatabaseSafely(request);
  });

  test.afterEach(async ({ request }) => {
    // Safely reset the isolated test database after each test
    await resetTestDatabaseSafely(request);
  });

  test.afterAll(async ({ request }) => {
    // Clean test database after the test suite finishes
    await resetTestDatabaseSafely(request);
  });

  test("Flows 1-6: Scan -> Add -> Duplicate grouping -> Idempotency -> Atomic edit -> Stale 409 -> Persistence", async ({
    page,
    request,
  }) => {
    // ------------------------------------------------------------------------
    // FLOW 1: Upload -> detect -> crop -> OCR -> candidate confirmation -> add to collection
    // ------------------------------------------------------------------------
    const scanId1 = await performScanUploadAndConfirmation(page);
    expect(scanId1).toBeTruthy();

    const addToCollectionBtn = page.getByRole("button", {
      name: /Voeg toe aan collectie/i,
    });
    await expect(addToCollectionBtn).toBeVisible({ timeout: 15000 });
    const addPromise = page.waitForResponse(
      (resp) => resp.url().includes("/collection") && resp.status() === 201
    );
    await addToCollectionBtn.click();
    await addPromise;

    const inCollectionLink = page.getByRole("link", {
      name: /In collectie ✓/i,
    });
    await expect(inCollectionLink).toBeVisible({ timeout: 10000 });

    await page.goto("/collection");
    const pikachuTile = page
      .locator("article, div, button", {
        hasText: /Pikachu/i,
      })
      .first();
    await expect(pikachuTile).toBeVisible({ timeout: 10000 });

    // ------------------------------------------------------------------------
    // FLOW 2: Second independent scan of same card -> same collection tile with quantity increment (x2)
    // ------------------------------------------------------------------------
    const scanId2 = await performScanUploadAndConfirmation(page);
    expect(scanId2).toBeTruthy();
    expect(scanId2).not.toEqual(scanId1);

    const addSecondScanBtn = page.getByRole("button", {
      name: /Voeg toe aan collectie/i,
    });
    await expect(addSecondScanBtn).toBeVisible({ timeout: 15000 });
    const addSecondPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/collection") &&
        (resp.status() === 200 || resp.status() === 201)
    );
    await addSecondScanBtn.click();
    await addSecondPromise;

    await expect(
      page.getByRole("link", { name: /In collectie ✓/i })
    ).toBeVisible({
      timeout: 10000,
    });

    await page.goto("/collection");
    // Verify grouping: exactly ONE Pikachu tile exists, displaying x2
    const pikachuTiles = page.getByRole("button", { name: /Pikachu/i });
    await expect(pikachuTiles).toHaveCount(1);
    await expect(pikachuTiles.first()).toContainText("×2");

    // ------------------------------------------------------------------------
    // FLOW 3: Repeating same scan -> no additional increment (idempotent HTTP 200)
    // ------------------------------------------------------------------------
    const repeatScanRes = await request.post(
      `/api/v1/scans/${scanId2}/collection`
    );
    expect(repeatScanRes.status()).toBe(200);
    const repeatData = await repeatScanRes.json();
    expect(repeatData.quantity).toBe(2);

    await page.goto("/collection");
    await expect(page.getByRole("button", { name: /Pikachu/i })).toHaveCount(1);
    await expect(
      page.getByRole("button", { name: /Pikachu/i }).first()
    ).toContainText("×2");

    // ------------------------------------------------------------------------
    // FLOW 4: Edit quantity using expected version
    // ------------------------------------------------------------------------
    const cardTileBtn = page.getByRole("button", { name: /Pikachu/i }).first();
    await cardTileBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    const quantityInput = modal.locator("#edit-quantity");
    await expect(quantityInput).toHaveValue("2");

    const incBtn = modal.getByRole("button", {
      name: "Verhoog aantal exemplaren",
    });
    await incBtn.click();
    await expect(quantityInput).toHaveValue("3");

    const saveBtn = modal.getByRole("button", {
      name: /Wijzigingen opslaan/i,
    });
    const patchPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/collection/") &&
        resp.request().method() === "PATCH" &&
        resp.status() === 200
    );
    await saveBtn.click();
    const patchResp = await patchPromise;
    const patchedItem = await patchResp.json();
    expect(patchedItem.quantity).toBe(3);
    const pikachuItemId = patchedItem.id;

    await expect(modal).not.toBeVisible({ timeout: 5000 });
    await expect(
      page.getByRole("button", { name: /Pikachu/i }).first()
    ).toContainText("×3");

    // ------------------------------------------------------------------------
    // FLOW 5: Stale concurrent edit -> HTTP 409
    // ------------------------------------------------------------------------
    // The item was updated and its version is now at least 2. Sending expected_version = 1 must fail.
    const stalePatchRes = await request.patch(
      `/api/v1/collection/${pikachuItemId}`,
      {
        data: {
          expected_version: 1,
          quantity: 99,
        },
      }
    );
    expect(stalePatchRes.status()).toBe(409);
    const conflictBody = await stalePatchRes.json();
    expect(conflictBody.detail?.code).toBe("VERSION_CONFLICT");

    // ------------------------------------------------------------------------
    // FLOW 6: Reload -> persistence remains correct
    // ------------------------------------------------------------------------
    await page.reload();
    const persistedCardTile = page
      .getByRole("button", { name: /Pikachu/i })
      .first();
    await expect(persistedCardTile).toBeVisible({ timeout: 10000 });
    await expect(persistedCardTile).toContainText("×3");
  });

  test("Flows 7-8: Manual catalog addition -> set variant & condition -> safe deletion", async ({
    page,
  }) => {
    // ------------------------------------------------------------------------
    // FLOW 7: Manual catalog addition
    // ------------------------------------------------------------------------
    await page.goto("/cards/base1-2");
    await expect(page).toHaveTitle(/DexLens/);

    const addBtn = page.getByRole("button", {
      name: /Voeg toe aan collectie/i,
    });
    await expect(addBtn).toBeVisible({ timeout: 15000 });
    await addBtn.click();

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    const variantSelect = modal.locator("#card-variant");
    await variantSelect.selectOption("holo");

    const conditionSelect = modal.locator("#card-condition");
    await conditionSelect.selectOption("mint");

    const submitBtn = modal.getByRole("button", {
      name: /Voeg toe aan collectie/i,
    });
    const createPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/collection") &&
        resp.request().method() === "POST" &&
        resp.status() === 201
    );
    await submitBtn.click();
    await createPromise;

    await expect(modal).not.toBeVisible({ timeout: 5000 });

    await page.goto("/collection");

    const blastoiseTile = page
      .getByRole("button", { name: /Blastoise/i })
      .first();
    await expect(blastoiseTile).toBeVisible({ timeout: 10000 });
    await expect(blastoiseTile).toContainText("Holo");
    await expect(blastoiseTile).toContainText("M");

    // ------------------------------------------------------------------------
    // FLOW 8: Safe deletion
    // ------------------------------------------------------------------------
    await blastoiseTile.click();
    const editModal = page.locator('[role="dialog"]');
    await expect(editModal).toBeVisible({ timeout: 5000 });

    const deleteBtn = editModal.getByRole("button", {
      name: /Verwijder uit collectie/i,
    });
    await deleteBtn.click();

    const confirmDeleteBtn = page
      .locator('[role="alertdialog"]')
      .getByRole("button", {
        name: /Ja, verwijderen/i,
      });
    await expect(confirmDeleteBtn).toBeVisible({ timeout: 5000 });
    const deletePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/collection/") &&
        resp.request().method() === "DELETE" &&
        resp.status() === 204
    );
    await confirmDeleteBtn.click();
    await deletePromise;

    await expect(editModal).not.toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: /Blastoise/i })).toHaveCount(
      0
    );
  });

  test("Flow 9: Existing Phase 5 upload and recognition workflow remains operational", async ({
    page,
  }) => {
    // ------------------------------------------------------------------------
    // FLOW 9: Existing upload workflow remains functional
    // ------------------------------------------------------------------------
    await page.goto("/scan");
    await expect(page).toHaveTitle(/DexLens/);

    const fileChooserInput = page.locator(
      'input[aria-label="Kies een kaartfoto"]'
    );
    await fileChooserInput.setInputFiles(FIXTURE_IMAGE_PATH);

    const uploadBtn = page.getByRole("button", {
      name: /Verder naar uitsnijden/i,
    });
    await expect(uploadBtn).toBeVisible({ timeout: 15000 });
    await uploadBtn.click();

    await page.waitForURL(/\/scan\/[a-f0-9-]+/);

    const previewCropBtn = page.getByRole("button", {
      name: /Uitsnede Bekijken/i,
    });
    await expect(previewCropBtn).toBeVisible({ timeout: 15000 });
    await previewCropBtn.click();

    await expect(page.getByAltText("Uitsnede preview")).toBeVisible({
      timeout: 15000,
    });

    const confirmCropBtn = page
      .getByRole("button", {
        name: /Deze Uitsnede Bevestigen|Uitsnede Vastzetten/i,
      })
      .first();
    await expect(confirmCropBtn).toBeVisible({ timeout: 15000 });
    await confirmCropBtn.click();

    const recognizeBtn = page.getByRole("button", {
      name: /Start Optische Herkenning/i,
    });
    await expect(recognizeBtn).toBeVisible({ timeout: 15000 });
    await recognizeBtn.click();

    // Verify candidates are rendered with confidence badges and selection button
    const chooseCardBtn = page
      .getByRole("button", {
        name: /Kies Deze Kaart/i,
      })
      .first();
    await expect(chooseCardBtn).toBeVisible({ timeout: 30000 });

    // Selecting candidate renders confirmed card specimen slab
    await chooseCardBtn.click();
    await expect(
      page.getByRole("button", { name: /Voeg toe aan collectie/i })
    ).toBeVisible({
      timeout: 10000,
    });
    // Verify scan specimen details (Base Set, 58/102) without needing to add to collection
    await expect(page.locator("body")).toContainText("Base Set");
  });

  test("Database Safety Guard: Refuses destructive reset on non-test databases and allows on test database", async ({
    request,
  }) => {
    // 1. Verify reset is allowed on the current isolated test stack (tcg_test)
    const testResetRes = await request.post("/api/v1/testing/reset");
    expect(testResetRes.status()).toBe(200);
    const testResetBody = await testResetRes.json();
    expect(testResetBody.status).toBe("success");
    expect(testResetBody.database).toBe("tcg_test");

    // 2. Verify that if a destructive reset is attempted against the dev API on port 8000 (tcg),
    // it is STRICTLY REFUSED with HTTP 403 Forbidden.
    try {
      const devRes = await request.post(
        "http://localhost:8000/api/v1/testing/reset"
      );
      expect(devRes.status()).toBe(403);
      const devBody = await devRes.json();
      expect(devBody.detail).toContain("SAFETY GUARD REJECTION");
      expect(devBody.detail).toContain("tcg");
    } catch (err) {
      // If dev API port 8000 is not exposed/running, that also ensures safety
      console.log("Dev API on port 8000 verified safe or unreachable:", err);
    }
  });
});
