"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getHealth, HealthResponse } from "@/lib/api";

export default function DebugPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const check = useCallback(async () => {
    setLoading(true);
    setHealth(await getHealth());
    setCheckedAt(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const apiOnline = health !== null && health.status !== "disconnected";
  const databaseOnline = health?.database === "connected";

  return (
    <main className="content-page debug-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            <span className="red-square" /> SYSTEEMSTATUS / INTERN
          </p>
          <h1>Onder de motorkap.</h1>
          <p className="page-intro">
            Een eenvoudige controle van de API en de kaartendatabase.
          </p>
        </div>
        <button
          className="ink-button secondary small"
          onClick={() => void check()}
          disabled={loading}
        >
          {loading ? "Controleren…" : "Opnieuw controleren"}
        </button>
      </div>

      <div className="status-grid">
        <article
          className={apiOnline ? "status-card online" : "status-card offline"}
        >
          <div className="status-card-top">
            <span>01 / API</span>
            <i />
          </div>
          <h2>{apiOnline ? "Verbonden" : "Niet bereikbaar"}</h2>
          <p>
            {apiOnline
              ? "De applicatieserver reageert normaal."
              : "De applicatieserver geeft geen antwoord."}
          </p>
        </article>
        <article
          className={
            databaseOnline ? "status-card online" : "status-card offline"
          }
        >
          <div className="status-card-top">
            <span>02 / DATABASE</span>
            <i />
          </div>
          <h2>{databaseOnline ? "Verbonden" : "Niet bereikbaar"}</h2>
          <p>
            {databaseOnline
              ? "De kaartencatalogus is beschikbaar."
              : "De kaartendatabase geeft geen antwoord."}
          </p>
        </article>
      </div>

      <div className="debug-footer">
        <span>
          {checkedAt
            ? `Laatst gecontroleerd: ${checkedAt.toLocaleTimeString("nl-NL")}`
            : "Nog niet gecontroleerd"}
        </span>
        <div>
          <Link href="/">Start</Link>
          <Link href="/scan">Scanner</Link>
          <Link href="/cards">Catalogus</Link>
        </div>
      </div>
    </main>
  );
}
