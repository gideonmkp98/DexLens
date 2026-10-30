import Link from "next/link";
export default function Footer() {
  return (
    <footer className="site-footer">
      <div>
        <strong>DexLens.</strong>
        <span>Voor de kaarten die je wilt kennen.</span>
      </div>
      <div className="footer-links">
        <Link href="/collection">Collectie</Link>
        <Link href="/scan">Scannen</Link>
        <Link href="/cards">Catalogus</Link>
        <Link href="/sets">Sets</Link>
      </div>
      <p>
        Een onafhankelijke tool voor verzamelaars. Kaartgegevens via TCGdex.
        Pokémon © Nintendo / Creatures / GAME FREAK.
      </p>
    </footer>
  );
}
