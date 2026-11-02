/**
 * Card Framing & Quality Analysis Engine
 * Phase 7: Live Scan & Go - Pokémon TCG Scanner
 *
 * Provides client-side, bounded real-time analysis of video frames to assess:
 * - Exposure / Mean Luminance (ITU-R BT.601)
 * - Specular Glare / Hotspots
 * - Sharpness / Blur via discrete Laplacian variance
 * - Frame Motion Stability via Mean Absolute Difference (MAD)
 * - Framing & Aspect Ratio check (~0.7159 portrait for Pokémon TCG)
 * - Stability tracking & cooldown timers to govern automatic capture
 */

import { QualityStatus, QUALITY_FEEDBACK } from "./types.ts";
import type {
  ImageDataLike,
  QualityAnalysisResult,
  QualityAnalyzerOptions,
  QualityMetrics,
  StabilityEvaluation,
} from "./types.ts";

export const DEFAULT_ANALYZER_OPTIONS: Required<QualityAnalyzerOptions> = {
  minLuminance: 32,
  maxLuminance: 230,
  maxGlareRatio: 0.06, // tolerate small foil highlights without blocking capture
  minSharpness: 35, // enough edge detail for OCR without fighting autofocus
  maxMotionMAD: 24.0, // discount normal handheld sensor noise and autofocus shifts
  targetAspectRatio: 63 / 88, // ~0.7159 (standard Pokémon TCG card)
  aspectRatioTolerance: 0.2,
};

/**
 * Converts an RGBA pixel buffer to ITU-R BT.601 grayscale float values [0, 255].
 */
export function rgbaToGrayscale(
  data: Uint8ClampedArray,
  width: number,
  height: number
): Float32Array {
  const pixelCount = width * height;
  const grayscale = new Float32Array(pixelCount);
  for (let i = 0, j = 0; i < pixelCount; i++, j += 4) {
    const r = data[j] ?? 0;
    const g = data[j + 1] ?? 0;
    const b = data[j + 2] ?? 0;
    grayscale[i] = 0.299 * r + 0.587 * g + 0.114 * b;
  }
  return grayscale;
}

/**
 * Calculates mean luminance over a grayscale buffer.
 */
export function computeMeanLuminance(grayscale: Float32Array): number {
  if (grayscale.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < grayscale.length; i++) {
    sum += grayscale[i] ?? 0;
  }
  return sum / grayscale.length;
}

/**
 * Detects the ratio of specular reflection / glare pixels where R, G, and B
 * all exceed the saturation threshold (default 240).
 */
export function computeGlareRatio(
  data: Uint8ClampedArray,
  threshold: number = 240
): number {
  const totalPixels = data.length / 4;
  if (totalPixels === 0) return 0;

  let saturatedPixels = 0;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i] ?? 0;
    const g = data[i + 1] ?? 0;
    const b = data[i + 2] ?? 0;
    if (r >= threshold && g >= threshold && b >= threshold) {
      saturatedPixels++;
    }
  }
  return saturatedPixels / totalPixels;
}

/**
 * Computes sharpness as the variance of the discrete 3x3 Laplacian operator.
 * Kernel:
 *   [ 0,  1,  0 ]
 *   [ 1, -4,  1 ]
 *   [ 0,  1,  0 ]
 */
export function computeLaplacianVariance(
  grayscale: Float32Array,
  width: number,
  height: number
): number {
  if (width < 3 || height < 3) return 0;

  const validWidth = width - 2;
  const validHeight = height - 2;
  const validCount = validWidth * validHeight;

  let sum = 0;
  let sumSq = 0;

  for (let y = 1; y < height - 1; y++) {
    const rowOffset = y * width;
    const upOffset = (y - 1) * width;
    const downOffset = (y + 1) * width;

    for (let x = 1; x < width - 1; x++) {
      const center = grayscale[rowOffset + x] ?? 0;
      const left = grayscale[rowOffset + x - 1] ?? 0;
      const right = grayscale[rowOffset + x + 1] ?? 0;
      const up = grayscale[upOffset + x] ?? 0;
      const down = grayscale[downOffset + x] ?? 0;

      const laplacian = left + right + up + down - 4 * center;
      sum += laplacian;
      sumSq += laplacian * laplacian;
    }
  }

  const mean = sum / validCount;
  const variance = sumSq / validCount - mean * mean;
  return Math.max(0, variance);
}

