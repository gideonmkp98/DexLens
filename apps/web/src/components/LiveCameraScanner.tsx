"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  captureLiveScanFrame,
  CollectionItem,
  completeScanSession,
  createScanSession,
  getScanSession,
  LiveCaptureResponse,
  ScanSessionDetailResponse,
  ScanSessionItemResponse,
} from "@/lib/api";
import {
  analyzeCardFrame,
  CardStabilityTracker,
  ImageDataLike,
  QualityAnalysisResult,
  QualityStatus,
  RectCoords,
  StabilityEvaluation,
  useCamera,
} from "@/lib/camera";
import LiveScanMatchModal from "./LiveScanMatchModal";
import ScanSessionTray from "./ScanSessionTray";
import ScannerOnboardingModal from "./ScannerOnboardingModal";
import { trackEvent } from "@/lib/analytics";

const PROCESSING_STAGES = [
  "Foto vastgelegd",
  "Kaart wordt uitgesneden",
  "Tekst wordt gelezen",
  "Catalogus wordt vergeleken",
  "Beste match bepalen",
] as const;
const AUTO_CAPTURE_READY_FRAMES = 5;

function createCaptureRequestKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface LiveCameraScannerProps {
  onSwitchToUpload?: () => void;
  onExit?: () => void;
  className?: string;
}

