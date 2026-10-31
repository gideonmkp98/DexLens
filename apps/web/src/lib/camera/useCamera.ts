/**
 * Camera Management Hook
 * Phase 7: Live Scan & Go - Pokémon TCG Scanner
 *
 * Handles:
 * - Camera hardware negotiation via getUserMedia with mobile rear-camera priority & fallbacks
 * - Clean track lifecycle teardown and <video> disconnection
 * - Device enumeration and hotplugging ("devicechange")
 * - Torch / Flashlight and digital/optical zoom capabilities with safe, non-throwing guards
 * - Comprehensive error mapping (PermissionDenied, InsecureContext, CameraInUse, etc.)
 * - Display-to-intrinsic video coordinate mapping (object-fit aware)
 * - Full-resolution frame capture (JPEG Blob + dataUrl) and lightweight downscaled frame capture
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CameraError,
  CameraErrorCode,
  CapturedFrame,
  ImageDataLike,
  RectCoords,
  ZoomCapability,
} from "./types.ts";

export interface UseCameraOptions {
  /** Automatically start the camera stream upon mounting (default: true) */
  autoStart?: boolean;
  /** Preferred facing mode (default: "environment") */
  preferredFacingMode?: "environment" | "user";
  /** Specific video input device ID to start with */
  preferredDeviceId?: string;
  /** Callback fired whenever an error occurs */
  onError?: (error: CameraError) => void;
}

export interface UseCameraResult {
  videoRef: React.RefObject<HTMLVideoElement>;
  isStreaming: boolean;
  isLoading: boolean;
  error: CameraError | null;
  devices: MediaDeviceInfo[];
  activeDeviceId: string | null;
  hasTorch: boolean;
  isTorchOn: boolean;
  hasZoom: boolean;
  zoomRange: ZoomCapability | null;
  currentZoom: number;
  videoDimensions: { width: number; height: number };
  startCamera: (deviceId?: string) => Promise<boolean>;
  stopCamera: () => void;
  switchCamera: (deviceId: string) => Promise<boolean>;
  toggleTorch: (enabled?: boolean) => Promise<boolean>;
  setZoom: (zoomLevel: number) => Promise<boolean>;
  captureFrame: () => Promise<CapturedFrame>;
  captureDownscaledFrame: (
    targetWidth?: number,
    targetHeight?: number
  ) => ImageDataLike | null;
  mapDisplayToVideoCoords: (displayRect: RectCoords) => RectCoords;
  clearError: () => void;
}

/**
 * Normalizes browser DOM exceptions into typed CameraError structures with Dutch feedback.
 */
function mapCameraError(err: unknown): CameraError {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return {
      code: "INSECURE_CONTEXT",
      message:
        "Cameratoegang vereist een beveiligde HTTPS-verbinding of localhost.",
      originalError: err,
    };
  }

  if (err instanceof Error) {
    const name = err.name;
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      return {
        code: "PERMISSION_DENIED",
        message:
          "Cameratoegang is geweigerd. Geef toestemming via je browserinstellingen.",
        originalError: err,
      };
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return {
        code: "NO_CAMERA_HARDWARE",
        message: "Geen camera gevonden op dit apparaat.",
        originalError: err,
      };
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return {
        code: "CAMERA_IN_USE",
        message:
          "De camera is al in gebruik door een andere app of browsertabblad.",
        originalError: err,
      };
    }
    if (name === "OverconstrainedError") {
      return {
        code: "OVERCONSTRAINED",
        message:
          "De gewenste camera-instellingen of lens worden niet ondersteund.",
        originalError: err,
      };
    }
  }

  return {
    code: "UNKNOWN_ERROR",
    message:
      err instanceof Error
        ? err.message
        : "Er is een onbekende fout opgetreden bij het starten van de camera.",
    originalError: err,
  };
}

