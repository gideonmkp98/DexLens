"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CornerSelector } from "@/components/CornerSelector";
import CardImage from "@/components/CardImage";
import {
  addScanToCollection,
  ApiError,
  CandidateMatchItem,
  CollectionItem,
  confirmCatalogCard,
  confirmCrop,
  CropCorners,
  cropScan,
  detectCard,
  getScan,
  getScanCollectionItem,
  getScanCropImageUrl,
  getScanImageUrl,
  recognizeCard,
  resetCatalogCardConfirmation,
  ScanResponse,
  searchCardCandidates,
} from "@/lib/api";

const DEFAULT_CORNERS: CropCorners = {
  top_left: { x: 0.12, y: 0.12 },
  top_right: { x: 0.88, y: 0.12 },
  bottom_right: { x: 0.88, y: 0.88 },
  bottom_left: { x: 0.12, y: 0.88 },
};

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

function formatDate(isoString?: string | null): string {
  if (!isoString) return "-";
  try {
    const d = new Date(isoString);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function ScanResultPage() {
  const params = useParams();
  const id = typeof params?.id === "string" ? params.id : "";

  // Track active scan id and request revisions to prevent race conditions
  const currentScanIdRef = useRef<string>(id);
  const selectionRevisionRef = useRef<number>(0);
  const activeDetectionIdRef = useRef<number>(0);
  const activePreviewIdRef = useRef<number>(0);
  const activeRecognitionIdRef = useRef<number>(0);
  const activeSearchIdRef = useRef<number>(0);
  const activeConfirmCardIdRef = useRef<number>(0);

  useEffect(() => {
    currentScanIdRef.current = id;
  }, [id]);

  // Scan and basic state
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Phase 4 interactive state
  const [corners, setCorners] = useState<CropCorners>(DEFAULT_CORNERS);
  const [rotation, setRotation] = useState<number>(0);
  const [isDetecting, setIsDetecting] = useState<boolean>(false);
  const [detectionMessage, setDetectionMessage] = useState<string | null>(null);
  const [isCropping, setIsCropping] = useState<boolean>(false);
  const [isConfirming, setIsConfirming] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);
  const [isEditingConfirmed, setIsEditingConfirmed] = useState<boolean>(false);

  // Phase 5 OCR and candidate matching state
  const [isRecognizing, setIsRecognizing] = useState<boolean>(false);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [isConfirmingCard, setIsConfirmingCard] = useState<boolean>(false);
  const [isResettingCard, setIsResettingCard] = useState<boolean>(false);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);

  // Search input fields
  const [editName, setEditName] = useState<string>("");
  const [editNumber, setEditNumber] = useState<string>("");
  const [editSetId, setEditSetId] = useState<string>("");
  const [showManualSearch, setShowManualSearch] = useState<boolean>(false);

  // Phase 6 Collection state
  const [collectionItem, setCollectionItem] = useState<CollectionItem | null>(
    null
  );
  const [isAddingToCollection, setIsAddingToCollection] =
    useState<boolean>(false);
  const [collectionSuccessMsg, setCollectionSuccessMsg] = useState<
    string | null
  >(null);

  // Run automatic detection with race condition protection
  const runAutoDetection = useCallback(async (scanId: string) => {
    setIsDetecting(true);
    setActionError(null);
    const detectionId = ++activeDetectionIdRef.current;
    const requestRevision = selectionRevisionRef.current;

    try {
      const result = await detectCard(scanId);
      if (
        activeDetectionIdRef.current !== detectionId ||
        currentScanIdRef.current !== scanId ||
        selectionRevisionRef.current !== requestRevision
      ) {
        return;
      }
      setCorners(result.corners);
      setDetectionMessage(result.message);
      setHasUnsavedChanges(true);
      selectionRevisionRef.current += 1;
    } catch {
      if (
        activeDetectionIdRef.current !== detectionId ||
        currentScanIdRef.current !== scanId ||
        selectionRevisionRef.current !== requestRevision
      ) {
        return;
      }
      setCorners(DEFAULT_CORNERS);
      setDetectionMessage(
        "Automatische detectie is niet beschikbaar. Zet de hoeken handmatig goed."
      );
      setHasUnsavedChanges(true);
      selectionRevisionRef.current += 1;
    } finally {
      if (activeDetectionIdRef.current === detectionId) {
        setIsDetecting(false);
      }
    }
  }, []);

  // Load initial scan
  const fetchScan = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setErrorStatus(null);
    setErrorMessage(null);

    try {
      const data = await getScan(id);
      setScan(data);
      if (data.rotation !== undefined) {
        setRotation(data.rotation);
      }
      if (data.corners) {
        setCorners(data.corners);
        setHasUnsavedChanges(false);
      } else {
        void runAutoDetection(id);
      }

      const initialName = data.user_search_name ?? data.recognized_name ?? "";
      const initialNumber =
        data.user_search_number ?? data.recognized_number ?? "";
      const initialSetCode =
        data.user_search_set_code ??
        data.user_search_provider_set_id ??
        data.recognized_set_code ??
        "";
      setEditName(initialName);
      setEditNumber(initialNumber);
      setEditSetId(initialSetCode);

      if (data.confirmed_card) {
        getScanCollectionItem(data.id)
          .then((item) => {
            setCollectionItem(item);
          })
          .catch(() => {
            // Background check failure is non-fatal
          });
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorStatus(err.status);
        setErrorMessage(err.message);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("De scan kon niet van de server worden geladen.");
      }
    } finally {
      setLoading(false);
    }
  }, [id, runAutoDetection]);

  useEffect(() => {
    void fetchScan();
  }, [fetchScan]);

  const handleCornersChange = (nextCorners: CropCorners) => {
    selectionRevisionRef.current += 1;
    setCorners(nextCorners);
    setHasUnsavedChanges(true);
    setActionError(null);
  };

  const handleRotate = (direction: "left" | "right") => {
    selectionRevisionRef.current += 1;
    const delta = direction === "right" ? 90 : 270;
    const next = (rotation + delta) % 360;
    setRotation(next);
    setHasUnsavedChanges(true);
    setActionError(null);
  };

  const handleResetCorners = () => {
    selectionRevisionRef.current += 1;
    setCorners(DEFAULT_CORNERS);
    setHasUnsavedChanges(true);
    setActionError(null);
  };

  const handleGeneratePreview = async () => {
    if (!scan) return;
    setIsCropping(true);
    setActionError(null);
    const previewId = ++activePreviewIdRef.current;
    const requestRevision = selectionRevisionRef.current;

    try {
      const updated = await cropScan(scan.id, {
        corners,
        rotation,
        expected_version: scan.crop_version ?? 0,
      });

      if (activePreviewIdRef.current !== previewId) return;

      setScan(updated);
      if (selectionRevisionRef.current === requestRevision) {
        setHasUnsavedChanges(false);
      }
    } catch (err: unknown) {
      if (activePreviewIdRef.current !== previewId) return;
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setActionError(
            "De scan is intussen gewijzigd. De nieuwste versie wordt opgehaald."
          );
          void fetchScan();
        } else {
          setActionError(err.message);
        }
      } else {
        setActionError(
          "De uitsnede kon niet worden gemaakt. Probeer het opnieuw."
        );
      }
    } finally {
      if (activePreviewIdRef.current === previewId) {
        setIsCropping(false);
      }
    }
  };

  const handleConfirmCrop = async () => {
    if (!scan || scan.crop_version === undefined) return;
    if (hasUnsavedChanges) {
      setActionError(
        "Corners or rotation were modified. Please preview changes before confirming."
      );
      return;
    }
    setIsConfirming(true);
    setActionError(null);
    const requestRevision = selectionRevisionRef.current;

    try {
      const updated = await confirmCrop(scan.id, {
        crop_version: scan.crop_version,
      });
      setScan(updated);
      setIsEditingConfirmed(false);
      if (selectionRevisionRef.current === requestRevision) {
        setHasUnsavedChanges(false);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setActionError("The crop version changed. Reloading current state.");
          void fetchScan();
        } else {
          setActionError(err.message);
        }
      } else {
        setActionError(
          "De uitsnede kon niet worden bevestigd. Probeer het opnieuw."
        );
      }
    } finally {
      setIsConfirming(false);
    }
  };

  const handleRecognizeCard = async () => {
    if (!scan) return;
    const recognitionId = ++activeRecognitionIdRef.current;
    const currentCropVer = scan.crop_version;
    const currentScanId = scan.id;

    setIsRecognizing(true);
    setRecognitionError(null);
    setActionError(null);

    try {
      const result = await recognizeCard(scan.id);
      if (
        activeRecognitionIdRef.current !== recognitionId ||
        currentScanIdRef.current !== currentScanId
      ) {
        return;
      }

      if (
        editName === (scan.recognized_name ?? "") &&
        scan.user_search_name == null
      ) {
        setEditName((prev) =>
          prev === editName ? (result.recognized_name ?? "") : prev
        );
      }
      if (
        editNumber === (scan.recognized_number ?? "") &&
        scan.user_search_number == null
      ) {
        setEditNumber((prev) =>
          prev === editNumber ? (result.recognized_number ?? "") : prev
        );
      }
      if (
        editSetId === (scan.recognized_set_code ?? "") &&
        scan.user_search_set_code == null
      ) {
        setEditSetId((prev) =>
          prev === editSetId ? (result.recognized_set_code ?? "") : prev
        );
      }

      setScan((prev) => {
        if (!prev || prev.crop_version !== currentCropVer) return prev;
        return {
          ...prev,
          recognition_status: "completed",
          recognition_id: result.recognition_id,
          ocr_crop_version: result.crop_version,
          ocr_raw_text: result.raw_text,
          recognized_name: result.recognized_name,
          recognized_number: result.recognized_number,
          recognized_set_code: result.recognized_set_code,
          ocr_confidence: result.ocr_confidence,
          confidence_state: result.confidence_state,
          image_quality: result.image_quality,
          evidence: result.evidence,
          catalog_status: result.catalog_status,
          catalog_error: result.catalog_error,
          search_version: result.search_version,
          candidate_search_version: result.search_version,
          card_selection_version: result.card_selection_version,
          candidates: result.candidates,
        };
      });

      if (result.catalog_status === "unavailable") {
        setRecognitionError(
          "De catalogus is tijdelijk niet bereikbaar. De herkende gegevens zijn bewaard; je kunt hieronder handmatig zoeken."
        );
        setShowManualSearch(true);
      }
    } catch (err: unknown) {
      if (
        activeRecognitionIdRef.current !== recognitionId ||
        currentScanIdRef.current !== currentScanId
      ) {
        return;
      }
      if (err instanceof ApiError) {
        if (err.status === 504) {
          setRecognitionError(
            "De herkenning duurde te lang. Probeer het opnieuw of zoek handmatig."
          );
        } else if (err.status === 503) {
          setRecognitionError(
            "De herkenningsdienst is tijdelijk niet beschikbaar. Je kunt hieronder handmatig zoeken."
          );
          setShowManualSearch(true);
        } else if (err.status === 409) {
          setActionError(
            "The crop was modified during recognition. Please check the current crop."
          );
          void fetchScan();
        } else {
          setRecognitionError(err.message);
        }
      } else {
        setRecognitionError(
          "Er ging iets mis tijdens het herkennen van de kaart."
        );
      }
    } finally {
      if (activeRecognitionIdRef.current === recognitionId) {
        setIsRecognizing(false);
      }
    }
  };

  const handleSearchCandidates = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!scan || scan.crop_version === undefined) return;

    const searchId = ++activeSearchIdRef.current;
    const currentCropVer = scan.crop_version;
    const currentScanId = scan.id;

    setIsSearching(true);
    setRecognitionError(null);
    setActionError(null);

    try {
      const result = await searchCardCandidates(scan.id, {
        name: editName || null,
        number: editNumber || null,
        set_code: editSetId || null,
        set_id: editSetId || null,
        expected_crop_version: scan.crop_version,
        expected_search_version: scan.search_version ?? 0,
      });

      if (
        activeSearchIdRef.current !== searchId ||
        currentScanIdRef.current !== currentScanId
      ) {
        return;
      }

      setScan((prev) => {
        if (!prev || prev.crop_version !== currentCropVer) return prev;
        return {
          ...prev,
          search_version: result.search_version,
          candidate_search_version: result.search_version,
          user_search_name: editName || null,
          user_search_number: editNumber || null,
          user_search_set_code: editSetId || null,
          candidates: result.candidates,
          confidence_state: result.confidence_state,
          catalog_status: result.catalog_status,
        };
      });

      if (result.catalog_status === "unavailable") {
        setRecognitionError(
          "De kaartencatalogus is tijdelijk niet bereikbaar."
        );
      }
    } catch (err: unknown) {
      if (
        activeSearchIdRef.current !== searchId ||
        currentScanIdRef.current !== currentScanId
      ) {
        return;
      }
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setActionError("The crop was changed. Refreshing candidates.");
          void fetchScan();
        } else {
          setRecognitionError(err.message);
        }
      } else {
        setRecognitionError("Het zoeken naar kaarten is niet gelukt.");
      }
    } finally {
      if (activeSearchIdRef.current === searchId) {
        setIsSearching(false);
      }
    }
  };

  const handleConfirmCard = async (candidateId: string) => {
    if (!scan || scan.crop_version === undefined) return;

    const confirmId = ++activeConfirmCardIdRef.current;
    const currentCropVer = scan.crop_version;
    const currentSearchVer = scan.search_version ?? 0;
    const currentSelectionVer = scan.card_selection_version ?? 0;
    const currentScanId = scan.id;

    setIsConfirmingCard(true);
    setActionError(null);
    setRecognitionError(null);

    try {
      const updated = await confirmCatalogCard(scan.id, {
        card_id: candidateId,
        expected_crop_version: currentCropVer,
        expected_search_version: currentSearchVer,
        expected_selection_version: currentSelectionVer,
      });

      if (
        activeConfirmCardIdRef.current !== confirmId ||
        currentScanIdRef.current !== currentScanId
      ) {
        return;
      }
      setScan(updated);
    } catch (err: unknown) {
      if (
        activeConfirmCardIdRef.current !== confirmId ||
        currentScanIdRef.current !== currentScanId
      ) {
        return;
      }
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setActionError(
            "De kaartkeuze of uitsnede is intussen gewijzigd. De pagina wordt ververst."
          );
          void fetchScan();
        } else {
          setActionError(err.message);
        }
      } else {
        setActionError("Could not confirm card. Please try again.");
      }
    } finally {
      if (activeConfirmCardIdRef.current === confirmId) {
        setIsConfirmingCard(false);
      }
    }
  };

  const handleResetCardConfirmation = async () => {
    if (!scan || scan.crop_version === undefined) return;

    const currentCropVer = scan.crop_version;
    const currentSelectionVer = scan.card_selection_version ?? 0;

    setIsResettingCard(true);
    setActionError(null);

    try {
      const updated = await resetCatalogCardConfirmation(scan.id, {
        expected_crop_version: currentCropVer,
        expected_selection_version: currentSelectionVer,
      });
      setScan(updated);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setActionError(
            "De bevestiging is intussen gewijzigd. De pagina wordt ververst."
          );
          void fetchScan();
        } else {
          setActionError(err.message);
        }
      } else {
        setActionError("De kaartkeuze kon niet worden hersteld.");
      }
    } finally {
      setIsResettingCard(false);
    }
  };

  const handleAddToCollection = async () => {
    if (!scan || !scan.confirmed_card) return;
    setIsAddingToCollection(true);
    setActionError(null);
    setCollectionSuccessMsg(null);

    try {
      const item = await addScanToCollection(scan.id);
      setCollectionItem(item);
      setCollectionSuccessMsg(
        "Kaart succesvol toegevoegd aan je persoonlijke collectie!"
      );
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setActionError(err.message);
      } else {
        setActionError("Kaart kon niet aan de collectie worden toegevoegd.");
      }
    } finally {
      setIsAddingToCollection(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto flex min-h-[60vh] max-w-4xl flex-col items-center justify-center px-4 py-16 text-center">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900 dark:border-zinc-800 dark:border-t-white" />
        <h2 className="mt-4 text-sm font-semibold tracking-wide text-zinc-800 dark:text-zinc-200">
          Scan laden…
        </h2>
        <p className="mt-1 font-mono text-xs text-zinc-500">
          Uitsnede en kaartresultaten worden opgehaald
        </p>
      </main>
    );
  }

  if (errorStatus === 404) {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <div className="rounded-2xl border border-zinc-200 bg-white p-8 dark:border-zinc-800 dark:bg-obsidian-900">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-obsidian-850 dark:text-zinc-400">
            <svg
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h1 className="mt-4 text-base font-bold text-zinc-900 dark:text-white">
            Scan niet gevonden
          </h1>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {errorMessage ||
              "Deze scan bestaat niet of is na de tijdelijke bewaartermijn verlopen."}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/scan"
              className="rounded-xl bg-zinc-900 px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-zinc-800 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
            >
              Nieuwe scan starten
            </Link>
            <Link
              href="/cards"
              className="rounded-xl border border-zinc-200 px-4 py-2.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-800/60"
            >
              Bekijk de catalogus
            </Link>
          </div>
        </div>
      </main>
    );
  }

  if (errorMessage || !scan) {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-8 dark:border-rose-950/60 dark:bg-rose-950/20">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-rose-200 bg-white text-rose-600 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-400">
            <svg
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
              />
            </svg>
          </div>
          <h1 className="mt-4 text-base font-bold text-rose-950 dark:text-rose-200">
            Scan laden lukt niet
          </h1>
          <p className="mt-2 text-xs text-rose-700 dark:text-rose-400">
            {errorMessage || "Er is een onverwachte fout opgetreden."}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => void fetchScan()}
              className="rounded-xl bg-rose-700 px-5 py-2.5 text-xs font-semibold text-white hover:bg-rose-600"
            >
              Opnieuw proberen
            </button>
            <Link
              href="/scan"
              className="rounded-xl border border-zinc-300 px-4 py-2.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              Nieuwe scan
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const isConfirmed = scan.crop_status === "confirmed" && !isEditingConfirmed;
  const isCardConfirmed = Boolean(scan.confirmed_card && isConfirmed);
  const originalImageUrl = getScanImageUrl(scan.id);
  const croppedImageUrl =
    scan.crop_image_url ||
    scan.crop_status === "confirmed" ||
    scan.crop_status === "preview"
      ? getScanCropImageUrl(scan.id, scan.crop_version)
      : null;
  const candidates: CandidateMatchItem[] = scan.candidates || [];

  return (
    <main className="content-page scan-result-page">
      {/* Top Header & Navigation */}
      <div className="mb-6 flex flex-col gap-4 border-b border-slate-200/80 pb-5 dark:border-white/10 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/scan"
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-bold text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
            >
              <span>&larr;</span>
              <span>Terug naar Scanner</span>
            </Link>
            <span className="text-slate-300 dark:text-slate-700">/</span>

            {isCardConfirmed ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-0.5 text-xs font-bold text-emerald-600 dark:text-emerald-400">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Kaart Geverifieerd
              </span>
            ) : isConfirmed ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-0.5 text-xs font-bold text-sky-600 dark:text-sky-400">
                <span className="h-2 w-2 rounded-full bg-sky-500" />
                Uitsnede Vergrendeld
              </span>
            ) : scan.crop_status === "preview" ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-0.5 text-xs font-bold text-amber-600 dark:text-amber-400">
                <span className="h-2 w-2 rounded-full bg-amber-500" />
                Voorbeeld Beschikbaar
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 bg-slate-100 px-3 py-0.5 text-xs font-bold text-slate-600 dark:border-white/10 dark:bg-slate-800 dark:text-slate-300">
                <span className="h-2 w-2 rounded-full bg-slate-400" />
                Hoeken Uitlijnen
              </span>
            )}
          </div>

          <h1 className="mt-2 text-2xl font-black tracking-tight text-slate-900 dark:text-white sm:text-3xl">
            {isCardConfirmed
              ? `${scan.confirmed_card?.name} #${scan.confirmed_card?.number}`
              : isConfirmed
                ? "Kaart Identificeren & Matchen"
                : scan.crop_status === "preview"
                  ? "Uitsnede Beoordelen & Bevestigen"
                  : "Kaartkader & Perspectief Uitlijnen"}
          </h1>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {isCardConfirmed
              ? `Officieel herkend en gekoppeld aan ${scan.confirmed_card?.set_name}.`
              : isConfirmed
                ? "Je uitsnede is vergrendeld. Start automatische herkenning of zoek handmatig."
                : scan.crop_status === "preview"
                  ? "Bekijk de gecorrigeerde uitsnede hieronder. Bevestig om door te gaan naar kaartdetectie."
                  : "Sleep de 4 hoekpunten strak om de buitenrand van de Pokémon kaart."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {isConfirmed && !isCardConfirmed && (
            <button
              type="button"
              onClick={() => setIsEditingConfirmed(true)}
              className="result-action secondary inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-white/10 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <svg
                className="h-3.5 w-3.5 text-slate-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                />
              </svg>
              <span>Uitsnede Wijzigen</span>
            </button>
          )}

          <Link href="/scan" className="ink-button red small">
            <svg
              className="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M12 4.5v15m7.5-7.5h-15"
              />
            </svg>
            <span>Nieuwe Scan</span>
          </Link>
        </div>
      </div>

      {/* Action Error Banner */}
      {actionError && (
        <div
          role="alert"
          className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-300 bg-rose-50 p-4 text-xs font-medium text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300"
        >
          <svg
            className="mt-0.5 h-4 w-4 shrink-0 text-rose-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4m0 4h.01" />
          </svg>
          <div className="flex-1">{actionError}</div>
        </div>
      )}

      {/* Recognition Error Banner */}
      {recognitionError && (
        <div
          role="alert"
          className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 text-xs font-medium text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
        >
          <svg
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 12.376zM12 15.75h.007v.008H12v-.008z"
            />
          </svg>
          <div className="flex-1">{recognitionError}</div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* SCENARIO 1: CARD IS CONFIRMED (Collector Slab Hero)           */}
      {/* ------------------------------------------------------------- */}
      {isCardConfirmed && scan.confirmed_card ? (
        <div className="space-y-6">
          <div className="card-slab rounded-3xl border border-slate-200 bg-white p-6 shadow-xl dark:border-white/10 dark:bg-vault-900 sm:p-8">
            <div className="grid grid-cols-1 gap-8 md:grid-cols-12 md:items-center">
              {/* Card Artwork in Slab Frame */}
              <div className="flex flex-col items-center justify-center md:col-span-5">
                <div className="relative aspect-card w-full max-w-[280px] overflow-hidden rounded-2xl border-2 border-emerald-500/30 bg-slate-950 p-2 shadow-2xl">
                  {scan.confirmed_card.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={scan.confirmed_card.image_url}
                      alt={scan.confirmed_card.name}
                      className="h-full w-full rounded-xl object-contain"
                    />
                  ) : croppedImageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={croppedImageUrl}
                      alt="Jouw gescannde kaart"
                      className="h-full w-full rounded-xl object-contain"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs font-semibold text-slate-400">
                      Geen afbeelding beschikbaar
                    </div>
                  )}
                  <span className="absolute bottom-3 right-3 rounded-full bg-black/80 px-2.5 py-1 font-mono text-[10px] font-black text-emerald-400 backdrop-blur-md">
                    BEVESTIGD
                  </span>
                </div>
              </div>

              {/* Card Details & Actions */}
              <div className="flex flex-col justify-between md:col-span-7">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-400">
                      <svg
                        className="h-3.5 w-3.5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2.5}
                          d="M4.5 12.75l6 6 9-13.5"
                        />
                      </svg>
                      Geverifieerd Exemplaar
                    </span>
                    <span className="font-mono text-xs font-bold text-slate-500">
                      #{scan.confirmed_card.number}
                    </span>
                    {collectionItem && (
                      <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-bold text-amber-700 dark:text-amber-400">
                        <svg
                          className="h-3.5 w-3.5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2.5}
                            d="M4.5 12.75l6 6 9-13.5"
                          />
                        </svg>
                        In collectie ({collectionItem.quantity}×)
                      </span>
                    )}
                  </div>

                  <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-900 dark:text-white sm:text-4xl">
                    {scan.confirmed_card.name}
                  </h2>
                  <p className="mt-1 text-sm font-semibold text-sky-600 dark:text-sky-400">
                    Set: {scan.confirmed_card.set_name}
                  </p>

                  <div className="mt-6 grid grid-cols-2 gap-4 rounded-2xl border border-slate-100 bg-slate-50/70 p-4 dark:border-white/5 dark:bg-vault-800/60 sm:grid-cols-2">
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Kaartnummer
                      </span>
                      <p className="mt-0.5 font-mono text-sm font-black text-slate-900 dark:text-white">
                        #{scan.confirmed_card.number}
                      </p>
                    </div>
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Geverifieerd op
                      </span>
                      <p className="mt-0.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                        {formatDate(scan.confirmed_card.confirmed_at)}
                      </p>
                    </div>
                  </div>

                  {collectionSuccessMsg && (
                    <div
                      role="status"
                      className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs font-bold text-emerald-800 dark:text-emerald-300"
                    >
                      <div className="flex items-center gap-2">
                        <svg
                          className="h-4 w-4 shrink-0 text-emerald-500"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2.5}
                            d="M4.5 12.75l6 6 9-13.5"
                          />
                        </svg>
                        <span>{collectionSuccessMsg}</span>
                      </div>
                      <Link
                        href="/collection"
                        className="text-sky-600 underline hover:no-underline dark:text-sky-400"
                      >
                        Bekijk in je collectie &rarr;
                      </Link>
                    </div>
                  )}
                </div>

                <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                  {collectionItem ? (
                    <Link
                      href="/collection"
                      className="inline-flex items-center justify-center gap-2 rounded-2xl border border-emerald-500/40 bg-emerald-500/15 px-5 py-3.5 text-xs font-bold text-emerald-700 transition hover:bg-emerald-500/25 dark:text-emerald-300"
                    >
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2.5}
                          d="M4.5 12.75l6 6 9-13.5"
                        />
                      </svg>
                      <span>In collectie ✓</span>
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void handleAddToCollection()}
                      disabled={isAddingToCollection}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-amber-500 px-5 py-3.5 text-xs font-black text-slate-950 shadow-lg shadow-amber-500/20 transition hover:bg-amber-400 active:scale-95 disabled:opacity-50"
                    >
                      {isAddingToCollection ? (
                        <>
                          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-950 border-t-transparent" />
                          <span>Toevoegen…</span>
                        </>
                      ) : (
                        <>
                          <svg
                            className="h-4 w-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2.5}
                              d="M12 4.5v15m7.5-7.5h-15"
                            />
                          </svg>
                          <span>Voeg toe aan collectie</span>
                        </>
                      )}
                    </button>
                  )}

                  <Link
                    href={`/cards/${encodeURIComponent(scan.confirmed_card.id)}`}
                    className="result-action primary inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 px-6 py-3.5 text-xs font-black text-white shadow-lg shadow-sky-500/30 transition hover:brightness-110 active:scale-95"
                  >
                    <span>Bekijk Kaart Details in Catalogus</span>
                    <span>&rarr;</span>
                  </Link>

                  <button
                    type="button"
                    onClick={() => void handleResetCardConfirmation()}
                    disabled={isResettingCard}
                    className="result-action secondary rounded-2xl border border-slate-200 px-5 py-3.5 text-xs font-bold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    {isResettingCard ? "Resetten..." : "Opnieuw Matchen"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : isConfirmed ? (
        /* ------------------------------------------------------------- */
        /* SCENARIO 2: CROP CONFIRMED, READY FOR MATCHING CANDIDATES    */
        /* ------------------------------------------------------------- */
        <div className="space-y-8">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
            {/* Left Column: USER'S CROPPED SCAN PREVIEW */}
            <div className="lg:col-span-4">
              <div className="card-slab sticky top-24 flex flex-col items-center rounded-3xl border border-slate-200 bg-white p-5 shadow-xl dark:border-white/10 dark:bg-vault-900">
                <div className="flex w-full items-center justify-between pb-3">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-sky-500/10 px-2.5 py-0.5 text-[11px] font-bold text-sky-600 dark:text-sky-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-500" />
                    Jouw Kaartuitsnede
                  </span>
                  <button
                    type="button"
                    onClick={() => setIsEditingConfirmed(true)}
                    className="result-action secondary compact text-xs font-bold text-slate-500 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                  >
                    Wijzigen &rarr;
                  </button>
                </div>

                <div className="relative aspect-card w-full max-w-[240px] overflow-hidden rounded-2xl border-2 border-sky-500/30 bg-slate-950 shadow-lg">
                  {croppedImageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={croppedImageUrl}
                      alt="Jouw gescannde kaartuitsnede"
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs font-semibold text-slate-500">
                      Uitsnede laden...
                    </div>
                  )}
                  {isRecognizing && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 backdrop-blur-[2px]">
                      <span className="h-8 w-8 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
                      <span className="mt-3 text-[11px] font-bold text-white">
                        Scannen...
                      </span>
                    </div>
                  )}
                </div>

                <p className="mt-3 text-center text-[11px] text-slate-400">
                  Dit fysieke exemplaar wordt vergeleken met de catalogus.
                </p>
              </div>
            </div>

            {/* Right Column: RECOGNITION ACTION OR CANDIDATES */}
            <div className="space-y-6 lg:col-span-8">
              {/* Action Callout if recognition not yet run */}
              {(!scan.candidates || scan.candidates.length === 0) && (
                <div className="card-slab rounded-3xl border border-slate-200 bg-white p-7 text-center shadow-xl dark:border-white/10 dark:bg-vault-900 sm:p-9">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-sky-400 to-blue-600 text-white shadow-lg shadow-sky-500/30">
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                      />
                    </svg>
                  </div>
                  <h2 className="mt-5 text-xl font-black text-slate-900 dark:text-white">
                    Klaar voor Automatische Herkenning
                  </h2>
                  <p className="mx-auto mt-2 max-w-md text-xs text-slate-500 dark:text-slate-400">
                    Onze optische scanner leest de kaartnaam, het set-symbool en
                    het kaartnummer direct van je uitsnede af om de kaart te
                    vinden in de officiële database.
                  </p>

                  <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => void handleRecognizeCard()}
                      disabled={isRecognizing}
                      className="result-action primary inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 px-8 py-3.5 text-xs font-black text-white shadow-lg shadow-sky-500/30 transition hover:brightness-110 disabled:opacity-60"
                    >
                      {isRecognizing ? (
                        <>
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                          <span>Kaart analyseren...</span>
                        </>
                      ) : (
                        <>
                          <span>Start Optische Herkenning</span>
                          <span>&rarr;</span>
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowManualSearch(!showManualSearch)}
                      className="result-action secondary rounded-2xl border border-slate-200 px-5 py-3.5 text-xs font-bold text-slate-600 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      {showManualSearch
                        ? "Verberg Handmatig Zoeken"
                        : "Handmatig Zoeken"}
                    </button>
                  </div>
                </div>
              )}

              {/* Candidate Matches */}
              {candidates.length > 0 && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-base font-black text-slate-900 dark:text-white">
                        Gevonden Matches ({candidates.length})
                      </h2>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Kies de kaart die exact overeenkomt met jouw uitsnede:
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowManualSearch(!showManualSearch)}
                      className="result-action secondary compact rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600 shadow-sm transition hover:bg-slate-50 dark:border-white/10 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                    >
                      {showManualSearch
                        ? "Verberg Zoekfilter"
                        : "Handmatig Verfijnen"}
                    </button>
                  </div>

                  {/* Candidates Grid */}
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
                    {candidates.map((cand) => (
                      <div
                        key={cand.id}
                        className="card-slab flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-3 shadow-md transition hover:-translate-y-1 hover:border-sky-400 hover:shadow-xl dark:border-white/10 dark:bg-vault-900"
                      >
                        <div>
                          <div className="relative aspect-card w-full overflow-hidden rounded-xl border border-slate-100 bg-slate-950 dark:border-white/10">
                            {cand.image_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={cand.image_url}
                                alt={cand.name}
                                className="h-full w-full object-contain"
                              />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-[10px] font-bold text-slate-400">
                                Geen artwork
                              </div>
                            )}
                            <span className="absolute bottom-1 right-1 rounded-md bg-black/80 px-1.5 py-0.5 font-mono text-[9px] font-bold text-white backdrop-blur-sm">
                              #{cand.local_id}
                            </span>
                          </div>

                          <h3 className="mt-2.5 line-clamp-1 text-xs font-black text-slate-900 dark:text-white">
                            {cand.name}
                          </h3>
                          <p className="line-clamp-1 text-[11px] font-semibold text-slate-500">
                            {cand.set_name}
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() => void handleConfirmCard(cand.id)}
                          disabled={isConfirmingCard}
                          className="result-action primary mt-3 w-full rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 py-2 text-xs font-black text-white shadow-md shadow-sky-500/20 transition hover:brightness-110 disabled:opacity-50"
                        >
                          {isConfirmingCard ? "Koppelen..." : "Kies Deze Kaart"}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Manual Refinement Form */}
              {(showManualSearch || candidates.length === 0) && (
                <div className="card-slab rounded-3xl border border-slate-200 bg-white p-6 shadow-xl dark:border-white/10 dark:bg-vault-900">
                  <h3 className="text-xs font-black uppercase tracking-wider text-slate-400">
                    Handmatig Zoeken &amp; Verfijnen
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    Pas de kaartnaam of het kaartnummer aan als er sprake was
                    van weerspiegeling of lichte onscherpte op de foto.
                  </p>

                  <form
                    onSubmit={handleSearchCandidates}
                    className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-4"
                  >
                    <input
                      type="text"
                      placeholder="Kaartnaam (bv. Charizard)"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-semibold text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none dark:border-white/10 dark:bg-slate-800 dark:text-white sm:col-span-2"
                    />
                    <input
                      type="text"
                      placeholder="Nummer (bv. 4)"
                      value={editNumber}
                      onChange={(e) => setEditNumber(e.target.value)}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-semibold text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none dark:border-white/10 dark:bg-slate-800 dark:text-white"
                    />
                    <button
                      type="submit"
                      disabled={isSearching}
                      className="result-action primary rounded-xl bg-slate-900 py-2.5 text-xs font-black text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
                    >
                      {isSearching ? "Zoeken..." : "Zoek Kaart"}
                    </button>
                  </form>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* ------------------------------------------------------------- */
        /* SCENARIO 3: ADJUST CORNERS / FRAMING & LIVE PREVIEW           */
        /* ------------------------------------------------------------- */
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Corner Selector Canvas Column */}
            <div
              className={croppedImageUrl ? "lg:col-span-7" : "lg:col-span-12"}
            >
              <div className="card-slab rounded-3xl border border-slate-200 bg-white p-5 shadow-xl dark:border-white/10 dark:bg-vault-900 sm:p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-sm font-black text-slate-900 dark:text-white">
                    Hoeken &amp; Perspectief Corrigeren
                  </h2>
                  <span className="text-[11px] font-semibold text-slate-400">
                    Versleep de 4 hoekpunten
                  </span>
                </div>

                {/* Corner Selector canvas */}
                <CornerSelector
                  imageUrl={originalImageUrl}
                  imageWidth={scan.width}
                  imageHeight={scan.height}
                  corners={corners}
                  onChange={handleCornersChange}
                  disabled={isCropping || isConfirming}
                />

                {/* Rotation and control buttons */}
                <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4 dark:border-white/10">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleRotate("left")}
                      className="result-action secondary rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      &larr; 90° Links
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRotate("right")}
                      className="result-action secondary rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      90° Rechts &rarr;
                    </button>
                    <button
                      type="button"
                      onClick={handleResetCorners}
                      className="result-action secondary rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-500 transition hover:bg-slate-50 dark:border-white/10 dark:text-slate-400 dark:hover:bg-slate-800"
                    >
                      Herstel Hoeken
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleGeneratePreview}
                      disabled={isCropping}
                      className="result-action utility inline-flex items-center gap-1.5 rounded-xl border border-sky-400/60 bg-sky-50 px-4 py-2 text-xs font-bold text-sky-700 transition hover:bg-sky-100 dark:border-sky-500/40 dark:bg-sky-950/40 dark:text-sky-300 dark:hover:bg-sky-900/60"
                    >
                      {isCropping ? (
                        <>
                          <span className="h-3 w-3 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
                          <span>Uitsnijden...</span>
                        </>
                      ) : (
                        <>
                          <span>👁️ Uitsnede Bekijken</span>
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={handleConfirmCrop}
                      disabled={isConfirming || hasUnsavedChanges}
                      className="result-action primary rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 px-5 py-2 text-xs font-black text-white shadow-md shadow-sky-500/20 transition hover:brightness-110 disabled:opacity-50"
                    >
                      {isConfirming
                        ? "Vastzetten..."
                        : "Uitsnede Vastzetten & Doorgaan"}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Live Crop Preview Column (Displayed when crop preview exists) */}
            {croppedImageUrl && (
              <div className="lg:col-span-5">
                <div className="card-slab flex flex-col items-center rounded-3xl border border-sky-500/30 bg-white p-5 shadow-xl dark:border-sky-500/20 dark:bg-vault-900 sm:p-6">
                  <div className="flex w-full items-center justify-between pb-3">
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-bold text-amber-600 dark:text-amber-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                      Voorbeeld Uitsnede
                    </span>
                    <span className="font-mono text-[11px] text-slate-400">
                      v{scan.crop_version ?? 0}
                    </span>
                  </div>

                  <div className="relative aspect-card w-full max-w-[260px] overflow-hidden rounded-2xl border-2 border-sky-500/40 bg-slate-950 shadow-2xl">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={croppedImageUrl}
                      alt="Uitsnede preview"
                      className="h-full w-full object-contain"
                    />
                  </div>

                  <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
                    Ziet de kaart er recht en scherp uit? Bevestig deze uitsnede
                    om de kaarttekst en het setnummer te identificeren.
                  </p>

                  <button
                    type="button"
                    onClick={handleConfirmCrop}
                    disabled={isConfirming || hasUnsavedChanges}
                    className="result-action primary mt-5 w-full rounded-2xl bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 py-3.5 text-xs font-black text-white shadow-lg shadow-sky-500/30 transition hover:brightness-110 active:scale-95 disabled:opacity-50"
                  >
                    {isConfirming
                      ? "Uitsnede vastzetten..."
                      : "✓ Deze Uitsnede Bevestigen & Kaart Zoeken"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* SYSTEM TELEMETRY (COLLAPSIBLE FOR DEVELOPERS)                 */}
      {/* ------------------------------------------------------------- */}
      <details className="mt-12 rounded-2xl border border-slate-200/80 bg-slate-50/50 p-4 font-mono text-xs dark:border-white/10 dark:bg-vault-950/60">
        <summary className="cursor-pointer font-bold text-slate-500 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
          Scangegevens &amp; OCR-resultaat (voor ontwikkelaars)
        </summary>
        <div className="mt-4 space-y-2 text-[11px] text-slate-600 dark:text-slate-400">
          <p>Scan UID: {scan.id}</p>
          <p>
            Afmetingen: {scan.width} &times; {scan.height} px &bull;
            Bestandsgrootte: {formatBytes(scan.file_size)}
          </p>
          <p>
            Uitsnede Status: {scan.crop_status} &bull; Versie:{" "}
            {scan.crop_version ?? 0}
          </p>
          {scan.ocr_confidence !== undefined && (
            <p>
              OCR Zekerheid: {Math.round((scan.ocr_confidence || 0) * 100)}% (
              {scan.confidence_state})
            </p>
          )}
          {scan.ocr_raw_text && (
            <div className="mt-2 rounded-xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-vault-900">
              <span className="font-bold text-slate-800 dark:text-slate-200">
                Gelezen Tekst Tokens:
              </span>
              <pre className="mt-1 whitespace-pre-wrap text-[10px] text-slate-500">
                {scan.ocr_raw_text}
              </pre>
            </div>
          )}
        </div>
      </details>
    </main>
  );
}
