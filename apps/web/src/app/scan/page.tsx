"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, uploadScan } from "@/lib/api";

const MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024; // 15 MiB
const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

export default function ScanUploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl(null);
      return;
    }

    const url = URL.createObjectURL(selectedFile);
    setPreviewUrl(url);

    return () => URL.revokeObjectURL(url);
  }, [selectedFile]);

  const validateAndSetFile = (file: File) => {
    if (isUploading) return;
    setErrorMessage(null);
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      setErrorMessage("Kies een JPG-, PNG- of WebP-afbeelding.");
      return;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setErrorMessage(
        `Je foto is te groot (${formatBytes(file.size)}). Maximaal 15 MB.`
      );
      return;
    }
    setSelectedFile(file);
  };
  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 1)
      setErrorMessage("Kies één kaartfoto tegelijk.");
    else if (files?.[0]) validateAndSetFile(files[0]);
    e.target.value = "";
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    if (!e.currentTarget.contains(e.relatedTarget as Node))
      setIsDragging(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 1)
      setErrorMessage("Sleep één kaartfoto tegelijk.");
    else if (e.dataTransfer.files[0])
      validateAndSetFile(e.dataTransfer.files[0]);
  };
  const handleRemove = () => {
    setSelectedFile(null);
    setErrorMessage(null);
  };
  const handleUpload = async () => {
    if (!selectedFile || isUploading) return;
    setIsUploading(true);
    setErrorMessage(null);
    try {
      const scan = await uploadScan(selectedFile);
      router.push(`/scan/${scan.id}`);
    } catch (err: unknown) {
      setIsUploading(false);
      setErrorMessage(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Uploaden is niet gelukt. Probeer opnieuw."
      );
    }
  };

  return (
    <main className="collector-page scan-page">
      <div className="section-topline">
        <Link href="/">DexLens</Link>
        <span>/</span>
        <span>Kaart scannen</span>
        <span className="edition">SCANNER / 01</span>
      </div>
      <div className="scan-layout">
        <section className="scan-copy">
          <p className="eyebrow">
            <span className="red-square" /> JOUW VOLGENDE ONTDEKKING
          </p>
          <h1>
            Laat je
            <br />
            kaart <em>zien.</em>
          </h1>
          <p className="hero-intro">
            Een oude klassieker of nét uit een booster. Maak een foto en ontdek
            welke kaart je in handen hebt.
          </p>
          <ol className="scan-steps">
            <li className="current">
              <span>01</span>
              <div>
                <strong>Kies je foto</strong>
                <p>De voorkant, met alle vier de hoeken.</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Controleer de uitsnede</strong>
                <p>Pas de hoeken aan als dat nodig is.</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>Vind de juiste kaart</strong>
                <p>Vergelijk de resultaten en bevestig je keuze.</p>
              </div>
            </li>
          </ol>
          <Link href="/cards" className="text-link">
            Liever zelf zoeken? Naar de catalogus →
          </Link>
        </section>
        <section className="scan-station" aria-label="Kaartfoto uploaden">
          <div className="station-header">
            <span className="station-lights" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span>DEXLENS / CARD READER</span>
            <span aria-hidden="true">✦</span>
          </div>
          <div className="station-body">
            <div className="station-label">
              <strong>
                {selectedFile ? "FOTO GESELECTEERD" : "PLAATS JE KAARTFOTO"}
              </strong>
              <span>01 / 03</span>
            </div>
            {errorMessage && (
              <div role="alert" className="upload-error">
                {errorMessage}
                <button
                  type="button"
                  onClick={() => setErrorMessage(null)}
                  aria-label="Sluit foutmelding"
                >
                  ×
                </button>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handleFileInputChange}
              className="sr-only"
              aria-label="Kies een kaartfoto"
              disabled={isUploading}
            />
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              onChange={handleFileInputChange}
              className="sr-only"
              aria-label="Maak een kaartfoto"
              disabled={isUploading}
            />
            {!selectedFile ? (
              <div
                className={`upload-mat ${isDragging ? "drag-active" : ""}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <button
                  type="button"
                  className="upload-target"
                  onClick={() => fileInputRef.current?.click()}
                  aria-label="Kies een kaartfoto om te uploaden"
                >
                  <span className="sample-card" aria-hidden="true">
                    <span className="sample-card-title">
                      JOUW KAART <span>✦</span>
                    </span>
                    <span className="sample-art">
                      <span className="pokeball" />
                    </span>
                    <span className="sample-lines" />
                    <span className="sample-number">??? / ???</span>
                  </span>
                  <span className="drop-caption">
                    Sleep je foto hierheen
                    <br />
                    <small>of klik om een bestand te kiezen</small>
                  </span>
                </button>
              </div>
            ) : (
              <div className="upload-mat preview-mat">
                {previewUrl && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={previewUrl}
                    alt="Voorvertoning van je geselecteerde kaartfoto"
                  />
                )}
                <div className="preview-file">
                  <span>{selectedFile.name}</span>
                  <small>{formatBytes(selectedFile.size)}</small>
                </div>
              </div>
            )}
            <div className="upload-actions">
              {selectedFile ? (
                <>
                  <button
                    type="button"
                    className="ink-button red"
                    disabled={isUploading}
                    onClick={handleUpload}
                  >
                    {isUploading ? "Foto uploaden…" : "Verder naar uitsnijden"}
                    <span aria-hidden="true">→</span>
                  </button>
                  <button
                    type="button"
                    className="ink-button secondary"
                    disabled={isUploading}
                    onClick={handleRemove}
                  >
                    Andere foto kiezen
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="ink-button red"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Kies een foto <span aria-hidden="true">↑</span>
                  </button>
                  <button
                    type="button"
                    className="ink-button secondary"
                    onClick={() => cameraInputRef.current?.click()}
                  >
                    Maak een foto <span aria-hidden="true">◎</span>
                  </button>
                </>
              )}
            </div>
            <p className="upload-formats" role="status">
              {isUploading
                ? "Even geduld. Je foto wordt klaargemaakt."
                : "JPG, PNG of WebP · Maximaal 15 MB · Eén kaart per foto"}
            </p>
            {!selectedFile && (
              <p className="camera-note">
                Op je telefoon opent ‘Maak een foto’ de camera als je browser
                dit ondersteunt. Op desktop kies je een bestand.
              </p>
            )}
          </div>
          <div className="station-bottom">
            <span aria-hidden="true">▰ ▰ ▰ ▰ ▰</span>
            <span>FOTO → UITSNEDE → HERKENNING</span>
          </div>
        </section>
      </div>
      <aside className="photo-tips">
        <span className="tips-heading">
          EEN GOEDE FOTO
          <br />
          <strong>maakt het verschil.</strong>
        </span>
        <div>
          <span>01 / LICHT</span>
          <p>
            Daglicht werkt fijn.
            <br />
            Vermijd flits en reflectie.
          </p>
        </div>
        <div>
          <span>02 / ACHTERGROND</span>
          <p>
            Leg je kaart plat op een
            <br />
            effen, contrasterende ondergrond.
          </p>
        </div>
        <div>
          <span>03 / KADER</span>
          <p>
            Houd alle hoeken in beeld.
            <br />
            Kom dichtbij voor scherpe tekst.
          </p>
        </div>
      </aside>
    </main>
  );
}

