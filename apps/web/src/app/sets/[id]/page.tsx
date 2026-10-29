"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import CardTile from "@/components/CardTile";
import EmptyState from "@/components/EmptyState";
import { CardGridSkeleton } from "@/components/LoadingSkeleton";
import { getCards, getSet, PaginatedCardsResponse, SetDetail } from "@/lib/api";

export default function SetDetailPage() {
  const params = useParams();
  const setId = Array.isArray(params.id) ? params.id[0] : params.id;
  const [setInfo, setSetInfo] = useState<SetDetail | null>(null);
  const [loadingSet, setLoadingSet] = useState(true);
  const [setError, setSetError] = useState<string | null>(null);
  const [cards, setCards] = useState<PaginatedCardsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loadingCards, setLoadingCards] = useState(true);

  useEffect(() => {
    if (!setId) {
      setSetError("Geen geldige set ontvangen.");
      setLoadingSet(false);
      return;
    }
    let active = true;
    getSet(setId)
      .then((data) => active && setSetInfo(data))
      .catch(
        (err) =>
          active &&
          setSetError(err instanceof Error ? err.message : "Set niet gevonden.")
      )
      .finally(() => active && setLoadingSet(false));
    return () => {
      active = false;
    };
  }, [setId]);

  useEffect(() => {
    if (!setId) return;
    let active = true;
    setLoadingCards(true);
    getCards({ set_id: setId, page, page_size: 24 })
      .then((data) => active && setCards(data))
      .catch(() => active && setCards(null))
      .finally(() => active && setLoadingCards(false));
    return () => {
      active = false;
    };
  }, [setId, page]);

  if (loadingSet)
    return (
      <main className="content-page detail-loading">
        <span className="loader-mark" aria-hidden="true" />
        <p>SET OPENEN…</p>
      </main>
    );

  if (setError || !setInfo)
    return (
      <main className="content-page">
        <EmptyState
          title="Deze set konden we niet vinden"
          description="De set staat niet in de catalogus of de verbinding is tijdelijk weg."
          actionHref="/sets"
          actionLabel="Terug naar alle sets"
        />
      </main>
    );

  const count = setInfo.card_count ?? setInfo.local_card_count ?? 0;
  const totalPages = cards
    ? cards.total !== null
      ? Math.max(1, Math.ceil(cards.total / cards.page_size))
      : cards.has_more
        ? page + 1
        : page
    : 1;

  return (
    <main className="content-page set-detail-page">
      <nav className="editorial-breadcrumb" aria-label="Kruimelpad">
        <Link href="/sets">Alle sets</Link>
        <span>/</span>
        <strong>{setInfo.name}</strong>
      </nav>

      <section className="set-hero">
        <div className="set-hero-copy">
          <p className="eyebrow">
            <span className="red-square" /> {setInfo.series || "POKÉMON TCG"} /{" "}
            {setInfo.external_id}
          </p>
          <h1>{setInfo.name}</h1>
          <p>
            {setInfo.release_date
              ? `Uitgebracht op ${setInfo.release_date}.`
              : "Releasedatum onbekend."}{" "}
            Bekijk alle kaarten uit deze uitbreiding.
          </p>
          <div className="set-stats">
            <div>
              <span>KAARTEN</span>
              <strong>{count}</strong>
              {setInfo.total ? <small> / {setInfo.total}</small> : null}
            </div>
            <div>
              <span>TAAL</span>
              <strong>{setInfo.language?.toUpperCase() || "EN"}</strong>
            </div>
          </div>
          <Link href="/scan" className="ink-button red">
            Scan een kaart uit deze set <span aria-hidden="true">↗</span>
          </Link>
        </div>
        <div className="set-hero-mark">
          <span>SET / {setInfo.external_id}</span>
          {setInfo.logo_url ? (
            <div className="set-logo">
              <Image
                src={
                  /\.(webp|png)$/i.test(setInfo.logo_url)
                    ? setInfo.logo_url
                    : `${setInfo.logo_url}.webp`
                }
                alt={setInfo.name}
                fill
                className="object-contain"
                unoptimized
              />
            </div>
          ) : (
            <strong>{setInfo.name.slice(0, 2).toUpperCase()}</strong>
          )}
          <small>{setInfo.release_date?.slice(0, 4) || "—"}</small>
        </div>
      </section>

      <section className="set-cards-section">
        <div className="section-heading-row">
          <div>
            <p className="eyebrow">DE CHECKLIST</p>
            <h2>Kaarten in deze set</h2>
          </div>
          <span>{cards?.total ?? count} kaarten</span>
        </div>
        {loadingCards ? (
          <CardGridSkeleton count={12} />
        ) : cards && cards.items.length ? (
          <div className="card-grid">
            {cards.items.map((card) => (
              <CardTile key={card.external_id || card.id} card={card} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="Nog geen kaarten gevonden"
            description="Voor deze set zijn op dit moment geen kaarten beschikbaar."
            actionHref="/cards"
            actionLabel="Zoek in alle kaarten"
          />
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <button
              className="ink-button secondary small"
              disabled={page <= 1 || loadingCards}
              onClick={() => setPage((value) => value - 1)}
            >
              ← Vorige
            </button>
            <span>
              Pagina {page} van {totalPages}
            </span>
            <button
              className="ink-button secondary small"
              disabled={page >= totalPages || loadingCards}
              onClick={() => setPage((value) => value + 1)}
            >
              Volgende →
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
