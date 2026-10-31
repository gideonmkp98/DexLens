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
  StabilityEvaluation,
  useCamera,
} from "@/lib/camera";
import LiveScanMatchModal from "./LiveScanMatchModal";
import ScanSessionTray from "./ScanSessionTray";

export interface LiveCameraScannerProps {
  onSwitchToUpload?: () => void;
  className?: string;
}

export default function LiveCameraScanner({
  onSwitchToUpload,
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
    clearError,
  } = useCamera({
    autoStart: true,
    preferredFacingMode: "environment",
  });

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
  const [autoCaptureEnabled, setAutoCaptureEnabled] = useState<boolean>(true);
  const [qualityResult, setQualityResult] =
    useState<QualityAnalysisResult | null>(null);
  const [stability, setStability] = useState<StabilityEvaluation | null>(null);
  const [isCapturing, setIsCapturing] = useState<boolean>(false);
  const isCapturingRef = useRef<boolean>(false);
  const stabilityTrackerRef = useRef<CardStabilityTracker>(
    new CardStabilityTracker(3, 2200)
  );
  const prevFrameRef = useRef<ImageDataLike | null>(null);

  // Match modal
  const [activeCaptureResult, setActiveCaptureResult] =
    useState<LiveCaptureResponse | null>(null);
  const [isMatchModalOpen, setIsMatchModalOpen] = useState<boolean>(false);
  const [captureError, setCaptureError] = useState<string | null>(null);

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

  // Full-resolution capture handler
  const handleCapture = useCallback(async () => {
    if (isCapturingRef.current || isMatchModalOpen) return;
    isCapturingRef.current = true;
    setIsCapturing(true);
    setCaptureError(null);

    triggerHaptic();

    try {
      // 1. Capture high-res frame from video feed
      const frame = await captureFrame();

      // 2. Ensure active session
      let targetSessionId = sessionId;
      if (!targetSessionId) {
        const createdSession = await createScanSession();
        targetSessionId = createdSession.id;
        setSessionId(createdSession.id);
      }

      // 3. Send frame to live capture endpoint
      const result = await captureLiveScanFrame(targetSessionId, frame.blob);

      // 4. Mark stability tracker cooldown
      stabilityTrackerRef.current.markCaptured();

      // 5. Append to session items
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

      setSessionItems((prev) => [newItem, ...prev]);

      // 6. Open match modal with results
      setActiveCaptureResult(result);
      setIsMatchModalOpen(true);

      // Refresh full session in background
      if (targetSessionId) {
        void refreshSession(targetSessionId);
      }
    } catch (err) {
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
  }, [
    captureFrame,
    isMatchModalOpen,
    refreshSession,
    sessionId,
    triggerHaptic,
  ]);

  // Quality analysis polling loop (~180ms)
  useEffect(() => {
    if (!isStreaming) return;

    let timeoutId: NodeJS.Timeout | null = null;
    let isActive = true;

    const runAnalysisCycle = () => {
      if (!isActive) return;

      if (!isCapturingRef.current && !isMatchModalOpen) {
        const downscaled = captureDownscaledFrame(320, 240);
        if (downscaled) {
          const result = analyzeCardFrame(downscaled, prevFrameRef.current);
          prevFrameRef.current = downscaled;
          setQualityResult(result);

          const evalResult = stabilityTrackerRef.current.evaluate(result);
          setStability(evalResult);

          // Auto-capture trigger
          if (autoCaptureEnabled && evalResult.isReadyForCapture) {
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
    autoCaptureEnabled,
    captureDownscaledFrame,
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
      await switchCamera(nextDevice.deviceId);
    }
  };

  // Close match modal and instantly rearm live camera
  const handleNextCard = () => {
    setIsMatchModalOpen(false);
    setActiveCaptureResult(null);
    stabilityTrackerRef.current.reset();
  };

  // Retake current frame
  const handleRetake = () => {
    setIsMatchModalOpen(false);
    setActiveCaptureResult(null);
    stabilityTrackerRef.current.reset();
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
  const progressRatio = Math.min(1, consecutiveCount / 3);
  const ringRadius = 40;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringOffset = ringCircumference - progressRatio * ringCircumference;

  // Real-time HUD guidance feedback text and status
  const feedbackText =
    stability?.feedback ||
    qualityResult?.feedback ||
    "Plaats de kaart in het kader";
  const isCardReady = qualityResult?.status === QualityStatus.READY;

  return (
    <div
      className={`relative flex min-h-[580px] w-full select-none flex-col overflow-hidden bg-slate-950 text-white ${className}`}
      style={{
        height: "calc(100dvh - 75px)",
      }}
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
        className="bg-radial-gradient pointer-events-none absolute inset-0 from-transparent via-slate-950/30 to-slate-950/80"
        aria-hidden="true"
      />

      {/* Error Banner Overlay (if camera access fails) */}
      {cameraError && (
        <div
          role="alert"
          className="absolute inset-x-4 top-20 z-40 mx-auto max-w-md rounded-2xl border border-rose-500/50 bg-slate-950/95 p-5 text-center shadow-2xl backdrop-blur-md"
        >
          <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/20 text-rose-400">
            !
          </div>
          <h2 className="text-sm font-bold text-white">
            Cameratoegang niet mogelijk
          </h2>
          <p className="mt-1 text-xs text-slate-300">{cameraError.message}</p>
          <div className="mt-4 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => {
                clearError();
                void startCamera();
              }}
              className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-rose-500"
            >
              Opnieuw proberen
            </button>
            {onSwitchToUpload && (
              <button
                type="button"
                onClick={onSwitchToUpload}
                className="rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-xs font-bold text-white transition hover:bg-white/20"
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
          className="absolute inset-x-4 top-20 z-40 mx-auto max-w-md rounded-xl border border-amber-500/50 bg-amber-950/90 p-3 text-xs text-amber-200 shadow-xl backdrop-blur-sm"
        >
          {captureError}
        </div>
      )}

      {/* Top Bar: Controls HUD */}
      <header className="relative z-20 flex items-center justify-between px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        {/* Mode Switcher / Back Button */}
        <div className="flex items-center gap-2">
          {onSwitchToUpload ? (
            <button
              type="button"
              onClick={onSwitchToUpload}
              className="flex items-center gap-1.5 rounded-full border border-white/20 bg-slate-950/70 px-3 py-1.5 text-xs font-bold text-white shadow backdrop-blur-md transition hover:bg-white/15"
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
              <span>Foto uploaden</span>
            </button>
          ) : (
            <Link
              href="/"
              className="flex items-center gap-1.5 rounded-full border border-white/20 bg-slate-950/70 px-3 py-1.5 text-xs font-bold text-white shadow backdrop-blur-md transition hover:bg-white/15"
            >
              <span>← Terug</span>
            </Link>
          )}
        </div>

        {/* Action Controls: Auto-capture, Torch & Camera Switch */}
        <div className="flex items-center gap-2">
          {/* Auto-capture toggle pill */}
          <button
            type="button"
            onClick={() => setAutoCaptureEnabled((v) => !v)}
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold shadow backdrop-blur-md transition ${
              autoCaptureEnabled
                ? "border-emerald-400/50 bg-emerald-950/80 text-emerald-300"
                : "border-white/20 bg-slate-950/70 text-slate-400"
            }`}
            title="Schakel automatisch vastleggen in of uit"
            aria-pressed={autoCaptureEnabled}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                autoCaptureEnabled
                  ? "animate-pulse bg-emerald-400"
                  : "bg-slate-500"
              }`}
            />
            <span>Auto</span>
          </button>

          {/* Torch toggle (if supported by track) */}
          {hasTorch && (
            <button
              type="button"
              onClick={() => void toggleTorch()}
              className={`flex h-9 w-9 items-center justify-center rounded-full border shadow backdrop-blur-md transition ${
                isTorchOn
                  ? "border-amber-400/60 bg-amber-400 text-slate-950"
                  : "border-white/20 bg-slate-950/70 text-white hover:bg-white/15"
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
              className="flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-slate-950/70 text-white shadow backdrop-blur-md transition hover:bg-white/15"
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
        </div>
      </header>

      {/* Viewfinder Center: Optical Card Framing Reticle */}
      <main className="relative flex flex-1 items-center justify-center p-4">
        {/* Reticle bounding box (63mm x 88mm aspect ratio ~ 0.71) */}
        <div
          className={`relative aspect-card w-full max-w-[280px] rounded-3xl border-2 transition-colors duration-300 sm:max-w-[310px] ${
            isCardReady
              ? "border-emerald-400 shadow-[0_0_24px_rgba(52,211,153,0.35)]"
              : "border-sky-400/50 shadow-[0_0_20px_rgba(56,189,248,0.2)]"
          }`}
        >
          {/* Precision Optical Corner Brackets */}
          <div
            className={`absolute -left-1.5 -top-1.5 h-7 w-7 rounded-tl-xl border-l-4 border-t-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-sky-400"
            }`}
          />
          <div
            className={`absolute -right-1.5 -top-1.5 h-7 w-7 rounded-tr-xl border-r-4 border-t-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-sky-400"
            }`}
          />
          <div
            className={`absolute -bottom-1.5 -left-1.5 h-7 w-7 rounded-bl-xl border-b-4 border-l-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-sky-400"
            }`}
          />
          <div
            className={`absolute -bottom-1.5 -right-1.5 h-7 w-7 rounded-br-xl border-b-4 border-r-4 transition-colors duration-200 ${
              isCardReady ? "border-emerald-400" : "border-sky-400"
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
                  : "border-sky-400/50 bg-sky-400/10"
              }`}
            />
          </div>

          {/* Quality Feedback HUD Pill */}
          <div className="pointer-events-none absolute inset-x-0 -bottom-12 text-center">
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-bold shadow-lg backdrop-blur-md transition-all duration-200 ${
                isCardReady
                  ? "border-emerald-400/60 bg-emerald-950/85 text-emerald-300"
                  : qualityResult?.status === QualityStatus.UNSTABLE
                    ? "border-amber-400/60 bg-amber-950/85 text-amber-300"
                    : "border-sky-400/40 bg-slate-950/85 text-sky-200"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isCardReady
                    ? "animate-pulse bg-emerald-400"
                    : qualityResult?.status === QualityStatus.UNSTABLE
                      ? "animate-bounce bg-amber-400"
                      : "bg-sky-400"
                }`}
              />
              {feedbackText}
            </span>
          </div>
        </div>
      </main>

      {/* Bottom Shutter & Controls Section */}
      <footer className="relative z-20 flex flex-col items-center justify-center pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-3">
        {/* Primary Shutter Button with Auto-Capture Progress Ring */}
        <div className="relative flex items-center justify-center">
          {/* SVG Progress Ring */}
          <svg
            className="pointer-events-none -rotate-90"
            width={96}
            height={96}
            viewBox="0 0 96 96"
            aria-hidden="true"
          >
            <circle
              cx={48}
              cy={48}
              r={ringRadius}
              className="stroke-white/10"
              strokeWidth={5}
              fill="transparent"
            />
            {autoCaptureEnabled && (
              <circle
                cx={48}
                cy={48}
                r={ringRadius}
                className="stroke-emerald-400 transition-all duration-200"
                strokeWidth={5}
                strokeDasharray={ringCircumference}
                strokeDashoffset={ringOffset}
                strokeLinecap="round"
                fill="transparent"
              />
            )}
          </svg>

          {/* Physical Shutter Button */}
          <button
            type="button"
            onClick={handleCapture}
            disabled={isCapturing || !isStreaming}
            className="h-18 w-18 absolute flex items-center justify-center rounded-full border-4 border-slate-900 bg-white shadow-2xl transition hover:scale-105 active:scale-95 disabled:opacity-50"
            aria-label="Maak een foto van de kaart"
          >
            {isCapturing ? (
              <span className="border-3 h-6 w-6 animate-spin rounded-full border-emerald-600 border-t-transparent" />
            ) : (
              <div
                className={`h-14 w-14 rounded-full border-2 border-slate-900 transition-colors ${
                  isCardReady ? "bg-emerald-500" : "bg-red-600"
                }`}
              />
            )}
          </button>
        </div>

        <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-slate-400">
          {autoCaptureEnabled
            ? "Auto-capture actief"
            : "Druk om vast te leggen"}
        </p>
      </footer>

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
    </div>
  );
}