export function useCamera({
  autoStart = true,
  preferredFacingMode = "environment",
  preferredDeviceId,
  onError,
}: UseCameraOptions = {}): UseCameraResult {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const downscaledCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<CameraError | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [activeDeviceId, setActiveDeviceId] = useState<string | null>(
    preferredDeviceId ?? null
  );

  // Hardware capability state
  const [hasTorch, setHasTorch] = useState(false);
  const [isTorchOn, setIsTorchOn] = useState(false);
  const [hasZoom, setHasZoom] = useState(false);
  const [zoomRange, setZoomRange] = useState<ZoomCapability | null>(null);
  const [currentZoom, setCurrentZoom] = useState(1);

  // Dynamic intrinsic video dimensions
  const [videoDimensions, setVideoDimensions] = useState({
    width: 0,
    height: 0,
  });

  const clearError = useCallback(() => setError(null), []);

  /**
   * Refreshes the list of available videoinput hardware devices.
   */
  const enumerateVideoDevices = useCallback(async () => {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.enumerateDevices
    ) {
      return;
    }
    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = allDevices.filter((dev) => dev.kind === "videoinput");
      setDevices(videoInputs);
    } catch {
      // Non-fatal device enumeration failure
    }
  }, []);

  /**
   * Evaluates hardware capabilities (torch, zoom) on the active video track.
   */
  const inspectCapabilities = useCallback((track: MediaStreamTrack) => {
    try {
      // Cast track capabilities to extended shape supporting torch and zoom
      type ExtendedCapabilities = MediaTrackCapabilities & {
        torch?: boolean;
        zoom?: { min: number; max: number; step: number };
      };
      const capabilities: ExtendedCapabilities =
        typeof track.getCapabilities === "function"
          ? track.getCapabilities()
          : {};

      // Torch support
      const torchSupported = Boolean(capabilities.torch);
      setHasTorch(torchSupported);
      setIsTorchOn(false);

      // Zoom support
      if (
        capabilities.zoom &&
        typeof capabilities.zoom.min === "number" &&
        typeof capabilities.zoom.max === "number" &&
        capabilities.zoom.max > capabilities.zoom.min
      ) {
        setHasZoom(true);
        setZoomRange({
          min: capabilities.zoom.min,
          max: capabilities.zoom.max,
          step: capabilities.zoom.step || 0.1,
        });
        setCurrentZoom(capabilities.zoom.min);
      } else {
        setHasZoom(false);
        setZoomRange(null);
        setCurrentZoom(1);
      }
    } catch {
      setHasTorch(false);
      setHasZoom(false);
      setZoomRange(null);
    }
  }, []);

  /**
   * Completely stops all active media tracks and clears video element bindings.
   */
  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // Ignore track stop exceptions
        }
      });
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsStreaming(false);
    setIsLoading(false);
    setHasTorch(false);
    setIsTorchOn(false);
    setHasZoom(false);
    setZoomRange(null);
  }, []);

  /**
   * Starts or restarts the camera stream with progressive fallbacks.
   */
  const startCamera = useCallback(
    async (targetDeviceId?: string): Promise<boolean> => {
      // Environment guards
      if (typeof window === "undefined") return false;

      if (!window.isSecureContext) {
        const err: CameraError = {
          code: "INSECURE_CONTEXT",
          message:
            "Cameratoegang vereist een veilige HTTPS-verbinding of localhost.",
        };
        setError(err);
        onError?.(err);
        return false;
      }

      if (
        typeof navigator === "undefined" ||
        !navigator.mediaDevices?.getUserMedia
      ) {
        const err: CameraError = {
          code: "UNSUPPORTED_BROWSER",
          message:
            "Je browser ondersteunt helaas geen camera-toegang (getUserMedia).",
        };
        setError(err);
        onError?.(err);
        return false;
      }

      setIsLoading(true);
      setError(null);

      // Stop any existing stream first
      stopCamera();

      const deviceToUse = targetDeviceId ?? activeDeviceId;

      // 1. Primary constraint set: target device or ideal environment facingMode with 1080p ideal
      const primaryConstraints: MediaStreamConstraints = {
        audio: false,
        video: deviceToUse
          ? {
              deviceId: { exact: deviceToUse },
              width: { ideal: 1920 },
              height: { ideal: 1080 },
            }
          : {
              facingMode: { ideal: preferredFacingMode },
              width: { ideal: 1920 },
              height: { ideal: 1080 },
            },
      };

      let stream: MediaStream | null = null;

      try {
        stream = await navigator.mediaDevices.getUserMedia(primaryConstraints);
      } catch (primaryErr) {
        // 2. Fallback constraint set: relaxed constraints
        try {
          const fallbackConstraints: MediaStreamConstraints = {
            audio: false,
            video: { facingMode: { ideal: preferredFacingMode } },
          };
          stream =
            await navigator.mediaDevices.getUserMedia(fallbackConstraints);
        } catch {
          // 3. Ultimate fallback: unconstrained video
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              audio: false,
              video: true,
            });
          } catch (finalErr) {
            const mappedError = mapCameraError(finalErr || primaryErr);
            setError(mappedError);
            setIsLoading(false);
            onError?.(mappedError);
            return false;
          }
        }
      }

      if (!stream) {
        setIsLoading(false);
        return false;
      }

      streamRef.current = stream;
      const videoTrack = stream.getVideoTracks()[0];

      if (videoTrack) {
        inspectCapabilities(videoTrack);

        const trackSettings = videoTrack.getSettings?.();
        if (trackSettings?.deviceId) {
          setActiveDeviceId(trackSettings.deviceId);
        }
      }

      // Bind to video element
      if (videoRef.current) {
        const videoEl = videoRef.current;
        videoEl.srcObject = stream;
        videoEl.playsInline = true;
        videoEl.muted = true;

        try {
          await videoEl.play();
        } catch {
          // Auto-play might require user gesture, will play upon interaction
        }

        const handleMetadata = () => {
          setVideoDimensions({
            width: videoEl.videoWidth || 0,
            height: videoEl.videoHeight || 0,
          });
        };

        if (videoEl.readyState >= HTMLMediaElement.HAVE_METADATA) {
          handleMetadata();
        } else {
          videoEl.addEventListener("loadedmetadata", handleMetadata, {
            once: true,
          });
        }
      }

      setIsStreaming(true);
      setIsLoading(false);

      // Re-enumerate devices after permissions have been granted
      await enumerateVideoDevices();

      return true;
    },
    [
      activeDeviceId,
      enumerateVideoDevices,
      inspectCapabilities,
      onError,
      preferredFacingMode,
      stopCamera,
    ]
  );

  /**
   * Switches to a specific camera device ID.
   */
  const switchCamera = useCallback(
    async (deviceId: string): Promise<boolean> => {
      setActiveDeviceId(deviceId);
      return startCamera(deviceId);
    },
    [startCamera]
  );

  /**
   * Toggles the torch / flashlight without throwing unhandled exceptions.
   */
  const toggleTorch = useCallback(
    async (enabled?: boolean): Promise<boolean> => {
      if (!streamRef.current || !hasTorch) return false;

      const track = streamRef.current.getVideoTracks()[0];
      if (!track) return false;

      const targetState = enabled !== undefined ? enabled : !isTorchOn;

      try {
        type AdvancedConstraint = { advanced: Array<{ torch?: boolean }> };
        const constraints = {
          advanced: [{ torch: targetState }],
        } as unknown as MediaTrackConstraints;

        await track.applyConstraints(constraints);
        setIsTorchOn(targetState);
        return true;
      } catch {
        // Graceful failure - unsupported on this browser/track configuration
        return false;
      }
    },
    [hasTorch, isTorchOn]
  );

  /**
   * Adjusts hardware zoom safely clamped within supported bounds.
   */
  const setZoom = useCallback(
    async (zoomLevel: number): Promise<boolean> => {
      if (!streamRef.current || !hasZoom || !zoomRange) return false;

      const track = streamRef.current.getVideoTracks()[0];
      if (!track) return false;

      const clampedZoom = Math.min(
        Math.max(zoomLevel, zoomRange.min),
        zoomRange.max
      );

      try {
        const constraints = {
          advanced: [{ zoom: clampedZoom }],
        } as unknown as MediaTrackConstraints;

        await track.applyConstraints(constraints);
        setCurrentZoom(clampedZoom);
        return true;
      } catch {
        return false;
      }
    },
    [hasZoom, zoomRange]
  );

  /**
   * Captures a full-resolution still frame onto an offscreen canvas.
   * Returns a JPEG Blob and data URL for upload.
   */
  const captureFrame = useCallback(async (): Promise<CapturedFrame> => {
    const video = videoRef.current;
    if (
      !video ||
      video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
      video.videoWidth === 0
    ) {
      throw new Error(
        "Camera video is niet gereed voor opname. Wacht tot de videofeed actief is."
      );
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Kan geen 2D context alloceren voor frame capture.");
    }

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL("image/jpeg", 0.92);

    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (b) => {
          if (b) resolve(b);
          else reject(new Error("Mislukt om JPEG blob te genereren."));
        },
        "image/jpeg",
        0.92
      );
    });

    return {
      blob,
      dataUrl,
      width: canvas.width,
      height: canvas.height,
      timestamp: Date.now(),
    };
  }, []);

  /**
   * Captures a lightweight downscaled frame (default: 320x240) into an offscreen canvas
   * for non-blocking client-side card quality analysis.
   */
  const captureDownscaledFrame = useCallback(
    (targetWidth = 320, targetHeight = 240): ImageDataLike | null => {
      const video = videoRef.current;
      if (
        !video ||
        video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
        video.videoWidth === 0 ||
        video.videoHeight === 0
      ) {
        return null;
      }

      if (!downscaledCanvasRef.current) {
        downscaledCanvasRef.current = document.createElement("canvas");
      }
      const canvas = downscaledCanvasRef.current;

      if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
        canvas.width = targetWidth;
        canvas.height = targetHeight;
      }

      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return null;

      ctx.drawImage(video, 0, 0, targetWidth, targetHeight);
      return ctx.getImageData(0, 0, targetWidth, targetHeight);
    },
    []
  );

  /**
   * Maps display coordinates (e.g. viewfinder guide rectangle) to intrinsic video coordinates,
   * accounting for CSS object-fit (cover or contain).
   */
  const mapDisplayToVideoCoords = useCallback(
    (displayRect: RectCoords): RectCoords => {
      const video = videoRef.current;
      if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
        return displayRect;
      }

      const displayW = video.clientWidth;
      const displayH = video.clientHeight;
      const videoW = video.videoWidth;
      const videoH = video.videoHeight;

      if (displayW === 0 || displayH === 0) {
        return displayRect;
      }

      // Default standard object-fit in mobile viewfinders is 'cover'
      const scale = Math.max(displayW / videoW, displayH / videoH);
      const renderedW = videoW * scale;
      const renderedH = videoH * scale;

      const offsetX = (renderedW - displayW) / 2;
      const offsetY = (renderedH - displayH) / 2;

      const intrinsicX = (displayRect.x + offsetX) / scale;
      const intrinsicY = (displayRect.y + offsetY) / scale;
      const intrinsicW = displayRect.width / scale;
      const intrinsicH = displayRect.height / scale;

      return {
        x: Math.max(0, Math.min(intrinsicX, videoW)),
        y: Math.max(0, Math.min(intrinsicY, videoH)),
        width: Math.min(intrinsicW, videoW),
        height: Math.min(intrinsicH, videoH),
      };
    },
    []
  );

  // Auto-start and teardown on mount / unmount
  useEffect(() => {
    if (autoStart) {
      void startCamera();
    }

    return () => {
      stopCamera();
    };
  }, [autoStart, startCamera, stopCamera]);

  // Handle device plugged / unplugged changes
  useEffect(() => {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.addEventListener
    ) {
      return;
    }

    const handleDeviceChange = () => {
      void enumerateVideoDevices();
    };

    navigator.mediaDevices.addEventListener("devicechange", handleDeviceChange);
    return () => {
      navigator.mediaDevices.removeEventListener(
        "devicechange",
        handleDeviceChange
      );
    };
  }, [enumerateVideoDevices]);

  // Handle window resize and orientation changes
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleResize = () => {
      if (videoRef.current) {
        setVideoDimensions({
          width: videoRef.current.videoWidth || 0,
          height: videoRef.current.videoHeight || 0,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    window.addEventListener("orientationchange", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("orientationchange", handleResize);
    };
  }, []);

  return {
    videoRef,
    isStreaming,
    isLoading,
    error,
    devices,
    activeDeviceId,
    hasTorch,
    isTorchOn,
    hasZoom,
    zoomRange,
    currentZoom,
    videoDimensions,
    startCamera,
    stopCamera,
    switchCamera,
    toggleTorch,
    setZoom,
    captureFrame,
    captureDownscaledFrame,
    mapDisplayToVideoCoords,
    clearError,
  };
}