/**
 * Calculates the Mean Absolute Difference (MAD) between two successive frames
 * to gauge user movement / camera wobble.
 */
export function computeFrameMAD(
  currGray: Float32Array,
  prevGray: Float32Array
): number {
  const length = Math.min(currGray.length, prevGray.length);
  if (length === 0) return 0;

  let sumDiff = 0;
  for (let i = 0; i < length; i++) {
    const curr = currGray[i] ?? 0;
    const prev = prevGray[i] ?? 0;
    sumDiff += Math.abs(curr - prev);
  }
  return sumDiff / length;
}

/**
 * Measures spatial motion while discounting uniform auto-exposure changes.
 * Phone cameras frequently adjust exposure and white balance while the card is
 * already still; treating that global brightness shift as motion made the
 * scanner oscillate on "Houd stil".
 */
export function computeExposureCompensatedMAD(
  currGray: Float32Array,
  prevGray: Float32Array
): number {
  const length = Math.min(currGray.length, prevGray.length);
  if (length === 0) return 0;

  let currSum = 0;
  let prevSum = 0;
  for (let i = 0; i < length; i++) {
    currSum += currGray[i] ?? 0;
    prevSum += prevGray[i] ?? 0;
  }
  const exposureDelta = (currSum - prevSum) / length;

  let residual = 0;
  for (let i = 0; i < length; i++) {
    residual += Math.abs(
      (currGray[i] ?? 0) - (prevGray[i] ?? 0) - exposureDelta
    );
  }
  return residual / length;
}

/**
 * Evaluates whether card framing matches the expected Pokémon card aspect ratio
 * and occupies sufficient area in the downscaled frame.
 */
export function estimateCardFraming(
  grayscale: Float32Array,
  width: number,
  height: number,
  targetRatio: number,
  tolerance: number
): { aspectRatio: number; isFramed: boolean; presenceScore: number } {
  if (width < 10 || height < 10) {
    return { aspectRatio: 1, isFramed: false, presenceScore: 0 };
  }

  // Build directional gradient maps and their projection profiles. A real card
  // must contribute four coherent outer boundaries. Merely finding scattered
  // texture is not sufficient: the reticle crop already has a card-like ratio,
  // which previously allowed busy backgrounds to trigger automatic capture.
  const hGrad = new Float32Array(width);
  const vGrad = new Float32Array(height);
  const gxMap = new Float32Array(width * height);
  const gyMap = new Float32Array(width * height);
  let gradientSum = 0;
  let gradientSamples = 0;

  for (let y = 1; y < height - 1; y++) {
    const row = y * width;
    for (let x = 1; x < width - 1; x++) {
      const gx = Math.abs(
        (grayscale[row + x + 1] ?? 0) - (grayscale[row + x - 1] ?? 0)
      );
      const gy = Math.abs(
        (grayscale[(y + 1) * width + x] ?? 0) -
          (grayscale[(y - 1) * width + x] ?? 0)
      );
      gxMap[row + x] = gx;
      gyMap[row + x] = gy;
      hGrad[x] = (hGrad[x] ?? 0) + gx;
      vGrad[y] = (vGrad[y] ?? 0) + gy;
      gradientSum += gx + gy;
      gradientSamples += 2;
    }
  }

  const strongestLine = (
    profile: Float32Array,
    start: number,
    end: number
  ): number => {
    let strongestIndex = start;
    let strongestValue = -1;
    for (let index = start; index <= end; index++) {
      const value = profile[index] ?? 0;
      if (value > strongestValue) {
        strongestValue = value;
        strongestIndex = index;
      }
    }
    return strongestIndex;
  };

  // Card edges should live in the outer 35% bands, leaving enough interior for
  // artwork and text while tolerating a card that does not perfectly fill the guide.
  const minX = strongestLine(
    hGrad,
    Math.floor(width * 0.03),
    Math.floor(width * 0.35)
  );
  const maxX = strongestLine(
    hGrad,
    Math.ceil(width * 0.65),
    Math.floor(width * 0.97)
  );
  const minY = strongestLine(
    vGrad,
    Math.floor(height * 0.03),
    Math.floor(height * 0.35)
  );
  const maxY = strongestLine(
    vGrad,
    Math.ceil(height * 0.65),
    Math.floor(height * 0.97)
  );

  const detectedW = Math.max(1, maxX - minX);
  const detectedH = Math.max(1, maxY - minY);
  const detectedRatio = detectedW / detectedH;

  const ratioDiff = Math.abs(detectedRatio - targetRatio);
  const fitsAspect = ratioDiff <= tolerance;

  // Card must occupy a useful part of the reticle without being just a small
  // background rectangle.
  const occupiesSufficientSize =
    detectedW >= width * 0.45 && detectedH >= height * 0.45;

  const meanGradient = gradientSum / Math.max(1, gradientSamples);
  const supportThreshold = Math.max(12, meanGradient * 1.35);
  const insetX = Math.max(1, Math.floor(detectedW * 0.04));
  const insetY = Math.max(1, Math.floor(detectedH * 0.04));

  const verticalSupport = (x: number): number => {
    let supported = 0;
    let samples = 0;
    for (let y = minY + insetY; y <= maxY - insetY; y++) {
      if ((gxMap[y * width + x] ?? 0) >= supportThreshold) supported++;
      samples++;
    }
    return supported / Math.max(1, samples);
  };

  const horizontalSupport = (y: number): number => {
    let supported = 0;
    let samples = 0;
    for (let x = minX + insetX; x <= maxX - insetX; x++) {
      if ((gyMap[y * width + x] ?? 0) >= supportThreshold) supported++;
      samples++;
    }
    return supported / Math.max(1, samples);
  };

  const boundarySupports = [
    verticalSupport(minX),
    verticalSupport(maxX),
    horizontalSupport(minY),
    horizontalSupport(maxY),
  ];
  const averageSupport =
    boundarySupports.reduce((sum, value) => sum + value, 0) /
    boundarySupports.length;
  const weakestSupport = Math.min(...boundarySupports);

  // Require every side to be visible. This deliberately favours a missed auto
  // capture over photographing a shelf, desk, or monitor with no card present.
  const hasCoherentBoundary = averageSupport >= 0.42 && weakestSupport >= 0.24;
  const presenceScore = Math.max(
    0,
    Math.min(1, averageSupport * 0.8 + weakestSupport * 0.2)
  );

  return {
    aspectRatio: detectedRatio,
    isFramed: fitsAspect && occupiesSufficientSize && hasCoherentBoundary,
    presenceScore,
  };
}

