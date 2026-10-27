"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "@/components/ThemeToggle";

export default function AppHeader() {
  const pathname = usePathname();
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="brand" aria-label="DexLens startpagina">
          <span className="pokeball brand-ball" aria-hidden="true" />
          <span>
            DexLens<span className="brand-sub">POKÉMON CARD SCANNER</span>
          </span>
        </Link>
        <nav className="desktop-nav" aria-label="Hoofdnavigatie">
          {(
            [
              ["/", "Start"],
              ["/cards", "Kaarten"],
              ["/sets", "Sets"],
            ] as const
          ).map(([href, label]) => (
            <Link
              key={href}
              href={href}
              aria-current={
                (href === "/" ? pathname === href : pathname.startsWith(href))
                  ? "page"
                  : undefined
              }
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="header-actions">
          <ThemeToggle />
          <Link className="ink-button red small" href="/scan">
            Scan een kaart <span aria-hidden="true">↗</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
