"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import CardImage from "@/components/CardImage";
import EmptyState from "@/components/EmptyState";
import { CardDetail, getCard } from "@/lib/api";

export default function CardDetailPage() {
  const params = useParams();
  const cardId = Array.isArray(params.id) ? params.id[0] : params.id;
  const [card, setCard] = useState<CardDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!cardId) {
      setError("Geen geldig kaartnummer ontvangen.");
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    getCard(cardId)
      .then((data) => active && setCard(data))
      .catch(
        (err) =>
          active &&
          setError(err instanceof Error ? err.message : "Kaart niet gevonden.")
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [cardId]);

  if (loading) {
    return (
      <main className="content-page detail-loading">
        <span className="loader-mark" aria-hidden="true" />
        <p>KAARTGEGEVENS OPHALEN…</p>
      </main>
    );
  }

  if (error || !card) {
    return (
      <main className="content-page">
        <EmptyState
          title="Deze kaart konden we niet vinden"
          description="Het kaartnummer komt niet voor in de catalogus of de verbinding is tijdelijk weg."
          actionHref="/cards"
          actionLabel="Terug naar de catalogus"
        />
      </main>
    );
  }

  const regulationMark = card.regulation_mark || card.regulationMark;
  const variants = card.variants
    ? Object.entries(card.variants)
        .filter(([, active]) => active)
        .map(([name]) => name)
    : [];
  const specs = [
    ["Categorie", card.category],
    ["Zeldzaamheid", card.rarity],
    ["Type", card.types?.join(", ")],
    ["Illustrator", card.illustrator],
    ["Regelmarkering", regulationMark],
  ].filter(([, value]) => Boolean(value));

  return (
    <main className="content-page detail-page">
      <nav className="editorial-breadcrumb" aria-label="Kruimelpad">
        <Link href="/cards">Catalogus</Link>
        <span>/</span>
        {card.set ? (
          <Link href={`/sets/${card.set.external_id}`}>{card.set.name}</Link>
        ) : (
          <span>Set onbekend</span>
        )}
        <span>/</span>
        <strong>{card.name}</strong>
      </nav>

      <div className="card-profile">
        <section className="profile-art">
          <div className="profile-art-label">CATALOGUS / #{card.local_id}</div>
          <div className="profile-card-frame">
            <CardImage
              src={card.large_image_url || card.small_image_url}
              alt={card.name}
              priority
            />
          </div>
          <Link href="/scan" className="ink-button red">
            Scan jouw exemplaar <span aria-hidden="true">↗</span>
          </Link>
        </section>

        <section className="profile-copy">
          <p className="eyebrow">
            <span className="red-square" /> KAARTPROFIEL /{" "}
            {card.language?.toUpperCase() || "EN"}
          </p>
          <h1>{card.name}</h1>
          <div className="profile-badges">
            <span>#{card.local_id}</span>
            {card.rarity && <span>{card.rarity}</span>}
            {card.hp != null && <span className="red-badge">{card.hp} HP</span>}
            {card.status === "stale" && <span>Gecachte gegevens</span>}
          </div>
          {card.set && (
            <Link
              href={`/sets/${card.set.external_id}`}
              className="set-callout"
            >
              <span>UIT DE SET</span>
              <strong>{card.set.name}</strong>
              <b>→</b>
            </Link>
          )}

          <div className="detail-section">
            <div className="detail-section-heading">
              <span>01</span>
              <h2>Kaartgegevens</h2>
            </div>
            {specs.length ? (
              <dl className="spec-grid">
                {specs.map(([label, value]) => (
                  <div key={String(label)}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="muted-copy">
                Voor deze kaart zijn nog geen extra gegevens beschikbaar.
              </p>
            )}
          </div>

          {variants.length > 0 && (
            <div className="detail-section">
              <div className="detail-section-heading">
                <span>02</span>
                <h2>Drukvarianten</h2>
              </div>
              <div className="variant-list">
                {variants.map((variant) => (
                  <span key={variant}>
                    {variant.replace(/([A-Z])/g, " $1")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {card.attacks && card.attacks.length > 0 && (
            <div className="detail-section">
              <div className="detail-section-heading">
                <span>03</span>
                <h2>Aanvallen</h2>
              </div>
              <div className="move-list">
                {card.attacks.map((attack, index) => (
                  <article key={`${attack.name}-${index}`}>
                    <div>
                      <strong>{attack.name || "Onbekende aanval"}</strong>
                      {attack.damage != null && <b>{attack.damage}</b>}
                    </div>
                    {attack.cost?.length ? (
                      <small>{attack.cost.join(" · ")}</small>
                    ) : null}
                    {attack.effect && <p>{attack.effect}</p>}
                  </article>
                ))}
              </div>
            </div>
          )}

          {card.abilities && card.abilities.length > 0 && (
            <div className="detail-section">
              <div className="detail-section-heading">
                <span>04</span>
                <h2>Vaardigheden</h2>
              </div>
              <div className="move-list">
                {card.abilities.map((ability, index) => (
                  <article key={`${ability.name}-${index}`}>
                    <div>
                      <strong>{ability.name || "Vaardigheid"}</strong>
                      <small>{ability.type}</small>
                    </div>
                    {ability.effect && <p>{ability.effect}</p>}
                  </article>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
