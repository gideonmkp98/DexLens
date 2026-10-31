import Image from "next/image";
import Link from "next/link";

export default function HomePage() {
  return (
    <main className="collector-page">
      <section className="home-hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="red-square" /> VOOR VERZAMELAARS. UIT
            NIEUWSGIERIGHEID.
          </p>
          <h1>
            Oude favoriet.
            <br />
            Nieuwe vondst.
            <br />
            <em>Welke heb jij?</em>
          </h1>
          <p className="hero-intro">
            Van die eerste Pikachu tot je nieuwste pull. Geef je Pokémon-kaart
            een naam, een set en een plek in het verhaal.
          </p>
          <div className="hero-buttons">
            <Link href="/scan" className="ink-button red">
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                <span>Live Scanner</span>
              </span>
              <span aria-hidden="true">◎</span>
            </Link>
            <Link href="/collection" className="ink-button secondary">
              Mijn collectie
            </Link>
            <Link href="/cards" className="text-link">
              Duik in de catalogus →
            </Link>
          </div>
          <p className="small-note">
            Real-time live camera herkenning & instant collectiebevestiging.
          </p>
        </div>
        <div className="card-showcase">
          <span className="showcase-caption">UIT DE OUDE SCHOENENDOOS</span>
          <div className="card-fan">
            <Image
              className="fan-card fan-left"
              src="/cards/flareon.webp"
              alt="Flareon uit Jungle"
              width={250}
              height={350}
              priority
            />
            <Image
              className="fan-card fan-right"
              src="/cards/charizard.webp"
              alt="Charizard uit Base Set"
              width={250}
              height={350}
              priority
            />
            <Image
              className="fan-card fan-front"
              src="/cards/pikachu.webp"
              alt="Pikachu uit Base Set"
              width={250}
              height={350}
              priority
            />
          </div>
          <span className="collector-stamp">
            ÉCHTE KAARTEN.
            <br />
            GOEDE VERHALEN.
          </span>
          <span className="showcase-bottom">BASE SET & JUNGLE · 1999</span>
        </div>
      </section>
      <div className="collector-strip">
        <span>VAN BASE SET TOT NU</span>
        <span aria-hidden="true">✦</span>
        <span>ONTDEK JOUW KAART</span>
        <span aria-hidden="true">✦</span>
        <span>BEKIJK DE HELE SET</span>
      </div>
      <section className="home-explore">
        <div className="home-explore-intro">
          <p className="eyebrow">BLADEREN MAG OOK</p>
          <h2>Het begint bij één kaart.</h2>
          <p>
            Zoek een bekende naam, bekijk een hele uitbreiding of beheer je
            eigen verzameling.
          </p>
        </div>
        <Link href="/cards" className="explore-ticket">
          <span className="ticket-number">01 / CATALOGUS</span>
          <h3>
            Zoek jouw favoriet <span>↗</span>
          </h3>
          <p>Kaartnaam, nummer of set. Jij kiest.</p>
        </Link>
        <Link href="/sets" className="explore-ticket yellow">
          <span className="ticket-number">02 / UITBREIDINGEN</span>
          <h3>
            Open een set <span>↗</span>
          </h3>
          <p>Van de klassiekers tot recente releases.</p>
        </Link>
        <Link href="/collection" className="explore-ticket">
          <span className="ticket-number">03 / VERZAMELING</span>
          <h3>
            Jouw collectie <span>↗</span>
          </h3>
          <p>Beheer je exemplaren, condities en dubbelen.</p>
        </Link>
      </section>
    </main>
  );
}
