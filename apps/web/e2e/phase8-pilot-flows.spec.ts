import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import fs from "fs";
import path from "path";

const pikachuImagePath = path.resolve(__dirname, "fixtures/pikachu_photo.jpg");
const pikachuBase64 = fs.readFileSync(pikachuImagePath).toString("base64");
const pikachuDataUrl = `data:image/jpeg;base64,${pikachuBase64}`;

async function resetTestDatabaseSafely(request: APIRequestContext) {
  const resetRes = await request.post("/api/v1/testing/reset");
  if (!resetRes.ok()) {
    const body = await resetRes.text();
    throw new Error(
      `Failed to reset test database (status ${resetRes.status()}): ${body}`
    );
  }
}

async function setupMockCamera(page: Page) {
  await page.addInitScript(
    ({ pikaDataUrl }) => {
      (window as any).__cameraMock = {
        mode: "card",
        trackStopped: false,
      };

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

      const origToBlob = HTMLCanvasElement.prototype.toBlob;
      HTMLCanvasElement.prototype.toBlob = function (callback, type, quality) {
        if ((window as any).__pikachuBlob) {
          callback((window as any).__pikachuBlob);
          return;
        }
        origToBlob.call(this, callback, type, quality);
      };

      if (!navigator.mediaDevices) {
        (navigator as any).mediaDevices = {};
      }

      navigator.mediaDevices.enumerateDevices = async () => [
        {
          deviceId: "mock-back-camera-id",
          kind: "videoinput",
          label: "Back Camera 1 (Environment)",
          groupId: "group-1",
          toJSON: () => ({}),
        } as MediaDeviceInfo,
      ];

      navigator.mediaDevices.getUserMedia = async (constraints: any) => {
        const canvas = document.createElement("canvas");
        canvas.width = 1280;
        canvas.height = 720;
        const ctx = canvas.getContext("2d", { willReadFrequently: true })!;

        const img = new Image();
        img.src = pikaDataUrl;
        img.onload = () => {
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        };

        const stream = canvas.captureStream(15);
        const videoTrack = stream.getVideoTracks()[0];

        if (videoTrack) {
          (videoTrack as any).applyConstraints = async () => {};
          (videoTrack as any).getCapabilities = () => ({
            facingMode: ["environment"],
            focusMode: ["continuous", "auto"],
          });
          const origStop = videoTrack.stop.bind(videoTrack);
          videoTrack.stop = () => {
            (window as any).__cameraMock.trackStopped = true;
            origStop();
          };
        }

        const interval = setInterval(() => {
          if (!videoTrack || videoTrack.readyState === "ended") {
            clearInterval(interval);
            return;
          }
          try {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          } catch {
            // Handled
          }
        }, 100);

        return stream;
      };

      // Hook video prototype so video element reports readyState = 4 and valid dimensions
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
    { pikaDataUrl: pikachuDataUrl }
  );
}

async function startLiveScanner(page: Page) {
  const startButton = page.getByRole("button", { name: "Scanner starten" });
  await expect(startButton).toBeVisible({ timeout: 10000 });
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

test.describe("Phase 8: Early Access, Field Validation & Production Readiness", () => {
  test.beforeEach(async ({ request }) => {
    await resetTestDatabaseSafely(request);
  });

  test("1. PWA Manifest and Offline Fallback Page", async ({
    page,
    request,
  }) => {
    // Verify Web App Manifest
    const manifestResp = await request.get("/manifest.json");
    expect(manifestResp.status()).toBe(200);
    const manifest = await manifestResp.json();
    expect(manifest.name).toBe("DexLens — Pokémon TCG Scanner");
    expect(manifest.short_name).toBe("DexLens");
    expect(manifest.display).toBe("standalone");
    expect(manifest.theme_color).toBe("#20251f");
    expect(manifest.background_color).toBe("#20251f");
    expect(manifest.icons.length).toBeGreaterThanOrEqual(2);

    // Verify Offline Page
    await page.goto("/offline");
    await expect(page.locator("h1")).toContainText("DexLens is offline");
    await expect(
      page.getByRole("link", { name: "Opnieuw Proberen" })
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Naar Startpagina" })
    ).toBeVisible();
  });

  test("2. Scanner First-Time Onboarding Tips", async ({ page }) => {
    await setupMockCamera(page);
    await page.goto("/scan");

    // On first visit without localStorage set, the tips modal is automatically opened!
    const modal = page.getByRole("dialog", {
      name: "Scan Tips voor Verzamelaars",
    });
    await expect(modal).toBeVisible({ timeout: 10000 });
    await expect(modal).toContainText("Plaatsing in het kader");
    await expect(modal).toContainText("Licht & Weerspiegeling");
    await expect(modal).toContainText("Auto vs. Zelf");

    // Dismiss modal
    const dismissBtn = modal.getByRole("button", {
      name: "Begrepen & Start Scanner",
    });
    await dismissBtn.click();
    await expect(modal).not.toBeVisible();

    // Now test manual reopening via "Scan tips bekijken" button
    const tipsBtn = page
      .getByRole("button", { name: /Scan tips bekijken|Bekijk scan tips/i })
      .first();
    await expect(tipsBtn).toBeVisible({ timeout: 5000 });
    await tipsBtn.click();
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Sluit tips" }).click();
    await expect(modal).not.toBeVisible();
  });

  test("3. Privacy Analytics Non-Breaking Resilience", async ({ page }) => {
    await setupMockCamera(page);

    // Suppress onboarding popup for automated scan test
    await page.addInitScript(() => {
      localStorage.setItem("dexlens_scanner_tips_seen", "true");
    });

    // Intercept analytics events and intentionally abort/reject them
    let interceptedEvent = false;
    await page.route("**/api/v1/analytics/events", async (route) => {
      interceptedEvent = true;
      await route.abort("failed");
    });

    await page.goto("/scan");
    await startLiveScanner(page);

    // Switch to manual and capture
    const manualBtn = page.getByRole("button", { name: "Zelf" });
    await expect(manualBtn).toBeVisible({ timeout: 10000 });
    await manualBtn.click();
    await expect(manualBtn).toHaveAttribute("aria-pressed", "true");

    const shutterBtn = page.getByRole("button", {
      name: "Maak een foto van de kaart",
    });
    await expect(shutterBtn).toBeVisible();
    await shutterBtn.click();

    // Verify recognition and modal display still succeeds without breaking
    const matchModal = page.getByRole("dialog", {
      name: "Controleer deze suggestie",
    });
    await expect(matchModal).toBeVisible({ timeout: 25000 });
    expect(interceptedEvent).toBe(true);
  });

  test("4. Scan Feedback Submission & Confirmation", async ({ page }) => {
    await setupMockCamera(page);

    // Suppress onboarding popup for automated scan test
    await page.addInitScript(() => {
      localStorage.setItem("dexlens_scanner_tips_seen", "true");
    });

    await page.goto("/scan");
    await startLiveScanner(page);

    const manualBtn = page.getByRole("button", { name: "Zelf" });
    await expect(manualBtn).toBeVisible({ timeout: 10000 });
    await manualBtn.click();
    await expect(manualBtn).toHaveAttribute("aria-pressed", "true");

    const shutterBtn = page.getByRole("button", {
      name: "Maak een foto van de kaart",
    });
    await shutterBtn.click();

    const matchModal = page.getByRole("dialog", {
      name: "Controleer deze suggestie",
    });
    await expect(matchModal).toBeVisible({ timeout: 25000 });

    // Verify feedback widget inside modal
    const feedbackWidget = page.getByTestId("scan-feedback-widget");
    await expect(feedbackWidget).toBeVisible();
    await expect(feedbackWidget).toContainText("Klopt deze kaartmatch?");

    // Click "✓ Klopt"
    const confirmMatchBtn = feedbackWidget.getByRole("button", {
      name: "✓ Klopt",
    });
    await confirmMatchBtn.click();

    // Verify feedback confirmation banner appears
    const successBanner = page.getByTestId("scan-feedback-success");
    await expect(successBanner).toBeVisible({ timeout: 5000 });
    await expect(successBanner).toContainText("Bedankt voor je feedback!");
  });

  test("5. Pilot Diagnostics Dashboard Rendering", async ({ page }) => {
    await page.goto("/pilot-diagnostics");

    await expect(page.locator("h1")).toContainText(
      "Pilot & Diagnostiek Dashboard"
    );

    // Verify authentication / pilot secret gate appears
    await expect(page.getByText("Toegang Beveiligd")).toBeVisible({
      timeout: 10000,
    });
    const tokenInput = page.getByPlaceholder("Pilot Admin Secret");
    await expect(tokenInput).toBeVisible();

    // Unlock with pilot secret by submitting the form
    await tokenInput.fill("pilot-secret-dev");
    await tokenInput.press("Enter");

    // Verify dashboard metrics are now visible
    await expect(page.getByText("Totaal Scans")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Voltooiingsratio")).toBeVisible();
    await expect(page.getByText("Prestaties per Opnamemodus")).toBeVisible();
    await expect(page.getByText("Gebruikersfeedback Signalen")).toBeVisible();
  });
});
