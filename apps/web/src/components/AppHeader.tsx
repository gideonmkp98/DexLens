"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "@/components/ThemeToggle";
import AuthModal from "@/components/AuthModal";
import {
  ensureBrowserSession,
  resetBrowserSessionBootstrap,
} from "@/lib/session";

export default function AppHeader() {
  const pathname = usePathname();
  const [user, setUser] = useState<{
    id: string;
    email: string;
    role: string;
  } | null>(null);
  const [showAuthModal, setShowAuthModal] = useState<boolean>(false);

  const checkUser = useCallback(async () => {
    try {
      const data = await ensureBrowserSession();
      if (data.user) {
        setUser(data.user);
        return;
      }
      setUser(null);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    void checkUser();
  }, [checkUser]);

  const handleLogout = async () => {
    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "include",
      });
      resetBrowserSessionBootstrap();
      setUser(null);
      window.location.reload();
    } catch {
      // Non-fatal
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
          {user ? (
            <button
              type="button"
              onClick={handleLogout}
              className="ink-button secondary small"
              title={`Ingelogd als ${user.email}`}
            >
              Uitloggen
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowAuthModal(true)}
              className="ink-button secondary small"
            >
              Inloggen
            </button>
          )}
          <Link className="ink-button red small" href="/scan">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span>Live Scanner</span>
            </span>
            <span aria-hidden="true">◎</span>
          </Link>
        </div>
      </div>
      <AuthModal
        isOpen={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        onSuccess={checkUser}
      />
    </header>
  );
}
