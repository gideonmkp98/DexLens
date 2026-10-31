/**
 * Standalone Unit Tests for Card Quality Analyzer
 * Phase 7: Live Scan & Go - Pokémon TCG Scanner
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  rgbaToGrayscale,
  computeMeanLuminance,
  computeGlareRatio,
  computeLaplacianVariance,
  computeFrameMAD,
  analyzeCardFrame,
  CardStabilityTracker,
  estimateCardFraming,
} from "./cardQualityAnalyzer.ts";
import { QualityStatus } from "./types.ts";
import type { ImageDataLike } from "./types.ts";

/**
 * Creates an ImageDataLike test buffer initialized with a fill RGBA color.
 */
function createTestBuffer(
  width: number,
  height: number,
  r = 0,
  g = 0,
  b = 0,
  a = 255
): ImageDataLike {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = r;
    data[i + 1] = g;
    data[i + 2] = b;
    data[i + 3] = a;
  }
  return { data, width, height };
}

/**
 * Creates a synthetic checkerboard pattern with sharp alternating edges.
 */
function createCheckerboardBuffer(
  width: number,
  height: number,
  blockSize = 8
): ImageDataLike {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      const isWhite =
        (Math.floor(x / blockSize) + Math.floor(y / blockSize)) % 2 === 0;
      const val = isWhite ? 200 : 40;
      data[idx] = val;
      data[idx + 1] = val;
      data[idx + 2] = val;
      data[idx + 3] = 255;
    }
  }
  return { data, width, height };
}

/**
 * Creates a synthetic card-shaped rectangle centered in the frame.
 */
function createSyntheticCardBuffer(
  frameW = 240,
  frameH = 320,
  cardW = 140,
  cardH = 196
): ImageDataLike {
  const data = new Uint8ClampedArray(frameW * frameH * 4);
  const startX = Math.floor((frameW - cardW) / 2);
  const startY = Math.floor((frameH - cardH) / 2);

  // Background: dark slate (30)
  for (let i = 0; i < data.length; i += 4) {
    data[i] = 30;
    data[i + 1] = 30;
    data[i + 2] = 30;
    data[i + 3] = 255;
  }

  // Card interior: well-lit with rich texture (mean ~130)
  for (let y = startY; y < startY + cardH; y++) {
    for (let x = startX; x < startX + cardW; x++) {
      const idx = (y * frameW + x) * 4;
      // High-frequency texture to ensure high sharpness
      const noise = ((x * 17 + y * 31) % 60) - 30;
      const val = Math.min(210, Math.max(50, 130 + noise));
      data[idx] = val;
      data[idx + 1] = val;
      data[idx + 2] = val;
      data[idx + 3] = 255;
    }
  }

  return { data, width: frameW, height: frameH };
}