export default function LiveCameraScanner({
  onSwitchToUpload,
  onExit,
  className = "",
}: LiveCameraScannerProps) {
  // Camera hook
  const {
    videoRef,
    isStreaming,
    isLoading: isCameraLoading,
    error: cameraError,
    devices,
    activeDeviceId,
    hasTorch,
    isTorchOn,
    startCamera,
    switchCamera,
    toggleTorch,
    captureFrame,
    captureDownscaledFrame,
    mapDisplayToVideoCoords,
    clearError,
  } = useCamera({
    autoStart: false,
    preferredFacingMode: "environment",
  });

  const [cameraRequested, setCameraRequested] = useState<boolean>(false);

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<ScanSessionDetailResponse | null>(
    null
  );
  const [sessionItems, setSessionItems] = useState<ScanSessionItemResponse[]>(
    []
  );
  const [isCompletingSession, setIsCompletingSession] =
    useState<boolean>(false);

  // Quality analysis & auto-capture
  const [captureMode, setCaptureMode] = useState<"auto" | "manual">("auto");
  const [qualityResult, setQualityResult] =
    useState<QualityAnalysisResult | null>(null);
  const [stability, setStability] = useState<StabilityEvaluation | null>(null);
  const [isCapturing, setIsCapturing] = useState<boolean>(false);
  const isCapturingRef = useRef<boolean>(false);
  const stabilityTrackerRef = useRef<CardStabilityTracker>(
    new CardStabilityTracker(AUTO_CAPTURE_READY_FRAMES, 2200)
  );
  const prevFrameRef = useRef<ImageDataLike | null>(null);
  const reticleRef = useRef<HTMLDivElement | null>(null);
  const analysisPausedRef = useRef<boolean>(false);
  const analysisGraceUntilRef = useRef<number>(0);

  // Match modal
  const [activeCaptureResult, setActiveCaptureResult] =
    useState<LiveCaptureResponse | null>(null);
  const [isMatchModalOpen, setIsMatchModalOpen] = useState<boolean>(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [processingPreview, setProcessingPreview] = useState<string | null>(
    null
  );
  const [processingStage, setProcessingStage] = useState<number>(0);
  const lastCapturedBlobRef = useRef<Blob | null>(null);
  const lastIdempotencyKeyRef = useRef<string | null>(null);

  // Scanner onboarding tips modal state
  const [showTips, setShowTips] = useState<boolean>(false);

  useEffect(() => {
    try {
      const seen = localStorage.getItem("dexlens_scanner_tips_seen");
      if (!seen) {
        setShowTips(true);
      }
    } catch {
      // Non-fatal
    }
  }, []);

  const handleCloseTips = () => {
    setShowTips(false);
    try {
      localStorage.setItem("dexlens_scanner_tips_seen", "true");
    } catch {
      // Non-fatal
    }
  };

  // Initialize or fetch active scan session
  useEffect(() => {
    let isMounted = true;

    async function initSession() {
      try {
        const newSession = await createScanSession();
        if (isMounted) {
          setSessionId(newSession.id);
        }
      } catch {
        // Handled silently; capture will retry creating session if needed
      }
    }

    void initSession();

    return () => {
      isMounted = false;
    };
  }, []);

  // Update session detail
  const refreshSession = useCallback(async (id: string) => {
    try {
      const detail = await getScanSession(id);
      setSession(detail);
      setSessionItems(detail.items || []);
    } catch {
      // Non-fatal
    }
  }, []);

  // Haptic feedback trigger
  const triggerHaptic = useCallback(() => {
    if (
      typeof navigator !== "undefined" &&
      typeof navigator.vibrate === "function"
    ) {
      try {
        navigator.vibrate([50]);
      } catch {
        // Non-fatal
      }
    }
  }, []);

  const processCapturedBlob = useCallback(
    async (blob: Blob, idempotencyKey: string) => {
      const startTime = Date.now();
      let targetSessionId = sessionId;
      try {
        if (!targetSessionId) {
          const createdSession = await createScanSession();
          targetSessionId = createdSession.id;
          setSessionId(createdSession.id);
        }

        const result = await captureLiveScanFrame(
          targetSessionId,
          blob,
          idempotencyKey
        );
        stabilityTrackerRef.current.markCaptured();

        const newItem: ScanSessionItemResponse = {
          scan_id: result.scan.id,
          session_id: result.session_id,
          status: result.scan.status,
          crop_status: result.scan.crop_status || "confirmed",
          created_at: result.scan.created_at,
          image_url: result.scan.image_url,
          crop_image_url: result.scan.crop_image_url ?? null,
          best_match: result.best_match,
          candidates: result.candidates,
          confirmed_card: result.scan.confirmed_card ?? null,
          in_collection: result.in_collection,
          collection_quantity: result.collection_quantity,
          collection_item_id: result.collection_item_id,
        };

        setSessionItems((prev) => {
          if (prev.some((item) => item.scan_id === newItem.scan_id))
            return prev;
          return [newItem, ...prev];
        });
        setActiveCaptureResult(result);
        setIsMatchModalOpen(true);
        void refreshSession(targetSessionId);

        trackEvent("scan_processing_completed", {
          scan_id: result.scan.id,
          session_id: targetSessionId,
          capture_mode: captureMode,
          processing_duration_ms: Date.now() - startTime,
          confidence_state: result.scan.confidence_state,
          candidate_count: result.candidates.length,
          is_top_suggestion_selected: true,
        });
      } catch (err) {
        trackEvent("scan_processing_failed", {
          session_id: targetSessionId,
          capture_mode: captureMode,
          failure_category: err instanceof Error ? err.name : "unknown",
        });
        setCaptureError(
          err instanceof Error
            ? err.message
            : "Vastleggen van de kaart is niet gelukt. Probeer opnieuw."
        );
        stabilityTrackerRef.current.reset();
      } finally {
        setIsCapturing(false);
        isCapturingRef.current = false;
      }
    },
    [captureMode, refreshSession, sessionId]
  );

  const getReticleSourceRect = useCallback((): RectCoords | undefined => {
    const reticle = reticleRef.current;
    const video = videoRef.current;
    if (!reticle || !video) return undefined;

    const reticleBounds = reticle.getBoundingClientRect();
    const videoBounds = video.getBoundingClientRect();
    return mapDisplayToVideoCoords({
      x: reticleBounds.left - videoBounds.left,
      y: reticleBounds.top - videoBounds.top,
      width: reticleBounds.width,
      height: reticleBounds.height,
    });
  }, [mapDisplayToVideoCoords, videoRef]);

  // Capture the full-resolution pixels inside the visible card guide. Sending
  // the entire camera frame made shelves, screens and table edges compete with
  // the card detector and reduced OCR accuracy in real-world surroundings.
  const handleCapture = useCallback(async () => {
    if (isCapturingRef.current || isMatchModalOpen || !isStreaming) return;
    isCapturingRef.current = true;
    setIsCapturing(true);
    setProcessingStage(0);
    setCaptureError(null);
    triggerHaptic();

    trackEvent(
      captureMode === "auto"
        ? "auto_capture_triggered"
        : "manual_capture_triggered",
      {
        capture_mode: captureMode,
        session_id: sessionId,
      }
    );
    trackEvent("scan_processing_started", {
      capture_mode: captureMode,
      session_id: sessionId,
    });

    try {
      const frame = await captureFrame(getReticleSourceRect());
      const requestKey = createCaptureRequestKey();
      lastCapturedBlobRef.current = frame.blob;
      lastIdempotencyKeyRef.current = requestKey;
      setProcessingPreview(frame.dataUrl);
      await processCapturedBlob(frame.blob, requestKey);
    } catch (err) {
      setCaptureError(
        err instanceof Error
          ? err.message
          : "Vastleggen van de kaart is niet gelukt. Probeer opnieuw."
      );
      setIsCapturing(false);
      isCapturingRef.current = false;
    }
  }, [
    captureFrame,
    captureMode,
    getReticleSourceRect,
    isMatchModalOpen,
    isStreaming,
    processCapturedBlob,
    sessionId,
    triggerHaptic,
  ]);

  const retryLastCapture = useCallback(async () => {
    const blob = lastCapturedBlobRef.current;
    const requestKey = lastIdempotencyKeyRef.current;
    if (!blob || !requestKey || isCapturingRef.current) return;
    isCapturingRef.current = true;
    setIsCapturing(true);
    setProcessingStage(1);
    setCaptureError(null);
    await processCapturedBlob(blob, requestKey);
  }, [processCapturedBlob]);

  useEffect(() => {
    if (!isCapturing) return;
    const intervalId = window.setInterval(() => {
      setProcessingStage((current) =>
        Math.min(current + 1, PROCESSING_STAGES.length - 1)
      );
    }, 850);
    return () => window.clearInterval(intervalId);
  }, [isCapturing]);

  const handleStartCamera = useCallback(async () => {
    setCameraRequested(true);
    setCaptureError(null);
    analysisGraceUntilRef.current = Date.now() + 1600;
    trackEvent("scan_started", {
      capture_mode: captureMode,
      session_id: sessionId,
    });
    await startCamera();
  }, [captureMode, sessionId, startCamera]);

  useEffect(() => {
    if (isStreaming) {
      trackEvent("camera_permission_granted", { session_id: sessionId });
    }
  }, [isStreaming, sessionId]);

  useEffect(() => {
    if (cameraError) {
      trackEvent("camera_permission_denied", {
        session_id: sessionId,
        failure_category: cameraError.code,
      });
    }
  }, [cameraError, sessionId]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      analysisPausedRef.current = document.hidden;
      prevFrameRef.current = null;
      stabilityTrackerRef.current.reset();
      setStability(null);
      if (!document.hidden) {
        analysisGraceUntilRef.current = Date.now() + 900;
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () =>
      document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);

  // Quality analysis polling loop (~180ms)
  useEffect(() => {
    if (!isStreaming) return;

    let timeoutId: NodeJS.Timeout | null = null;
    let isActive = true;

    const runAnalysisCycle = () => {
      if (!isActive) return;

      if (
        !analysisPausedRef.current &&
        Date.now() >= analysisGraceUntilRef.current &&
        !isCapturingRef.current &&
        !isMatchModalOpen
      ) {
        const sourceRect = getReticleSourceRect();
        const downscaled = captureDownscaledFrame(180, 252, sourceRect);
        if (downscaled) {
          const result = analyzeCardFrame(downscaled, prevFrameRef.current);
          prevFrameRef.current = downscaled;
          setQualityResult(result);

          const evalResult = stabilityTrackerRef.current.evaluate(result);
          setStability(evalResult);

          // Auto-capture trigger
          if (captureMode === "auto" && evalResult.isReadyForCapture) {
            void handleCapture();
          }
        }
      }

      timeoutId = setTimeout(runAnalysisCycle, 180);
    };

    timeoutId = setTimeout(runAnalysisCycle, 180);

    return () => {
      isActive = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [
    captureMode,
    captureDownscaledFrame,
    getReticleSourceRect,
    handleCapture,
    isMatchModalOpen,
    isStreaming,
  ]);

  // Camera switcher
  const handleSwitchCamera = async () => {
    if (devices.length <= 1) return;
    const currentIndex = devices.findIndex(
      (d) => d.deviceId === activeDeviceId
    );
    const nextIndex = (currentIndex + 1) % devices.length;
    const nextDevice = devices[nextIndex];
    if (nextDevice?.deviceId) {
      analysisGraceUntilRef.current = Date.now() + 1600;
      prevFrameRef.current = null;
      await switchCamera(nextDevice.deviceId);
    }
  };

  // Close match modal and instantly rearm live camera
  const handleNextCard = () => {
    setIsMatchModalOpen(false);
    setActiveCaptureResult(null);
    setProcessingPreview(null);
    setCaptureError(null);
    lastCapturedBlobRef.current = null;
    lastIdempotencyKeyRef.current = null;
    stabilityTrackerRef.current.reset();
    analysisGraceUntilRef.current = Date.now() + 700;
  };

  // Retake current frame
  const handleRetake = () => {
    setIsMatchModalOpen(false);
    setActiveCaptureResult(null);
    setProcessingPreview(null);
    setCaptureError(null);
    lastCapturedBlobRef.current = null;
    lastIdempotencyKeyRef.current = null;
    stabilityTrackerRef.current.reset();
    analysisGraceUntilRef.current = Date.now() + 700;
  };

  // Complete session
  const handleCompleteSession = async () => {
    if (!sessionId || isCompletingSession) return;
    setIsCompletingSession(true);
    try {
      await completeScanSession(sessionId);
      // Start a fresh session
      const freshSession = await createScanSession();
      setSessionId(freshSession.id);
      setSession(null);
      setSessionItems([]);
    } catch {
      // Non-fatal
    } finally {
      setIsCompletingSession(false);
    }
  };

  // Review existing scan from tray
  const handleSelectTrayScan = (item: ScanSessionItemResponse) => {
    // Navigate to scan detail
    window.location.href = `/scan/${item.scan_id}`;
  };

  // Circular progress calculation for shutter ring
  const consecutiveCount = stability?.consecutiveReadyCount ?? 0;
  const progressRatio = Math.min(
    1,
    consecutiveCount / AUTO_CAPTURE_READY_FRAMES
  );
  const ringRadius = 40;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringOffset = ringCircumference - progressRatio * ringCircumference;

  // Real-time HUD guidance feedback text and status
  const feedbackText =
    stability?.feedback ||
    qualityResult?.feedback ||
    "Plaats de kaart in het kader";
  const isCardReady = qualityResult?.status === QualityStatus.READY;
  const hasSessionItems =
    sessionItems.length > 0 || (session?.total_scans ?? 0) > 0;

  return (
    <div
      data-testid="live-camera-scanner"
      className={`relative flex h-full min-h-0 w-full select-none flex-col overflow-hidden bg-[#171c16] text-[#f3efdf] ${className}`}
    >
      {/* Background Camera Video Stream */}
      <video
        ref={videoRef}
        className="absolute inset-0 h-full w-full object-cover"
        playsInline
        muted
        autoPlay
        aria-label="Live camera videofeed"
      />

      {/* Dimming vignette & dark contrast overlay */}
      <div
        className="bg-radial-gradient pointer-events-none absolute inset-0 from-transparent via-[#171c16]/30 to-[#10150f]/85"
        aria-hidden="true"
      />

      {!cameraRequested && !isStreaming && !cameraError && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#20251f] px-6 text-center">
          {onExit ? (
            <button
              type="button"
              onClick={onExit}
              className="absolute left-4 top-[max(1rem,env(safe-area-inset-top))] flex min-h-10 items-center gap-2 rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-3 text-xs font-black text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#eb6b5d]"
              aria-label="Scanner sluiten"
            >
              <span className="text-base leading-none" aria-hidden="true">
                ×
              </span>
              Terug
            </button>
          ) : (
            <Link
              href="/"
              className="absolute left-4 top-[max(1rem,env(safe-area-inset-top))] flex min-h-10 items-center gap-2 rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-3 text-xs font-black text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#eb6b5d]"
              aria-label="Scanner sluiten"
            >
              <span className="text-base leading-none" aria-hidden="true">
                ×
              </span>
              Terug
            </Link>
          )}
          <div className="max-w-sm">
            <span
              className="pokeball mx-auto mb-6 block h-16 w-16 rotate-[-12deg]"
              aria-hidden="true"
            />
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.24em] text-[#eb6b5d]">
              Live Scan &amp; Go
            </p>
            <h1 className="mt-3 text-2xl font-black tracking-tight">
              Klaar om je kaart te scannen?
            </h1>
            <p className="mt-3 text-sm leading-6 text-[#b6bbaa]">
              Je camera wordt pas gestart nadat je hieronder toestemming geeft.
              Alleen de foto die je vastlegt wordt verzonden.
            </p>
            <button
              type="button"
              onClick={() => void handleStartCamera()}
              disabled={isCameraLoading}
              className="mt-6 min-h-12 w-full rounded-[5px] border border-[#252923] bg-[#c6372e] px-5 py-3 text-sm font-black text-[#fff9ee] shadow-[4px_4px_0_#10150f] transition hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[6px_6px_0_#10150f] disabled:opacity-60"
            >
              {isCameraLoading ? "Camera starten…" : "Scanner starten"}
            </button>
            {onSwitchToUpload && (
              <button
                type="button"
                onClick={onSwitchToUpload}
                className="mt-3 min-h-11 w-full rounded-[5px] border border-[#4b5347] bg-[#2a3028] px-5 py-2.5 text-sm font-bold text-[#f3efdf]"
              >
                Liever een foto uploaden
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowTips(true)}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-[#f1ca53] hover:underline"
            >
              <span>Scan tips bekijken</span>
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>
      )}

      {/* Error Banner Overlay (if camera access fails) */}
      {cameraError && (
        <div
          role="alert"
          className="bg-[#20251f]/98 absolute inset-x-4 top-20 z-40 mx-auto max-w-md rounded-[5px] border border-[#eb6b5d] p-5 text-center shadow-[5px_5px_0_#10150f]"
        >
          <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-[3px] border border-[#eb6b5d]/50 bg-[#eb6b5d]/15 text-[#eb6b5d]">
            !
          </div>
          <h2 className="text-sm font-black text-[#f3efdf]">
            Cameratoegang niet mogelijk
          </h2>
          <p className="mt-1 text-xs text-[#b6bbaa]">{cameraError.message}</p>
          <div className="mt-4 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => {
                clearError();
                void handleStartCamera();
              }}
              className="rounded-[5px] border border-[#252923] bg-[#c6372e] px-4 py-2 text-xs font-black text-[#fff9ee] shadow-[2px_2px_0_#10150f] transition hover:bg-[#d94b40]"
            >
              Opnieuw proberen
            </button>
            {onSwitchToUpload && (
              <button
                type="button"
                onClick={onSwitchToUpload}
                className="rounded-[5px] border border-[#f3efdf]/25 bg-[#2a3028] px-4 py-2 text-xs font-bold text-[#f3efdf] transition hover:border-[#f1ca53]"
              >
                Foto uploaden
              </button>
            )}
          </div>
        </div>
      )}

      {/* Capture Transient Error Toast */}
      {captureError && (
        <div
          role="alert"
          className="bg-[#20251f]/98 absolute inset-x-4 top-20 z-[60] mx-auto max-w-md rounded-[5px] border border-[#f1ca53] p-4 text-sm text-[#f3efdf] shadow-[5px_5px_0_#10150f]"
        >
          <p className="font-bold">Verwerking niet gelukt</p>
          <p className="mt-1 text-xs text-[#d9d4c4]">{captureError}</p>
          <div className="mt-3 flex gap-2">
            {lastCapturedBlobRef.current && (
              <button
                type="button"
                onClick={() => void retryLastCapture()}
                className="rounded-[5px] border border-[#252923] bg-[#f1ca53] px-3 py-2 text-xs font-black text-[#252923] shadow-[2px_2px_0_#10150f]"
              >
                Opnieuw verwerken
              </button>
            )}
            <button
              type="button"
              onClick={handleRetake}
              className="rounded-[5px] border border-[#f3efdf]/25 bg-[#2a3028] px-3 py-2 text-xs font-bold"
            >
              Nieuwe foto
            </button>
          </div>
        </div>
      )}

      {/* Top Bar: Controls HUD */}
      {(cameraRequested || isStreaming || cameraError) && (
        <header className="relative z-20 flex items-center justify-between px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
          {/* Exit and alternate input */}
          <div className="flex items-center gap-2">
            {onExit ? (
              <button
                type="button"
                onClick={onExit}
                className="flex h-9 items-center gap-2 rounded-[5px] border border-[#f3efdf]/30 bg-[#171c16]/95 px-2.5 text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#eb6b5d] hover:text-white"
                aria-label="Scanner sluiten"
              >
                <span className="text-base leading-none" aria-hidden="true">
                  ×
                </span>
                <span className="text-[9px] font-black uppercase tracking-[0.1em]">
                  Terug
                </span>
              </button>
            ) : (
              <Link
                href="/"
                className="flex h-9 items-center gap-2 rounded-[5px] border border-[#f3efdf]/30 bg-[#171c16]/95 px-2.5 text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#eb6b5d]"
                aria-label="Scanner sluiten"
              >
                <span className="text-base leading-none" aria-hidden="true">
                  ×
                </span>
              </Link>
            )}
            {onSwitchToUpload ? (
              <button
                type="button"
                onClick={onSwitchToUpload}
                className="flex h-9 items-center gap-1.5 rounded-[5px] border border-[#f3efdf]/30 bg-[#20251f]/95 px-2.5 text-xs font-bold text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#f1ca53]"
                aria-label="Schakel over naar foto uploaden"
              >
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                  />
                </svg>
                <span className="text-[9px] font-black uppercase tracking-[0.1em]">
                  Upload
                </span>
              </button>
            ) : null}
          </div>

          {/* Action Controls: Auto-capture, Torch & Camera Switch */}
          <div className="flex items-center gap-2">
            {/* Explicit mode selector: both choices stay visible and predictable. */}
            <div
              role="group"
              aria-label="Opnamemodus"
              className="flex h-9 items-center rounded-[5px] border border-[#f3efdf]/30 bg-[#171c16]/95 p-0.5 shadow-[3px_3px_0_#10150f]"
            >
              <button
                type="button"
                onClick={() => {
                  setCaptureMode("auto");
                  stabilityTrackerRef.current.reset();
                  setStability(null);
                  trackEvent("capture_mode_changed", {
                    capture_mode: "auto",
                    session_id: sessionId,
                  });
                }}
                className={`h-7 rounded-[3px] px-2 font-mono text-[8px] font-black uppercase tracking-[0.1em] transition ${
                  captureMode === "auto"
                    ? "bg-emerald-400 text-[#10150f]"
                    : "text-[#b6bbaa] hover:text-[#f3efdf]"
                }`}
                aria-pressed={captureMode === "auto"}
              >
                Auto
              </button>
              <button
                type="button"
                onClick={() => {
                  setCaptureMode("manual");
                  stabilityTrackerRef.current.reset();
                  setStability(null);
                  trackEvent("capture_mode_changed", {
                    capture_mode: "manual",
                    session_id: sessionId,
                  });
                }}
                className={`h-7 rounded-[3px] px-2 font-mono text-[8px] font-black uppercase tracking-[0.1em] transition ${
                  captureMode === "manual"
                    ? "bg-[#f1ca53] text-[#10150f]"
                    : "text-[#b6bbaa] hover:text-[#f3efdf]"
                }`}
                aria-pressed={captureMode === "manual"}
              >
                Zelf
              </button>
            </div>

            {/* Torch toggle (if supported by track) */}
            {hasTorch && (
              <button
                type="button"
                onClick={() => void toggleTorch()}
                className={`flex h-9 w-9 items-center justify-center rounded-[5px] border shadow-[3px_3px_0_#10150f] transition ${
                  isTorchOn
                    ? "border-[#252923] bg-[#f1ca53] text-[#252923]"
                    : "border-[#f3efdf]/30 bg-[#20251f]/95 text-[#f3efdf] hover:border-[#f1ca53]"
                }`}
                aria-label={
                  isTorchOn ? "Zaklamp uitschakelen" : "Zaklamp inschakelen"
                }
                title="Zaklamp"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              </button>
            )}

            {/* Camera switcher (if multiple lenses available) */}
            {devices.length > 1 && (
              <button
                type="button"
                onClick={handleSwitchCamera}
                className="flex h-9 w-9 items-center justify-center rounded-[5px] border border-[#f3efdf]/30 bg-[#20251f]/95 text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#f1ca53]"
                aria-label="Wissel van camera"
                title="Camera wisselen"
              >
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
            )}

            {/* Onboarding Tips Button */}
            <button
              type="button"
              onClick={() => setShowTips(true)}
              className="flex h-9 items-center gap-1.5 rounded-[5px] border border-[#f3efdf]/30 bg-[#20251f]/95 px-2.5 text-xs font-bold text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:border-[#f1ca53]"
              aria-label="Bekijk scan tips"
              title="Scan tips"
            >
              <span className="font-mono text-xs font-bold text-[#f1ca53]">
                ?
              </span>
              <span className="hidden sm:inline">Tips</span>
            </button>
          </div>
        </header>
      )}

      {/* Viewfinder Center: Optical Card Framing Reticle */}
      <main className="relative flex min-h-0 flex-1 items-center justify-center px-4 py-2">
        {/* Reticle bounding box (63mm x 88mm aspect ratio ~ 0.71) */}
        <div
          ref={reticleRef}
          className={`relative aspect-card h-[min(54dvh,430px)] max-h-full max-w-[78vw] rounded-[10px] border-2 transition-colors duration-300 ${
            isCardReady
              ? "border-emerald-400 shadow-[0_0_24px_rgba(52,211,153,0.35)]"
              : "border-[#f1ca53]/60 shadow-[0_0_20px_rgba(241,202,83,0.18)]"
          }`}
        >
          <span className="absolute -top-7 left-0 rounded-[3px] bg-[#20251f]/95 px-2 py-1 font-mono text-[8px] font-bold uppercase tracking-[0.18em] text-[#f3efdf] shadow-[2px_2px_0_#10150f]">
            DexLens / frame 01
          </span>
          {/* Precision Optical Corner Brackets */}
          <div
            className={`absolute -left-1.5 -top-1.5 h-7 w-7 rounded-tl-xl border-l-4 border-t-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-[#f1ca53]"
            }`}
          />
          <div
            className={`absolute -right-1.5 -top-1.5 h-7 w-7 rounded-tr-xl border-r-4 border-t-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-[#f1ca53]"
            }`}
          />
          <div
            className={`absolute -bottom-1.5 -left-1.5 h-7 w-7 rounded-bl-xl border-b-4 border-l-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-[#f1ca53]"
            }`}
          />
          <div
            className={`absolute -bottom-1.5 -right-1.5 h-7 w-7 rounded-br-xl border-b-4 border-r-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-[#f1ca53]"
            }`}
          />

          {/* Central Target Crosshair */}
          <div
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
            aria-hidden="true"
          >
            <div
              className={`h-4 w-4 rounded-full border-2 transition-colors ${
                isCardReady
                  ? "border-emerald-400/70 bg-emerald-400/20"
                  : "border-[#f1ca53]/60 bg-[#f1ca53]/10"
              }`}
            />
          </div>

          {/* Quality Feedback HUD Pill */}
          <div className="pointer-events-none absolute inset-x-0 -bottom-12 text-center">
            <span
              className={`inline-flex items-center gap-2 rounded-[5px] border px-3.5 py-1.5 text-xs font-bold shadow-[3px_3px_0_#10150f] transition-all duration-200 ${
                isCardReady
                  ? "border-emerald-400/60 bg-[#20251f]/95 text-emerald-300"
                  : qualityResult?.status === QualityStatus.UNSTABLE
                    ? "border-[#f1ca53] bg-[#20251f]/95 text-[#f1ca53]"
                    : "border-[#f3efdf]/30 bg-[#20251f]/95 text-[#f3efdf]"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isCardReady
                    ? "animate-pulse bg-emerald-400"
                    : qualityResult?.status === QualityStatus.UNSTABLE
                      ? "animate-bounce bg-amber-400"
                      : "bg-[#f1ca53]"
                }`}
              />
              {feedbackText}
            </span>
          </div>
        </div>
      </main>

      {/* Bottom Shutter & Controls Section */}
      <footer
        className={`relative z-20 flex shrink-0 flex-col items-center justify-center px-4 pt-2 ${
          hasSessionItems
            ? "pb-1"
            : "pb-[max(0.75rem,env(safe-area-inset-bottom))]"
        }`}
      >
        <div className="w-full max-w-sm rounded-[7px] border border-[#f3efdf]/25 bg-[#171c16]/95 p-2.5 shadow-[4px_4px_0_#10150f]">
          {captureMode === "manual" ? (
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[5px] border border-[#f1ca53]/35 bg-[#20251f] text-[#f1ca53]">
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.8}
                  aria-hidden="true"
                >
                  <path d="M4 8.5h3l1.4-2h7.2l1.4 2h3v10H4z" />
                  <circle cx="12" cy="13.5" r="3.2" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[#f1ca53]">
                  Handmatige opname
                </p>
                <p className="text-xs font-black text-[#f3efdf]">
                  Druk wanneer je kaart goed staat
                </p>
              </div>
              <button
                type="button"
                onClick={handleCapture}
                disabled={isCapturing || !isStreaming}
                className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-[3px] border-[#f3efdf] bg-[#171c16] p-1 shadow-[3px_3px_0_#10150f] transition hover:scale-105 active:scale-95 disabled:opacity-50"
                aria-label="Maak een foto van de kaart"
              >
                <span className="h-full w-full rounded-full border border-[#fff9ee]/35 bg-[#c6372e]" />
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <div className="relative h-11 w-11 shrink-0 rounded-[5px] border border-emerald-400/35 bg-[#20251f]">
                  <svg
                    className="absolute inset-0 -rotate-90"
                    width={44}
                    height={44}
                    viewBox="0 0 96 96"
                    aria-hidden="true"
                  >
                    <circle
                      cx={48}
                      cy={48}
                      r={ringRadius}
                      className="stroke-[#f3efdf]/10"
                      strokeWidth={6}
                      fill="transparent"
                    />
                    <circle
                      cx={48}
                      cy={48}
                      r={ringRadius}
                      className="stroke-emerald-400 transition-all duration-200"
                      strokeWidth={6}
                      strokeDasharray={ringCircumference}
                      strokeDashoffset={ringOffset}
                      strokeLinecap="round"
                      fill="transparent"
                    />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-[9px] font-black text-emerald-300">
                    {Math.min(AUTO_CAPTURE_READY_FRAMES, consecutiveCount)}/
                    {AUTO_CAPTURE_READY_FRAMES}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-emerald-300">
                    Automatisch scannen
                  </p>
                  <p className="truncate text-xs font-black text-[#f3efdf]">
                    {isCardReady ? "Even stilhouden…" : feedbackText}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleCapture}
                  disabled={isCapturing || !isStreaming}
                  className="flex h-11 shrink-0 items-center gap-1.5 rounded-[5px] border border-[#f3efdf]/30 bg-[#2a3028] px-2.5 text-[9px] font-black uppercase tracking-[0.08em] text-[#f3efdf] transition hover:border-[#f1ca53] active:scale-95 disabled:opacity-50"
                  aria-label="Nu handmatig vastleggen"
                  title="Nu handmatig vastleggen"
                >
                  <span className="h-2.5 w-2.5 rounded-full border border-[#f3efdf] bg-[#c6372e]" />
                  Foto
                </button>
              </div>
              <div
                className="mt-2 grid gap-1"
                style={{
                  gridTemplateColumns: `repeat(${AUTO_CAPTURE_READY_FRAMES}, minmax(0, 1fr))`,
                }}
                aria-hidden="true"
              >
                {Array.from(
                  { length: AUTO_CAPTURE_READY_FRAMES },
                  (_, step) => (
                    <span
                      key={step}
                      className={`h-1 rounded-[1px] transition-colors ${
                        consecutiveCount > step
                          ? "bg-emerald-400"
                          : "bg-[#3b4338]"
                      }`}
                    />
                  )
                )}
              </div>
            </>
          )}
        </div>
        <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-[#b6bbaa]">
          {captureMode === "auto"
            ? "Alleen bij een duidelijk zichtbare kaart"
            : "Jij bepaalt het moment"}
        </p>
      </footer>

      {isCapturing && (
        <div
          className="absolute inset-0 z-[70] flex items-center justify-center bg-[#171c16]/95 px-6"
          role="status"
          aria-live="polite"
          aria-label={PROCESSING_STAGES[processingStage]}
        >
          <div className="w-full max-w-sm text-center">
            {processingPreview && (
              <div
                className="mx-auto aspect-card h-[min(46dvh,360px)] rounded-[8px] border border-[#f3efdf]/30 bg-cover bg-center shadow-[6px_6px_0_#10150f]"
                style={{ backgroundImage: `url(${processingPreview})` }}
                aria-hidden="true"
              />
            )}
            <div className="mx-auto mt-5 h-1.5 w-full overflow-hidden rounded-[2px] bg-[#f3efdf]/10">
              <div
                className="h-full rounded-[2px] bg-[#f1ca53] transition-[width] duration-500"
                style={{
                  width: `${((processingStage + 1) / PROCESSING_STAGES.length) * 100}%`,
                }}
              />
            </div>
            <p className="mt-3 text-base font-black text-[#f3efdf]">
              {PROCESSING_STAGES[processingStage]}
            </p>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-[#b6bbaa]">
              Blijf op deze pagina; je resultaat verschijnt automatisch.
            </p>
          </div>
        </div>
      )}

      {/* Bottom Floating Multi-Card Session Tray */}
      <ScanSessionTray
        session={session}
        items={sessionItems}
        onSelectScan={handleSelectTrayScan}
        onCompleteSession={handleCompleteSession}
        isCompleting={isCompletingSession}
      />

      {/* Match Confirmation Modal / Bottom Sheet */}
      <LiveScanMatchModal
        isOpen={isMatchModalOpen}
        captureResult={activeCaptureResult}
        onClose={handleNextCard}
        onRetake={handleRetake}
        onCardAddedToCollection={() => {
          if (sessionId) {
            void refreshSession(sessionId);
          }
        }}
      />

      {/* First-time / On-demand Scanner Onboarding Tips */}
      <ScannerOnboardingModal isOpen={showTips} onClose={handleCloseTips} />
    </div>
  );
}
