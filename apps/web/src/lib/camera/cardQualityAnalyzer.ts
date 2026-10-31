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
  minLuminance: 40,
  maxLuminance: 220,
  maxGlareRatio: 0.04, // 4% of pixels saturated
  minSharpness: 45, // Laplacian variance
  maxMotionMAD: 12.0, // Mean absolute pixel difference
  targetAspectRatio: 63 / 88, // ~0.7159 (standard Pokémon TCG card)
  aspectRatioTolerance: 0.15,
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
 * Evaluates whether card framing matches the expected Pokémon card aspect ratio
 * and occupies sufficient area in the downscaled frame.
 */
export function estimateCardFraming(
  grayscale: Float32Array,
  width: number,
  height: number,
  targetRatio: number,
  tolerance: number
): { aspectRatio: number; isFramed: boolean } {
  if (width < 10 || height < 10) {
    return { aspectRatio: 1, isFramed: false };
  }

  // Compute horizontal and vertical gradient profiles
  const hGrad = new Float32Array(width);
  const vGrad = new Float32Array(height);

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
      hGrad[x] = (hGrad[x] ?? 0) + gx;
      vGrad[y] = (vGrad[y] ?? 0) + gy;
    }
  }

  // Find bounding thresholds covering significant gradient energy (15th to 85th percentile)
  let minX = Math.floor(width * 0.1);
  let maxX = Math.floor(width * 0.9);
  let minY = Math.floor(height * 0.1);
  let maxY = Math.floor(height * 0.9);

  // Scan inward for significant gradient activity
  const hThreshold = hGrad.reduce((acc, v) => acc + v, 0) / (width * 2 || 1);
  const vThreshold = vGrad.reduce((acc, v) => acc + v, 0) / (height * 2 || 1);

  for (let x = 0; x < width * 0.45; x++) {
    if ((hGrad[x] ?? 0) > hThreshold) {
      minX = x;
      break;
    }
  }
  for (let x = width - 1; x > width * 0.55; x--) {
    if ((hGrad[x] ?? 0) > hThreshold) {
      maxX = x;
      break;
    }
  }
  for (let y = 0; y < height * 0.45; y++) {
    if ((vGrad[y] ?? 0) > vThreshold) {
      minY = y;
      break;
    }
  }
  for (let y = height - 1; y > height * 0.55; y--) {
    if ((vGrad[y] ?? 0) > vThreshold) {
      maxY = y;
      break;
    }
  }

  const detectedW = Math.max(1, maxX - minX);
  const detectedH = Math.max(1, maxY - minY);
  const detectedRatio = detectedW / detectedH;

  const ratioDiff = Math.abs(detectedRatio - targetRatio);
  const fitsAspect = ratioDiff <= tolerance;

  // Card must occupy at least 35% of the frame dimensions to ensure sufficient resolution
  const occupiesSufficientSize =
    detectedW >= width * 0.35 && detectedH >= height * 0.35;

  return {
    aspectRatio: detectedRatio,
    isFramed: fitsAspect && occupiesSufficientSize,
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
    motionMAD = computeFrameMAD(currGray, prevGray);
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
      this.consecutiveReadyCount = 0;
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