/**
 * Analyzes a single frame's pixel buffer and produces actionable quality feedback.
 *
 * Evaluation Priority:
 * 1. Motion / Instability -> "Houd stil"
 * 2. Poor Lighting / Underexposed or Overexposed -> "Meer licht nodig"
 * 3. Specular Glare / Reflection -> "Minder weerspiegeling"
 * 4. Blurriness / Out of Focus -> "Dichterbij houden"
 * 5. Card Framing / Off Center -> "Plaats de kaart in het kader"
 * 6. Ready -> "Kaart gereed"
 */
export function analyzeCardFrame(
  currData: ImageDataLike,
  prevData?: ImageDataLike | null,
  options?: QualityAnalyzerOptions
): QualityAnalysisResult {
  const opts: Required<QualityAnalyzerOptions> = {
    ...DEFAULT_ANALYZER_OPTIONS,
    ...options,
  };

  const { width, height, data } = currData;
  const currGray = rgbaToGrayscale(data, width, height);
  const luminance = computeMeanLuminance(currGray);
  const glareRatio = computeGlareRatio(data);
  const sharpness = computeLaplacianVariance(currGray, width, height);

  let motionMAD = 0;
  if (prevData && prevData.width === width && prevData.height === height) {
    const prevGray = rgbaToGrayscale(prevData.data, width, height);
    motionMAD = computeExposureCompensatedMAD(currGray, prevGray);
  }

  const framing = estimateCardFraming(
    currGray,
    width,
    height,
    opts.targetAspectRatio,
    opts.aspectRatioTolerance
  );

  const metrics: QualityMetrics = {
    luminance,
    glareRatio,
    sharpness,
    motionMAD,
    aspectRatio: framing.aspectRatio,
    aspectRatioMatch: framing.isFramed,
    cardPresenceScore: framing.presenceScore,
  };

  const now = Date.now();

  // 1. Motion stability check
  if (motionMAD > opts.maxMotionMAD) {
    return {
      status: QualityStatus.UNSTABLE,
      feedback: QUALITY_FEEDBACK[QualityStatus.UNSTABLE],
      isReady: false,
      metrics,
      timestamp: now,
    };
  }

  // 2. Lighting / exposure check
  if (luminance < opts.minLuminance || luminance > opts.maxLuminance) {
    return {
      status: QualityStatus.POOR_LIGHTING,
      feedback: QUALITY_FEEDBACK[QualityStatus.POOR_LIGHTING],
      isReady: false,
      metrics,
      timestamp: now,
    };
  }

  // 3. Specular glare check
  if (glareRatio > opts.maxGlareRatio) {
    return {
      status: QualityStatus.GLARE,
      feedback: QUALITY_FEEDBACK[QualityStatus.GLARE],
      isReady: false,
      metrics,
      timestamp: now,
    };
  }

  // 4. Sharpness check
  if (sharpness < opts.minSharpness) {
    return {
      status: QualityStatus.BLURRY,
      feedback: QUALITY_FEEDBACK[QualityStatus.BLURRY],
      isReady: false,
      metrics,
      timestamp: now,
    };
  }

  // 5. Framing check
  if (!framing.isFramed) {
    return {
      status: QualityStatus.OFF_CENTER,
      feedback: QUALITY_FEEDBACK[QualityStatus.OFF_CENTER],
      isReady: false,
      metrics,
      timestamp: now,
    };
  }

  // 6. All criteria met
  return {
    status: QualityStatus.READY,
    feedback: QUALITY_FEEDBACK[QualityStatus.READY],
    isReady: true,
    metrics,
    timestamp: now,
  };
}

