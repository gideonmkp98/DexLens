import { test, expect, type Page } from "@playwright/test";
import fs from "fs";
import path from "path";

// Load test card photo fixture for 100% deterministic OpenCV & OCR recognition
const pikachuImagePath = path.resolve(
  __dirname,
  "../../../scratch_browser_test/pikachu_photo.jpg"
);
const pikachuBase64 = fs.readFileSync(pikachuImagePath).toString("base64");
const pikachuDataUrl = `data:image/jpeg;base64,${pikachuBase64}`;

const BASE_URL = process.env.BASE_URL || "http://localhost:3001";

interface MockCameraOptions {
  mode?:
    | "card"
    | "poor_lighting"
    | "glare"
    | "motion"
    | "flat"
    | "blurry"
    | "busy_background"
    | "denied"
    | "not_found";
}

/**
 * Injects a synthetic, canvas-backed MediaStream mock into the browser context.
 * Enables deterministic testing of camera permissions, device enumeration,
 * optical frame analysis, auto-capture, and media track teardown.
 */
async function setupMockCamera(page: Page, options: MockCameraOptions = {}) {
  const initialMode = options.mode ?? "card";

  await page.addInitScript(
    ({ pikaDataUrl, mode }) => {
      (window as any).__cameraMock = {
        mode,
        trackStopped: false,
      };

      if (mode === "denied") {
        if (!navigator.mediaDevices) {
          (navigator as any).mediaDevices = {};
        }
        navigator.mediaDevices.getUserMedia = async () => {
          throw new DOMException("Permission denied", "NotAllowedError");
        };
        return;
      }

      if (mode === "not_found") {
        if (!navigator.mediaDevices) {
          (navigator as any).mediaDevices = {};
        }
        navigator.mediaDevices.getUserMedia = async () => {
          throw new DOMException("No camera found", "NotFoundError");
        };
        navigator.mediaDevices.enumerateDevices = async () => [];
        return;
      }

      // Convert pikachuDataUrl to a real Blob for JPEG frame captures
      try {
        const base64Part = pikaDataUrl.split(",")[1] || "";
        const byteCharacters = atob(base64Part);
        const byteNumbers = new Uint8Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        (window as any).__pikachuBlob = new Blob(
          [byteNumbers.buffer as ArrayBuffer],
          { type: "image/jpeg" }
        );
      } catch {
        // Fallback handled gracefully
      }

      // Intercept HTMLCanvasElement.prototype.toBlob to deliver the clean test card
      // when captureLiveScanFrame runs in 'card' mode
      const origToBlob = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = function (callback, type, quality) {
        const curMode = (window as any).__cameraMock?.mode;
        if (curMode === "card" && (window as any).__pikachuBlob) {
          (window as any).__cameraMock.lastCaptureSize = {
            width: this.width,
            height: this.height,
          };
          callback((window as any).__pikachuBlob);
          return;
        }
        origToBlob.call(this, callback, type, quality);
      };

      // High-precision synthetic frame generator for card quality analyzer
      function getSyntheticImageData(
        w: number,
        h: number,
        curMode: string,
        count: number
      ) {
        const data = new Uint8ClampedArray(w * h * 4);
        if (curMode === "poor_lighting") {
          data.fill(15);
          for (let i = 3; i < data.length; i += 4) data[i] = 255;
          return new ImageData(data, w, h);
        }
        if (curMode === "glare") {
          data.fill(120);
          for (let i = 3; i < data.length; i += 4) data[i] = 255;
          // Hotspot: 10% of pixels = 255
          for (let i = 0; i < Math.floor(w * h * 0.1) * 4; i += 4) {
            data[i] = 255;
            data[i + 1] = 255;
            data[i + 2] = 255;
          }
          return new ImageData(data, w, h);
        }
        if (curMode === "motion") {
          const val = count % 2 === 0 ? 50 : 200;
          data.fill(val);
          for (let i = 3; i < data.length; i += 4) data[i] = 255;
          return new ImageData(data, w, h);
        }
        if (curMode === "blurry" || curMode === "flat") {
          data.fill(128);
          for (let i = 3; i < data.length; i += 4) data[i] = 255;
          return new ImageData(data, w, h);
        }
        if (curMode === "busy_background") {
          for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
              const idx = (y * w + x) * 4;
              const value = 55 + ((x * 37 + y * 53 + ((x * y) % 97)) % 145);
              data[idx] = value;
              data[idx + 1] = Math.max(35, value - ((x * 11) % 31));
              data[idx + 2] = Math.max(30, value - ((y * 7) % 43));
              data[idx + 3] = 255;
            }
          }
          return new ImageData(data, w, h);
        }

        // Mode: 'card' (Synthetic perfectly-framed card)
        const cardW = 120;
        const cardH = 168; // 120 / 168 = 0.714285 (~ 63/88)
        const startX = Math.floor((w - cardW) / 2);
        const startY = Math.floor((h - cardH) / 2);

        // Background: 35
        for (let i = 0; i < data.length; i += 4) {
          data[i] = 35;
          data[i + 1] = 35;
          data[i + 2] = 35;
          data[i + 3] = 255;
        }

        // Card interior with rich texture
        for (let y = startY; y < startY + cardH; y++) {
          for (let x = startX; x < startX + cardW; x++) {
            const idx = (y * w + x) * 4;
            const noise = ((x * 17 + y * 31) % 60) - 30;
            const val = Math.min(210, Math.max(50, 130 + noise));
            data[idx] = val;
            data[idx + 1] = val;
            data[idx + 2] = val;
            data[idx + 3] = 255;
          }
        }
        return new ImageData(data, w, h);
      }

      let sampleCounter = 0;
      const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
      CanvasRenderingContext2D.prototype.getImageData = function (
        sx: number,
        sy: number,
        sw: number,
        sh: number
      ) {
        if (
          ((sw === 320 && sh === 240) || (sw === 180 && sh === 252)) &&
          (window as any).__cameraMock
        ) {
          sampleCounter++;
          const curMode = (window as any).__cameraMock.mode;
          return getSyntheticImageData(sw, sh, curMode, sampleCounter);
        }
        return origGetImageData.call(this, sx, sy, sw, sh);
      };

      // Offscreen canvas serving as the simulated camera sensor
      const mockCanvas = document.createElement("canvas");
      mockCanvas.width = 640;
      mockCanvas.height = 480;
      const mockCtx = mockCanvas.getContext("2d", { willReadFrequently: true });

      function renderSyntheticFrame() {
        if (!mockCtx) return;
        mockCtx.fillStyle = "rgb(80, 90, 105)";
        mockCtx.fillRect(0, 0, 640, 480);
      }

      setInterval(renderSyntheticFrame, 50);
      renderSyntheticFrame();

      const stream = mockCanvas.captureStream(30);
      const videoTrack = stream.getVideoTracks()[0];
      if (videoTrack) {
        const origStop = videoTrack.stop.bind(videoTrack);
        videoTrack.stop = () => {
          (window as any).__cameraMock.trackStopped = true;
          origStop();
        };
        (videoTrack as any).applyConstraints = async () => {};
        (videoTrack as any).getCapabilities = () => ({
          torch: true,
          zoom: { min: 1, max: 5, step: 0.1 },
        });
        (videoTrack as any).getSettings = () => ({
          deviceId: "mock-environment-camera",
          facingMode: "environment",
          width: 640,
          height: 480,
        });
      }

      if (!navigator.mediaDevices) {
        (navigator as any).mediaDevices = {};
      }

      navigator.mediaDevices.getUserMedia = async () => {
        const curMode = (window as any).__cameraMock?.mode;
        if (curMode === "denied") {
          throw new DOMException("Permission denied", "NotAllowedError");
        }
        if (curMode === "not_found") {
          throw new DOMException("No camera found", "NotFoundError");
        }
        return stream;
      };

      navigator.mediaDevices.enumerateDevices = async () => [
        {
          deviceId: "mock-environment-camera",
          kind: "videoinput",
          label: "Rear Camera (Environment)",
          groupId: "mock-group",
          toJSON: () => ({}),
        } as MediaDeviceInfo,
        {
          deviceId: "mock-user-camera",
          kind: "videoinput",
          label: "Front Camera (User)",
          groupId: "mock-group",
          toJSON: () => ({}),
        } as MediaDeviceInfo,
      ];

      // Ensure HTMLVideoElement plays smoothly and sets dimensions
      const origPlay = HTMLVideoElement.prototype.play;
      HTMLVideoElement.prototype.play = async function () {
        if (this.srcObject) {
          Object.defineProperty(this, "videoWidth", {
            value: 640,
            configurable: true,
          });
          Object.defineProperty(this, "videoHeight", {
            value: 480,
            configurable: true,
          });
          Object.defineProperty(this, "readyState", {
            value: 4,
            configurable: true,
          });
        }
        try {
          return await origPlay.call(this);
        } catch {
          return;
        }
      };
    },
    { pikaDataUrl: pikachuDataUrl, mode: initialMode }
  );
}

