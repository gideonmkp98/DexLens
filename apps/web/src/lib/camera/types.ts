/**
 * Camera & Card Quality Analysis Type Definitions
 * Phase 7: Live Scan & Go - Pokémon TCG Scanner
 */

/**
 * Quality status of the evaluated camera frame.
 */
export enum QualityStatus {
  UNSTABLE = "UNSTABLE",
  BLURRY = "BLURRY",
  POOR_LIGHTING = "POOR_LIGHTING",
  GLARE = "GLARE",
  OFF_CENTER = "OFF_CENTER",
  READY = "READY",
}

/**
 * User-facing actionable guidance strings in Dutch for viewfinder overlay.
 */
export const QUALITY_FEEDBACK: Record<QualityStatus, string> = {
  [QualityStatus.UNSTABLE]: "Houd stil",
  [QualityStatus.BLURRY]: "Dichterbij houden",
  [QualityStatus.POOR_LIGHTING]: "Meer licht nodig",
  [QualityStatus.GLARE]: "Minder weerspiegeling",
  [QualityStatus.OFF_CENTER]: "Plaats de kaart in het kader",
  [QualityStatus.READY]: "Kaart gereed",
};

/**
 * Quantitative metrics computed during frame analysis.
 */
export interface QualityMetrics {
  /** Mean ITU-R BT.601 pixel luminance (0-255) */
  luminance: number;
  /** Fraction of pixels classified as specular glare (0-1) */
  glareRatio: number;
  /** Discrete Laplacian variance estimating sharpness (higher = sharper) */
  sharpness: number;
  /** Mean Absolute Difference (MAD) between consecutive frames (0-255) */
  motionMAD: number;
  /** Estimated aspect ratio (width / height) if contours detected */
  aspectRatio?: number;
  /** Whether framing fits within target aspect ratio tolerance */
  aspectRatioMatch?: boolean;
}

/**
 * Result of evaluating a single camera frame.
 */
export interface QualityAnalysisResult {
  status: QualityStatus;
  feedback: string;
  isReady: boolean;
  metrics: QualityMetrics;
  timestamp: number;
}

/**
 * Configuration options for the CardQualityAnalyzer engine.
 */
export interface QualityAnalyzerOptions {
  /** Minimum acceptable mean luminance (default: 40) */
  minLuminance?: number;
  /** Maximum acceptable mean luminance before overexposed (default: 220) */
  maxLuminance?: number;
  /** Maximum fraction of saturated specular reflection pixels (default: 0.04 -> 4%) */
  maxGlareRatio?: number;
  /** Minimum Laplacian variance for adequate card sharpness (default: 45) */
  minSharpness?: number;
  /** Maximum Mean Absolute Difference before motion flag (default: 12.0) */
  maxMotionMAD?: number;
  /** Target Pokémon card aspect ratio (63mm / 88mm ~ 0.7159) */
  targetAspectRatio?: number;
  /** Permissible aspect ratio deviation (default: 0.15) */
  aspectRatioTolerance?: number;
}

/**
 * State evaluated by the stability tracker for automatic capture.
 */
export interface StabilityEvaluation {
  isReadyForCapture: boolean;
  consecutiveReadyCount: number;
  inCooldown: boolean;
  status: QualityStatus;
  feedback: string;
}

/**
 * Camera error classification codes.
 */
export type CameraErrorCode =
  | "PERMISSION_DENIED"
  | "NO_CAMERA_HARDWARE"
  | "CAMERA_IN_USE"
  | "INSECURE_CONTEXT"
  | "UNSUPPORTED_BROWSER"
  | "OVERCONSTRAINED"
  | "UNKNOWN_ERROR";

/**
 * Normalized camera error description.
 */
export interface CameraError {
  code: CameraErrorCode;
  message: string;
  originalError?: unknown;
}

/**
 * Zoom capability range reported by the video track.
 */
export interface ZoomCapability {
  min: number;
  max: number;
  step: number;
}

/**
 * 2D bounding rectangle coordinates.
 */
export interface RectCoords {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Captured full-resolution image frame payload.
 */
export interface CapturedFrame {
  blob: Blob;
  dataUrl: string;
  width: number;
  height: number;
  timestamp: number;
}

/**
 * Minimal abstraction for pixel buffers compatible with browser ImageData and tests.
 */
export interface ImageDataLike {
  readonly data: Uint8ClampedArray;
  readonly width: number;
  readonly height: number;
}