/**
 * Convenience alias for analyzeCardFrame.
 */
export const analyzeCardQuality = analyzeCardFrame;

/**
 * Governs the auto-capture workflow by requiring K consecutive READY evaluations
 * and enforcing a cooldown timer after capture to prevent runaway capture loops.
 */
export class CardStabilityTracker {
  private readonly consecutiveReadyRequired: number;
  private readonly cooldownDurationMs: number;
  private consecutiveReadyCount: number = 0;
  private lastCaptureTimestamp: number = 0;

  constructor(consecutiveReadyRequired = 3, cooldownDurationMs = 2500) {
    this.consecutiveReadyRequired = Math.max(1, consecutiveReadyRequired);
    this.cooldownDurationMs = Math.max(0, cooldownDurationMs);
  }

  /**
   * Evaluates the latest frame result against stability and cooldown criteria.
   */
  public evaluate(
    result: QualityAnalysisResult,
    now: number = Date.now()
  ): StabilityEvaluation {
    const inCooldown = this.isInCooldown(now);

    if (result.status === QualityStatus.READY && !inCooldown) {
      this.consecutiveReadyCount++;
    } else {
      // Hysteresis: a single noisy autofocus or hand-held frame should not
      // erase all progress. Persistent poor frames still decay to zero fast.
      this.consecutiveReadyCount = Math.max(0, this.consecutiveReadyCount - 1);
    }

    const isReadyForCapture =
      !inCooldown &&
      this.consecutiveReadyCount >= this.consecutiveReadyRequired;

    return {
      isReadyForCapture,
      consecutiveReadyCount: this.consecutiveReadyCount,
      inCooldown,
      status: result.status,
      feedback: inCooldown ? "Kaart vastgelegd…" : result.feedback,
    };
  }

  /**
   * Records a successful capture event and begins the cooldown timer.
   */
  public markCaptured(now: number = Date.now()): void {
    this.lastCaptureTimestamp = now;
    this.consecutiveReadyCount = 0;
  }

  /**
   * Resets all internal counters and clears cooldown.
   */
  public reset(): void {
    this.consecutiveReadyCount = 0;
    this.lastCaptureTimestamp = 0;
  }

  /**
   * Checks whether the cooldown window is currently active.
   */
  public isInCooldown(now: number = Date.now()): boolean {
    if (this.lastCaptureTimestamp === 0) return false;
    return now - this.lastCaptureTimestamp < this.cooldownDurationMs;
  }

  /**
   * Current number of consecutive READY frames observed.
   */
  public getConsecutiveReadyCount(): number {
    return this.consecutiveReadyCount;
  }
}
