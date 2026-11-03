"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "@/components/ThemeToggle";
import AuthModal from "@/components/AuthModal";
import { useAuth } from "@/contexts/AuthContext";

export default function AppHeader() {
  const pathname = usePathname();
  const { status, user, logout, refreshAuth } = useAuth();
  const [showAuthModal, setShowAuthModal] = useState<boolean>(false);
  const [authActionError, setAuthActionError] = useState<string | null>(null);

  const handleLogout = async () => {
    setAuthActionError(null);
    try {
      await logout();
    } catch (error) {
      setAuthActionError(
        error instanceof Error
          ? error.message
          : "Uitloggen is niet gelukt. Probeer het opnieuw."
      );
    }
  };

  const handleAuthRetry = async () => {
    setAuthActionError(null);
    try {
      await refreshAuth();
    } catch {
      setAuthActionError(
        "Je accountstatus kon niet worden geladen. Controleer je verbinding."
      );
    }
  };

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
              ["/collection", "Collectie"],
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
          {status === "loading" ? (
            <div
              className="header-auth-skeleton"
              aria-label="Account laden..."
              role="status"
            />
          ) : status === "error" ? (
            <button
              type="button"
              onClick={handleAuthRetry}
              className="ink-button secondary small"
              title="Accountstatus opnieuw laden"
            >
              Opnieuw
            </button>
          ) : status === "authenticated" && user ? (
            <div className="flex items-center gap-2">
              <span
                className="hidden max-w-[140px] truncate font-mono text-[11px] font-bold text-[var(--muted)] lg:inline"
                title={user.email}
              >
                {user.email}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                className="ink-button secondary small"
                title={`Ingelogd als ${user.email}`}
              >
                Uitloggen
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAuthModal(true)}
              className="ink-button secondary small"
            >
              Inloggen
            </button>
          )}
          <Link className="ink-button red small header-scan-btn" href="/scan">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span>Live Scanner</span>
            </span>
            <span aria-hidden="true">◎</span>
          </Link>
          {authActionError ? (
            <span className="header-auth-error" role="alert">
              {authActionError}
            </span>
          ) : null}
        </div>
      </div>
      <AuthModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
      />
    </header>
  );
}
