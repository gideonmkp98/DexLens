"use client";

import { useEffect, useRef, useState } from "react";

type Theme = "light" | "dark";

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);
  const preference = useRef<Theme | null>(null);

  function applyTheme(dark: boolean) {
    document.documentElement.classList.toggle("dark", dark);
    setIsDark(dark);
  }

  useEffect(() => {
    const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
    const syncPreference = () => {
      try {
        const saved = localStorage.getItem("theme");
        preference.current =
          saved === "dark" || saved === "light" ? saved : null;
      } catch {
        // Theme switching still works when browser storage is unavailable.
      }
      applyTheme(
        preference.current ? preference.current === "dark" : systemTheme.matches
      );
    };
    const onSystemChange = () => {
      if (preference.current === null) applyTheme(systemTheme.matches);
    };
    const onStorageChange = (event: StorageEvent) => {
      if (event.key === "theme" || event.key === null) syncPreference();
    };

    syncPreference();
    systemTheme.addEventListener("change", onSystemChange);
    window.addEventListener("storage", onStorageChange);
    return () => {
      systemTheme.removeEventListener("change", onSystemChange);
      window.removeEventListener("storage", onStorageChange);
    };
  }, []);

  const label = isDark ? "Licht thema inschakelen" : "Donker thema inschakelen";

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => {
        const next = !document.documentElement.classList.contains("dark");
        preference.current = next ? "dark" : "light";
        applyTheme(next);
        try {
          localStorage.setItem("theme", preference.current);
        } catch {
          // Retain the preference for this page even without persistent storage.
        }
      }}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-white/20 dark:hover:bg-zinc-800"
    >
      {/* Sun Icon (shown in dark mode) */}
      <svg
        className="hidden h-4 w-4 dark:block"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="1.75"
      >
        <circle cx="12" cy="12" r="5" />
        <path
          strokeLinecap="round"
          d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
        />
      </svg>
      {/* Moon Icon (shown in light mode) */}
      <svg
        className="block h-4 w-4 dark:hidden"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth="1.75"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
        />
      </svg>
    </button>
  );
}