describe("cardQualityAnalyzer Unit Tests", () => {
  describe("Grayscale & Exposure Detection", () => {
    test("converts RGBA to BT.601 luminance accurately", () => {
      // Pure red: 0.299 * 255 = 76.245
      const redBuf = createTestBuffer(2, 2, 255, 0, 0);
      const grayRed = rgbaToGrayscale(redBuf.data, 2, 2);
      assert.ok(Math.abs(grayRed[0]! - 76.245) < 0.1);

      // Pure green: 0.587 * 255 = 149.685
      const greenBuf = createTestBuffer(2, 2, 0, 255, 0);
      const grayGreen = rgbaToGrayscale(greenBuf.data, 2, 2);
      assert.ok(Math.abs(grayGreen[0]! - 149.685) < 0.1);

      // Pure blue: 0.114 * 255 = 29.07
      const blueBuf = createTestBuffer(2, 2, 0, 0, 255);
      const grayBlue = rgbaToGrayscale(blueBuf.data, 2, 2);
      assert.ok(Math.abs(grayBlue[0]! - 29.07) < 0.1);
    });

    test("flags underexposed frames with POOR_LIGHTING and Dutch guidance", () => {
      const darkBuffer = createTestBuffer(100, 100, 20, 20, 20);
      const result = analyzeCardFrame(darkBuffer);
      assert.equal(result.status, QualityStatus.POOR_LIGHTING);
      assert.equal(result.feedback, "Meer licht nodig");
      assert.equal(result.isReady, false);
      assert.ok(result.metrics.luminance < 40);
    });

    test("flags overexposed frames with POOR_LIGHTING", () => {
      const brightBuffer = createTestBuffer(100, 100, 235, 235, 235);
      const result = analyzeCardFrame(brightBuffer);
      assert.equal(result.status, QualityStatus.POOR_LIGHTING);
      assert.equal(result.isReady, false);
      assert.ok(result.metrics.luminance > 220);
    });

    test("computes correct mean luminance on heterogeneous pixels", () => {
      const buf = createTestBuffer(2, 1, 100, 100, 100);
      // Change second pixel to 200
      buf.data[4] = 200;
      buf.data[5] = 200;
      buf.data[6] = 200;
      const gray = rgbaToGrayscale(buf.data, 2, 1);
      const mean = computeMeanLuminance(gray);
      assert.ok(Math.abs(mean - 150) < 0.5);
    });
  });

  describe("Specular Glare Detection", () => {
    test("detects zero glare on standard non-reflective pixels", () => {
      const normalBuf = createTestBuffer(50, 50, 120, 120, 120);
      const glare = computeGlareRatio(normalBuf.data);
      assert.equal(glare, 0);
    });

    test("flags frames exceeding maxGlareRatio as GLARE with guidance", () => {
      // 100x100 = 10,000 pixels. Place 500 saturated pixels (5% > 4% threshold)
      const buf = createTestBuffer(100, 100, 120, 120, 120);
      for (let i = 0; i < 500 * 4; i += 4) {
        buf.data[i] = 250;
        buf.data[i + 1] = 250;
        buf.data[i + 2] = 250;
      }
      const glareRatio = computeGlareRatio(buf.data);
      assert.ok(glareRatio >= 0.05);

      const result = analyzeCardFrame(buf);
      assert.equal(result.status, QualityStatus.GLARE);
      assert.equal(result.feedback, "Minder weerspiegeling");
      assert.equal(result.isReady, false);
    });
  });

  describe("Laplacian Sharpness & Blur Calculation", () => {
    test("reports zero variance on a completely flat, blurry image", () => {
      const flatBuf = createTestBuffer(50, 50, 128, 128, 128);
      const gray = rgbaToGrayscale(flatBuf.data, 50, 50);
      const variance = computeLaplacianVariance(gray, 50, 50);
      assert.equal(variance, 0);

      const result = analyzeCardFrame(flatBuf);
      assert.equal(result.status, QualityStatus.BLURRY);
      assert.equal(result.feedback, "Dichterbij houden");
      assert.equal(result.isReady, false);
    });

    test("computes high Laplacian variance on high-contrast checkerboard", () => {
      const checker = createCheckerboardBuffer(64, 64, 4);
      const gray = rgbaToGrayscale(checker.data, 64, 64);
      const variance = computeLaplacianVariance(gray, 64, 64);
      assert.ok(
        variance > 100,
        `Expected variance > 100, but got: ${variance}`
      );
    });
  });

  describe("Motion & Frame Stability (MAD)", () => {
    test("calculates zero MAD on identical consecutive frames", () => {
      const buf1 = createTestBuffer(50, 50, 120, 120, 120);
      const buf2 = createTestBuffer(50, 50, 120, 120, 120);
      const g1 = rgbaToGrayscale(buf1.data, 50, 50);
      const g2 = rgbaToGrayscale(buf2.data, 50, 50);
      const mad = computeFrameMAD(g1, g2);
      assert.equal(mad, 0);
    });

    test("flags camera movement when MAD exceeds motion threshold", () => {
      const buf1 = createTestBuffer(50, 50, 100, 100, 100);
      const buf2 = createTestBuffer(50, 50, 125, 125, 125); // delta = 25 > 12
      const result = analyzeCardFrame(buf2, buf1);
      assert.equal(result.status, QualityStatus.UNSTABLE);
      assert.equal(result.feedback, "Houd stil");
      assert.equal(result.isReady, false);
      assert.ok(result.metrics.motionMAD > 12);
    });
  });

  describe("Card Framing & Aspect Ratio", () => {
    test("detects card framing on synthetic well-proportioned card", () => {
      // 140 / 196 = 0.71428 (near 63/88 = 0.7159)
      const synthCard = createSyntheticCardBuffer(240, 320, 140, 196);
      const gray = rgbaToGrayscale(synthCard.data, 240, 320);
      const framing = estimateCardFraming(gray, 240, 320, 63 / 88, 0.15);
      assert.ok(framing.isFramed);
      assert.ok(Math.abs(framing.aspectRatio - 63 / 88) < 0.15);
    });

    test("returns READY when all lighting, sharpness, and framing conditions pass", () => {
      const synthCard = createSyntheticCardBuffer(240, 320, 140, 196);
      const prevSynthCard = createSyntheticCardBuffer(240, 320, 140, 196);

      const result = analyzeCardFrame(synthCard, prevSynthCard);
      assert.equal(result.status, QualityStatus.READY);
      assert.equal(result.feedback, "Kaart gereed");
      assert.equal(result.isReady, true);
    });
  });

  describe("CardStabilityTracker & Cooldown State Machine", () => {
    test("requires consecutive READY evaluations before triggering capture", () => {
      const tracker = new CardStabilityTracker(3, 2000);
      const readyResult = {
        status: QualityStatus.READY,
        feedback: "Kaart gereed",
        isReady: true,
        metrics: { luminance: 120, glareRatio: 0, sharpness: 80, motionMAD: 2 },
        timestamp: 1000,
      };

      // Frame 1
      let eval1 = tracker.evaluate(readyResult, 1000);
      assert.equal(eval1.isReadyForCapture, false);
      assert.equal(eval1.consecutiveReadyCount, 1);

      // Frame 2
      let eval2 = tracker.evaluate(readyResult, 1150);
      assert.equal(eval2.isReadyForCapture, false);
      assert.equal(eval2.consecutiveReadyCount, 2);

      // Frame 3 (triggers capture!)
      let eval3 = tracker.evaluate(readyResult, 1300);
      assert.equal(eval3.isReadyForCapture, true);
      assert.equal(eval3.consecutiveReadyCount, 3);
      assert.equal(eval3.inCooldown, false);
    });

    test("resets consecutive counter if an unstable frame occurs", () => {
      const tracker = new CardStabilityTracker(3, 2000);
      const readyResult = {
        status: QualityStatus.READY,
        feedback: "Kaart gereed",
        isReady: true,
        metrics: { luminance: 120, glareRatio: 0, sharpness: 80, motionMAD: 2 },
        timestamp: 1000,
      };
      const unstableResult = {
        status: QualityStatus.UNSTABLE,
        feedback: "Houd stil",
        isReady: false,
        metrics: {
          luminance: 120,
          glareRatio: 0,
          sharpness: 80,
          motionMAD: 25,
        },
        timestamp: 1150,
      };

      tracker.evaluate(readyResult, 1000);
      tracker.evaluate(readyResult, 1150);
      assert.equal(tracker.getConsecutiveReadyCount(), 2);

      // Wobble occurs -> reset
      const evalReset = tracker.evaluate(unstableResult, 1300);
      assert.equal(evalReset.consecutiveReadyCount, 0);
      assert.equal(evalReset.isReadyForCapture, false);
    });

    test("enforces cooldown window preventing runaway capture loops", () => {
      const tracker = new CardStabilityTracker(3, 2500);
      const readyResult = {
        status: QualityStatus.READY,
        feedback: "Kaart gereed",
        isReady: true,
        metrics: { luminance: 120, glareRatio: 0, sharpness: 80, motionMAD: 2 },
        timestamp: 1000,
      };

      // 3 ready evaluations
      tracker.evaluate(readyResult, 1000);
      tracker.evaluate(readyResult, 1200);
      const eval3 = tracker.evaluate(readyResult, 1400);
      assert.equal(eval3.isReadyForCapture, true);

      // Mark captured at t=1400ms
      tracker.markCaptured(1400);
      assert.equal(tracker.isInCooldown(1400), true);
      assert.equal(tracker.getConsecutiveReadyCount(), 0);

      // Subsequent frame during cooldown (t=2000ms, elapsed 600ms < 2500ms)
      const evalCooldown = tracker.evaluate(readyResult, 2000);
      assert.equal(evalCooldown.inCooldown, true);
      assert.equal(evalCooldown.isReadyForCapture, false);
      assert.equal(evalCooldown.feedback, "Kaart vastgelegd…");

      // After cooldown expires (t=4000ms, elapsed 2600ms > 2500ms)
      assert.equal(tracker.isInCooldown(4000), false);
      const evalAfterCooldown = tracker.evaluate(readyResult, 4000);
      assert.equal(evalAfterCooldown.inCooldown, false);
      assert.equal(evalAfterCooldown.consecutiveReadyCount, 1);
    });

    test("reset clears all counts and cooldown status", () => {
      const tracker = new CardStabilityTracker(3, 2000);
      tracker.markCaptured(1000);
      assert.equal(tracker.isInCooldown(1500), true);

      tracker.reset();
      assert.equal(tracker.isInCooldown(1500), false);
      assert.equal(tracker.getConsecutiveReadyCount(), 0);
    });
  });
});