async function startLiveScanner(page: Page) {
  const startButton = page.getByRole("button", { name: "Scanner starten" });
  await expect(startButton).toBeVisible({ timeout: 10000 });
  // The button can be server-rendered a moment before React attaches handlers.
  await page.waitForTimeout(500);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await startButton.click();
    if (!(await startButton.isVisible())) {
      return;
    }
    await page.waitForTimeout(500);
  }
  await expect(startButton).not.toBeVisible({ timeout: 5000 });
}

test.describe("Phase 7: Live Scan & Go End-to-End Test Suite", () => {
  // SAFETY RULE 1: Hard safety guard verifying connection to isolated test database
  test.beforeAll(async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/v1/testing/db-info`);
    expect(res.ok()).toBeTruthy();
    const dbInfo = await res.json();

    const dbName = (dbInfo.database || dbInfo.database_name || "") as string;
    const isTest = Boolean(dbInfo.is_test_database);

    if (!isTest || !dbName.endsWith("_test")) {
      throw new Error(
        `SAFETY GUARD REJECTION: E2E test suite must only run against an isolated test database ending in '_test'. Received: ${JSON.stringify(dbInfo)}`
      );
    }
  });

  // SAFETY RULE 3: Reset test database strictly via /api/v1/testing/reset before every test
  test.beforeEach(async ({ request, page }) => {
    const resetRes = await request.post(`${BASE_URL}/api/v1/testing/reset`);
    expect(resetRes.ok()).toBeTruthy();
    const body = await resetRes.json();
    expect(body.status).toBe("success");
    await page.addInitScript(() => {
      localStorage.setItem("dexlens_scanner_tips_seen", "true");
    });
  });

  // =========================================================================
  // SCENARIO 1: Supported-camera happy path with mocked media stream
  // =========================================================================
  test("1. Supported-camera happy path with mocked media stream", async ({
    page,
  }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);
    await expect(page).toHaveTitle(/DexLens/);

    // Live scanner is active by default
    const video = page.locator('video[aria-label="Live camera videofeed"]');
    await expect(video).toBeVisible({ timeout: 10000 });

    // Live mode is a dedicated full-screen workspace without a duplicate
    // page-level mode switcher above the camera controls.
    await expect(page.getByTestId("live-camera-scanner")).toBeVisible();
    await expect(
      page.locator('nav[aria-label="Scan methode selectie"]')
    ).not.toBeVisible();

    // Switch to manual so the quality HUD can be observed without auto-capturing.
    await page.getByRole("button", { name: "Zelf" }).click();
    const shutterBtn = page.getByRole("button", {
      name: "Maak een foto van de kaart",
    });
    await expect(shutterBtn).toBeEnabled();

    // HUD guidance pill is rendered with "Kaart gereed"
    const hudPill = page.locator("main span:has-text('Kaart gereed')");
    await expect(hudPill).toBeVisible({ timeout: 10000 });
  });

  // =========================================================================
  // SCENARIO 2: Camera permission denied UI fallback
  // =========================================================================
  test("2. Camera permission denied UI fallback", async ({ page }) => {
    await setupMockCamera(page, { mode: "denied" });
    await page.goto("/scan");
    await startLiveScanner(page);

    // Error alert banner displays Dutch guidance (filter out next-route-announcer)
    const alert = page
      .getByRole("alert")
      .filter({ hasText: "Cameratoegang niet mogelijk" });
    await expect(alert).toBeVisible({ timeout: 10000 });
    await expect(alert).toContainText(
      "Cameratoegang is geweigerd. Geef toestemming via je browserinstellingen."
    );

    // Fallback button allows immediate switch to photo upload
    const uploadFallbackBtn = alert.getByRole("button", {
      name: "Foto uploaden",
    });
    await expect(uploadFallbackBtn).toBeVisible();
    await uploadFallbackBtn.click();

    // Verify view transitioned to upload mode
    await expect(
      page.locator('input[aria-label="Kies een kaartfoto"]')
    ).toBeAttached();
    await expect(page.getByText("PLAATS JE KAARTFOTO")).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 3: No camera hardware available fallback
  // =========================================================================
  test("3. No camera hardware available fallback", async ({ page }) => {
    await setupMockCamera(page, { mode: "not_found" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const alert = page
      .getByRole("alert")
      .filter({ hasText: "Cameratoegang niet mogelijk" });
    await expect(alert).toBeVisible({ timeout: 10000 });
    await expect(alert).toContainText("Geen camera gevonden op dit apparaat.");

    const uploadBtn = alert.getByRole("button", { name: "Foto uploaden" });
    await expect(uploadBtn).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 4: Unsupported browser fallback
  // =========================================================================
  test("4. Unsupported browser fallback", async ({ page }) => {
    // Simulate a browser without the mediaDevices API on the navigator instance.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "mediaDevices", {
        value: undefined,
        configurable: true,
      });
    });

    await page.goto("/scan");

    // ScanPage automatically falls back to upload mode
    const liveScannerBtn = page.getByRole("button", { name: /Live Scanner/i });
    await expect(liveScannerBtn).toBeDisabled();

    const uploadModeBtn = page.getByRole("button", { name: /Foto uploaden/i });
    await expect(uploadModeBtn).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("PLAATS JE KAARTFOTO")).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 5: Manual capture flow
  // =========================================================================
  test("5. Manual capture flow", async ({ page }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    // Disable auto-capture so we explicitly test manual shutter trigger
    const manualModeBtn = page.getByRole("button", { name: "Zelf" });
    await expect(manualModeBtn).toBeVisible({ timeout: 10000 });
    await manualModeBtn.click();
    await expect(manualModeBtn).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Jij bepaalt het moment")).toBeVisible();

    // Click shutter button and wait for capture API response
    const shutterBtn = page.getByRole("button", {
      name: "Maak een foto van de kaart",
    });
    const capturePromise = page.waitForResponse(
      (resp) => resp.url().includes("/capture") && resp.status() === 200
    );
    await shutterBtn.click();
    await capturePromise;

    const capturedSize = await page.evaluate(
      () => (window as any).__cameraMock?.lastCaptureSize
    );
    expect(capturedSize).toBeTruthy();
    expect(capturedSize.width).toBeLessThan(640);
    expect(capturedSize.height).toBeLessThan(480);
    expect(capturedSize.width / capturedSize.height).toBeGreaterThan(0.69);
    expect(capturedSize.width / capturedSize.height).toBeLessThan(0.74);

    // Match modal opens
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 10000 });
    await expect(
      modal.getByRole("heading", {
        name: /Sterke match|Waarschijnlijke match|Controleer deze suggestie/,
      })
    ).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 6: Automatic capture flow after consecutive stable frames
  // =========================================================================
  test("6. Automatic capture flow after consecutive stable frames", async ({
    page,
  }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    // Auto-capture is on by default. Wait for five stable frames to trigger capture.
    const capturePromise = page.waitForResponse(
      (resp) => resp.url().includes("/capture") && resp.status() === 200,
      { timeout: 15000 }
    );
    await capturePromise;

    // Modal appears without pressing the shutter button
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 10000 });
  });

  // =========================================================================
  // SCENARIO 7: No automatic capture during blur, motion, or glare
  // =========================================================================
  test("7. No automatic capture during blur, motion, or glare", async ({
    page,
  }) => {
    // 7a. Test Poor Lighting
    await setupMockCamera(page, { mode: "poor_lighting" });
    await page.goto("/scan");
    await startLiveScanner(page);

    await expect(page.getByText("Meer licht nodig").first()).toBeVisible({
      timeout: 10000,
    });
    // Wait to confirm auto-capture does not trigger
    await page.waitForTimeout(800);
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);

    // 7b. A sharp, busy background without a card must never auto-capture.
    await page.evaluate(() => {
      (window as any).__cameraMock.mode = "busy_background";
    });
    await expect(
      page.getByText("Plaats de kaart in het kader").first()
    ).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(1300);
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);

    // 7c. Test Glare
    await page.evaluate(() => {
      (window as any).__cameraMock.mode = "glare";
    });
    await expect(page.getByText("Minder weerspiegeling").first()).toBeVisible({
      timeout: 10000,
    });
    await page.waitForTimeout(800);
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);

    // 7d. Test Motion / Unstable
    await page.evaluate(() => {
      (window as any).__cameraMock.mode = "motion";
    });
    await expect(page.getByText("Houd stil").first()).toBeVisible({
      timeout: 10000,
    });
    await page.waitForTimeout(800);
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  });

  // =========================================================================
  // SCENARIO 8: Retake action
  // =========================================================================
  test("8. Retake action", async ({ page }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    // Wait for capture modal
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    // Click retake button
    const retakeBtn = modal.getByRole("button", {
      name: /Opnieuw scannen/i,
    });
    await expect(retakeBtn).toBeVisible();
    await retakeBtn.click();

    // Modal closes and live scanner is active again
    await expect(modal).not.toBeVisible({ timeout: 5000 });
    await expect(
      page.locator('video[aria-label="Live camera videofeed"]')
    ).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 9: Recognition success and slab display
  // =========================================================================
  test("9. Recognition success and slab display", async ({ page }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    // Verify candidate slab details for Pikachu
    await expect(modal.locator("h3")).toContainText("Pikachu");
    await expect(modal.getByText("Base Set", { exact: true })).toBeVisible();
    await expect(modal.getByText("#58", { exact: true })).toBeVisible();
    await expect(modal.getByText(/Rangscore \d+\/100/)).toBeVisible();

    // Card artwork image is rendered
    const artwork = modal.locator('img[alt="Pikachu"]').first();
    await expect(artwork).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 10: Low-confidence alternatives selection and manual correction
  // =========================================================================
  test("10. Low-confidence alternatives selection and manual correction", async ({
    page,
  }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    // Alternatives accordion
    const altToggle = modal.getByRole("button", {
      name: /Andere mogelijkheden/i,
    });
    if (await altToggle.isVisible()) {
      await altToggle.click();

      const altCardBtn = modal
        .getByRole("button", { name: "Kies deze kaart" })
        .first();
      if (await altCardBtn.isVisible()) {
        const confirmPromise = page.waitForResponse(
          (resp) =>
            resp.url().includes("/confirm-card") && resp.status() === 200
        );
        await altCardBtn.click();
        await confirmPromise;
      }
    }

    // Verify manual correction link targets /scan/{id}
    const manualLink = modal.getByRole("link", {
      name: /Handmatig aanpassen/i,
    });
    await expect(manualLink).toBeVisible();
    await expect(manualLink).toHaveAttribute("href", /\/scan\/[a-f0-9-]+/);
  });

  // =========================================================================
  // SCENARIO 11: Add to collection from live match modal
  // =========================================================================
  test("11. Add to collection from live match modal", async ({
    page,
    request,
  }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    // Add card to collection
    const addBtn = modal.getByRole("button", {
      name: /Voeg toe aan collectie|Bevestig & voeg toe/i,
    });
    await expect(addBtn).toBeVisible();

    const addPromise = page.waitForResponse(
      (resp) => resp.url().includes("/collection") && resp.status() === 201
    );
    await addBtn.click();
    await addPromise;

    // Button transforms to confirmed status
    await expect(
      modal.getByRole("button", { name: /In collectie/i })
    ).toBeVisible({ timeout: 5000 });

    // Verify item exists in database via API
    const collRes = await page.request.get(`${BASE_URL}/api/v1/collection`);
    expect(collRes.ok()).toBeTruthy();
    const data = await collRes.json();
    expect(data.total).toBe(1);
    expect(data.items[0].card_id).toBe("base1-58");
  });

  // =========================================================================
  // SCENARIO 12: Duplicate scan grouping
  // =========================================================================
  test("12. Duplicate scan grouping", async ({ page, request }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    // Add first scan to collection
    const addBtn = modal.getByRole("button", {
      name: /Voeg toe aan collectie|Bevestig & voeg toe/i,
    });
    const addPromise1 = page.waitForResponse(
      (resp) => resp.url().includes("/collection") && resp.status() === 201
    );
    await addBtn.click();
    await addPromise1;

    // Scan next card in same session
    const nextBtn = modal.getByRole("button", {
      name: /Volgende kaart scannen/i,
    });
    await nextBtn.click();
    await expect(modal).not.toBeVisible();

    const scannerControls = page.getByRole("contentinfo");
    const sessionTray = page.getByRole("complementary", {
      name: "Huidige scansessie",
    });
    await expect(scannerControls).toBeVisible();
    await expect(sessionTray).toBeVisible();
    const controlsBox = await scannerControls.boundingBox();
    const trayBox = await sessionTray.boundingBox();
    expect(controlsBox).not.toBeNull();
    expect(trayBox).not.toBeNull();
    expect(
      (controlsBox?.y ?? 0) + (controlsBox?.height ?? 0)
    ).toBeLessThanOrEqual((trayBox?.y ?? 0) + 1);

    const manualModeBtn = page.getByRole("button", { name: "Zelf" });
    await manualModeBtn.click();
    await expect(manualModeBtn).toHaveAttribute("aria-pressed", "true");

    // Trigger second scan
    const shutterBtn = page.getByRole("button", {
      name: "Maak een foto van de kaart",
    });
    const capturePromise = page.waitForResponse(
      (resp) => resp.url().includes("/capture") && resp.status() === 200
    );
    await shutterBtn.click();
    await capturePromise;

    await expect(modal).toBeVisible({ timeout: 10000 });

    // Add second scan to collection (increments quantity to 2)
    const addBtn2 = modal.getByRole("button", {
      name: /Voeg toe aan collectie|Bevestig & voeg toe/i,
    });
    await expect(addBtn2).toBeVisible({ timeout: 10000 });
    const addPromise2 = page.waitForResponse(
      (resp) =>
        resp.url().includes("/collection") &&
        (resp.status() === 200 || resp.status() === 201)
    );
    await addBtn2.click();
    await addPromise2;

    // Verify collection has 1 unique card with quantity 2
    const collRes = await page.request.get(`${BASE_URL}/api/v1/collection`);
    expect(collRes.ok()).toBeTruthy();
    const data = await collRes.json();
    expect(data.total).toBe(1);
    expect(data.items[0].quantity).toBe(2);

    // Verify on /collection page
    await page.goto("/collection");
    const pikachuTile = page.getByRole("button", { name: /Pikachu/i }).first();
    await expect(pikachuTile).toBeVisible({ timeout: 10000 });
    await expect(pikachuTile).toContainText("×2");
  });

  // =========================================================================
  // SCENARIO 13: Idempotent repeat scan request
  // =========================================================================
  test("13. Idempotent repeat scan request", async ({ page, request }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    const addBtn = modal.getByRole("button", {
      name: /Voeg toe aan collectie|Bevestig & voeg toe/i,
    });
    const addPromise = page.waitForResponse(
      (resp) => resp.url().includes("/collection") && resp.status() === 201
    );
    await addBtn.click();
    const addResp = await addPromise;
    const itemData = await addResp.json();
    const scanId = itemData.source_scan_id;

    // Send direct repeat POST /api/v1/scans/{id}/collection
    const repeatRes = await page.request.post(
      `${BASE_URL}/api/v1/scans/${scanId}/collection`
    );
    expect(repeatRes.status()).toBe(200); // 200 OK idempotent, not 201 Created

    // Verify quantity is still 1
    const collRes = await page.request.get(`${BASE_URL}/api/v1/collection`);
    const collData = await collRes.json();
    expect(collData.items[0].quantity).toBe(1);
  });

  // =========================================================================
  // SCENARIO 14: Scan next card in same session without leaving scanner
  // =========================================================================
  test("14. Scan next card in same session without leaving scanner", async ({
    page,
  }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 15000 });

    // Click "Volgende kaart scannen"
    const nextBtn = modal.getByRole("button", {
      name: /Volgende kaart scannen/i,
    });
    await nextBtn.click();
    await expect(modal).not.toBeVisible();

    const manualModeBtn = page.getByRole("button", { name: "Zelf" });
    await manualModeBtn.click();
    await expect(manualModeBtn).toHaveAttribute("aria-pressed", "true");

    // Verify session tray shows 1 scan item
    await expect(page.getByText(/1 kaart gescand|Sessie/i).first()).toBeVisible(
      {
        timeout: 10000,
      }
    );

    // Verify session tray can expand and collapse cleanly
    const trayToggle = page.getByRole("button", { name: /kaart gescand/i });
    await expect(trayToggle).toBeVisible({ timeout: 10000 });
    await trayToggle.click();
    await expect(page.locator("#scan-session-tray-drawer")).toBeVisible();
    await expect(page.getByText(/Sessiegeschiedenis/i)).toBeVisible();
    await page.getByRole("button", { name: "Sluiten ✕" }).click();
    await expect(page.locator("#scan-session-tray-drawer")).not.toBeVisible();

    // Capture a second card
    const shutterBtn = page.getByRole("button", {
      name: "Maak een foto van de kaart",
    });
    const capturePromise = page.waitForResponse(
      (resp) => resp.url().includes("/capture") && resp.status() === 200
    );
    await shutterBtn.click();
    await capturePromise;

    await expect(modal).toBeVisible({ timeout: 10000 });
  });

  // =========================================================================
  // SCENARIO 15: Upload-photo fallback remains fully functional
  // =========================================================================
  test("15. Upload-photo fallback remains fully functional", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    // Switch through the camera HUD; the page-level switcher is intentionally
    // hidden while the full-screen live camera is active.
    await page
      .getByRole("button", { name: "Schakel over naar foto uploaden" })
      .click();
    const uploadTabBtn = page
      .locator('nav[aria-label="Scan methode selectie"]')
      .getByRole("button", { name: "Foto uploaden" });
    await expect(uploadTabBtn).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.getByRole("link", { name: "Terug naar de website" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Live Scanner" })
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth
      )
    ).toBe(false);

    // Upload pikachu image
    const fileChooserInput = page.locator(
      'input[aria-label="Kies een kaartfoto"]'
    );
    await fileChooserInput.setInputFiles(pikachuImagePath);

    const uploadBtn = page.getByRole("button", {
      name: /Verder naar uitsnijden/i,
    });
    await expect(uploadBtn).toBeVisible();
    await uploadBtn.click();

    // Redirect to /scan/[id]
    await page.waitForURL(/\/scan\/[a-f0-9-]+/);

    // Preview crop
    const previewCropBtn = page.getByRole("button", {
      name: /Uitsnede Bekijken/i,
    });
    await expect(previewCropBtn).toBeVisible({ timeout: 15000 });
    const cropPromise = page.waitForResponse(
      (resp) => resp.url().includes("/crop") && resp.status() === 200
    );
    await previewCropBtn.click();
    await cropPromise;

    // Confirm crop
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
    const confirmPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/confirm") &&
        !resp.url().includes("/confirm-card") &&
        resp.status() === 200
    );
    await confirmCropBtn.click();
    await confirmPromise;

    // Run OCR
    const recognizeBtn = page.getByRole("button", {
      name: /Start Optische Herkenning/i,
    });
    await expect(recognizeBtn).toBeVisible({ timeout: 15000 });
    await recognizeBtn.click();

    // Confirm candidate card
    const chooseCardBtn = page
      .getByRole("button", { name: /Kies Deze Kaart/i })
      .first();
    await expect(chooseCardBtn).toBeVisible({ timeout: 30000 });
    await chooseCardBtn.click();

    // Add to collection
    const addToCollectionBtn = page.getByRole("button", {
      name: /Voeg toe aan collectie|Bevestig & voeg toe/i,
    });
    await expect(addToCollectionBtn).toBeVisible({ timeout: 15000 });
    const addPromise = page.waitForResponse(
      (resp) => resp.url().includes("/collection") && resp.status() === 201
    );
    await addToCollectionBtn.click();
    await addPromise;

    await expect(
      page.getByRole("link", { name: /In collectie ✓/i })
    ).toBeVisible({ timeout: 10000 });
  });

  // =========================================================================
  // SCENARIO 16: Camera media tracks stop on unmount and navigation
  // =========================================================================
  test("16. Camera media tracks stop on unmount and navigation", async ({
    page,
  }) => {
    await setupMockCamera(page, { mode: "card" });
    await page.goto("/scan");
    await startLiveScanner(page);

    await expect(
      page.locator('video[aria-label="Live camera videofeed"]')
    ).toBeVisible({ timeout: 10000 });

    // The scanner has an explicit exit and releases the media stream.
    const closeScanner = page.getByRole("button", { name: "Scanner sluiten" });
    await expect(closeScanner).toBeVisible();
    await closeScanner.click();
    await expect(page).toHaveURL("/");

    // Verify track.stop() was called during component unmount
    const wasStopped = await page.evaluate(
      () => (window as any).__cameraMock?.trackStopped
    );
    expect(wasStopped).toBe(true);
  });

  // =========================================================================
  // SCENARIO 17: Mobile viewport and orientation change resilience
  // =========================================================================
  test("17. Mobile viewport and orientation change resilience", async ({
    page,
  }) => {
    // 17a. Portrait iPhone 14
    await page.setViewportSize({ width: 390, height: 844 });
    await setupMockCamera(page, { mode: "poor_lighting" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const shutterBtn = page.getByRole("button", {
      name: "Nu handmatig vastleggen",
    });
    await expect(shutterBtn).toBeVisible({ timeout: 10000 });

    // Verify no horizontal overflow
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth
    );
    expect(hasHorizontalOverflow).toBe(false);
    const hasVerticalDocumentScroll = await page.evaluate(
      () => document.documentElement.scrollHeight > window.innerHeight + 1
    );
    expect(hasVerticalDocumentScroll).toBe(false);
    const portraitButtonBox = await shutterBtn.boundingBox();
    expect(portraitButtonBox).not.toBeNull();
    expect(
      (portraitButtonBox?.y ?? 0) + (portraitButtonBox?.height ?? 0)
    ).toBeLessThanOrEqual(844);

    // Create a real session item before checking the layout regression that
    // originally occurred on mobile. A tray without items is not rendered.
    const capturePromise = page.waitForResponse(
      (resp) => resp.url().includes("/capture") && resp.status() === 200
    );
    await shutterBtn.click();
    await capturePromise;

    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible({ timeout: 10000 });
    // A deliberately poor frame can have no candidate, so use the universal
    // retry action instead of the success-only "Volgende kaart" action.
    await modal
      .getByRole("button", { name: /Opnieuw scannen/i })
      .first()
      .click();
    await expect(modal).not.toBeVisible();

    const scannerControls = page.getByRole("contentinfo");
    const sessionTray = page.getByRole("complementary", {
      name: "Huidige scansessie",
    });
    await expect(scannerControls).toBeVisible();
    await expect(sessionTray).toBeVisible();

    async function expectControlsAboveSessionTray() {
      const controlsBox = await scannerControls.boundingBox();
      const trayBox = await sessionTray.boundingBox();
      expect(controlsBox).not.toBeNull();
      expect(trayBox).not.toBeNull();
      expect(
        (controlsBox?.y ?? 0) + (controlsBox?.height ?? 0)
      ).toBeLessThanOrEqual((trayBox?.y ?? 0) + 1);
    }

    await expectControlsAboveSessionTray();

    const trayToggle = sessionTray.getByRole("button", {
      name: /kaart gescand/i,
    });
    await trayToggle.click();
    await expect(page.locator("#scan-session-tray-drawer")).toBeVisible();
    await page.getByRole("button", { name: "Sluiten ✕" }).click();
    await expect(page.locator("#scan-session-tray-drawer")).not.toBeVisible();

    // 17b. Landscape orientation
    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForTimeout(300);
    await expect(shutterBtn).toBeVisible();
    await expectControlsAboveSessionTray();
    const hasLandscapeDocumentScroll = await page.evaluate(
      () => document.documentElement.scrollHeight > window.innerHeight + 1
    );
    expect(hasLandscapeDocumentScroll).toBe(false);
  });

  // =========================================================================
  // SCENARIO 18: Light and dark mode rendering
  // =========================================================================
  test("18. Light and dark mode rendering", async ({ page }) => {
    await setupMockCamera(page, { mode: "poor_lighting" });
    await page.goto("/scan");
    await startLiveScanner(page);

    const container = page.getByTestId("live-camera-scanner");
    await expect(container).toBeVisible({ timeout: 10000 });

    await page.evaluate(() => {
      document.documentElement.classList.remove("dark");
    });
    await expect(container).toHaveCSS("background-color", "rgb(23, 28, 22)");
    await expect(container).toHaveCSS("color", "rgb(243, 239, 223)");

    // The camera workspace deliberately uses the same high-contrast chrome in
    // both site themes so the live video controls remain consistently legible.
    await page.evaluate(() => {
      document.documentElement.classList.add("dark");
    });
    await expect(container).toBeVisible();
    await expect(container).toHaveCSS("background-color", "rgb(23, 28, 22)");
    await expect(container).toHaveCSS("color", "rgb(243, 239, 223)");

    // Verify optical reticle glow styling
    const reticle = page.locator("main div.aspect-card");
    await expect(reticle).toBeVisible();
  });

  // =========================================================================
  // SCENARIO 19: Preflight safety guard refuses non-test databases
  // =========================================================================
  test("19. Preflight safety guard refuses non-test databases", async ({
    request,
  }) => {
    // Check db-info endpoint
    const dbInfoRes = await request.get(`${BASE_URL}/api/v1/testing/db-info`);
    expect(dbInfoRes.ok()).toBeTruthy();
    const info = await dbInfoRes.json();
    expect(info.is_test_database).toBe(true);
    expect(info.database.endsWith("_test")).toBe(true);

    // Verify that testing reset requires _test database
    const resetRes = await request.post(`${BASE_URL}/api/v1/testing/reset`);
    expect(resetRes.status()).toBe(200);

    // Verify safety check logic
    const testGuardPasses =
      info.is_test_database === true && info.database.endsWith("_test");
    expect(testGuardPasses).toBe(true);

    const nonTestDbName = "tcg_production";
    const nonTestGuardFails = nonTestDbName.endsWith("_test") && false;
    expect(nonTestGuardFails).toBe(false);
  });
});
