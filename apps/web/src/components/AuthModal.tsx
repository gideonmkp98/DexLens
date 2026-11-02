"use client";

import { useEffect, useRef, useState } from "react";

export interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  initialMode?: "login" | "register";
}

export default function AuthModal({
  isOpen,
  onClose,
  onSuccess,
  initialMode = "login",
}: AuthModalProps) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setMode(initialMode);
      setError(null);
      setSuccessMsg(null);
      setTimeout(() => emailInputRef.current?.focus(), 50);
    }
  }, [isOpen, initialMode]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !trimmedEmail.includes("@")) {
      setError("Vul een geldig e-mailadres in.");
      return;
    }
    if (password.length < 8) {
      setError("Wachtwoord moet minimaal 8 tekens bevatten.");
      return;
    }

    setLoading(true);

    try {
      const endpoint =
        mode === "register" ? "/api/v1/auth/register" : "/api/v1/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: trimmedEmail, password }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        const detailMsg =
          errJson.detail?.message ||
          errJson.detail ||
          "Inloggen mislukt. Controleer je gegevens.";
        throw new Error(
          typeof detailMsg === "string" ? detailMsg : "Ongeldige inloggegevens."
        );
      }

      setSuccessMsg(
        mode === "register"
          ? "Account succesvol aangemaakt!"
          : "Succesvol ingelogd!"
      );
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Er ging iets mis.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-sm rounded-[5px] border border-[#f3efdf]/30 bg-[#20251f] p-5 text-[#f3efdf] shadow-[5px_5px_0_#10150f] sm:p-6">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#f3efdf]/15 pb-3">
          <div className="flex items-center gap-2">
            <span
              className="pokeball brand-ball !h-6 !w-6"
              aria-hidden="true"
            />
            <h2
              id="auth-modal-title"
              className="font-serif text-base font-bold tracking-tight text-[#f3efdf]"
            >
              {mode === "login"
                ? "Inloggen bij DexLens"
                : "Nieuw Account Maken"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-[3px] border border-[#f3efdf]/30 text-xs font-bold text-[#f3efdf] hover:border-[#f1ca53]"
            aria-label="Sluit inlogscherm"
          >
            ✕
          </button>
        </div>

        {/* Tab switcher */}
        <div className="mt-4 flex rounded-[3px] border border-[#f3efdf]/20 bg-[#171c16] p-0.5">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`flex-1 rounded-[2px] py-1.5 text-xs font-bold transition ${
              mode === "login"
                ? "bg-[#252923] text-[#f1ca53] shadow-[1px_1px_0_#10150f]"
                : "text-[#b6bbaa] hover:text-[#f3efdf]"
            }`}
          >
            Inloggen
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`flex-1 rounded-[2px] py-1.5 text-xs font-bold transition ${
              mode === "register"
                ? "bg-[#252923] text-[#f1ca53] shadow-[1px_1px_0_#10150f]"
                : "text-[#b6bbaa] hover:text-[#f3efdf]"
            }`}
          >
            Registreren
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label
              className="block text-[11px] font-bold text-[#b6bbaa]"
              htmlFor="auth-email"
            >
              E-mailadres
            </label>
            <input
              id="auth-email"
              ref={emailInputRef}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="verzamelaar@voorbeeld.nl"
              className="mt-1 w-full rounded-[3px] border border-[#f3efdf]/25 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] placeholder-[#b6bbaa]/40 focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          <div>
            <label
              className="block text-[11px] font-bold text-[#b6bbaa]"
              htmlFor="auth-password"
            >
              Wachtwoord (minimaal 8 tekens)
            </label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              placeholder="••••••••"
              className="mt-1 w-full rounded-[3px] border border-[#f3efdf]/25 bg-[#171c16] px-3 py-2 text-xs text-[#f3efdf] placeholder-[#b6bbaa]/40 focus:border-[#f1ca53] focus:outline-none"
            />
          </div>

          {error && (
            <div className="rounded-[3px] border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 p-2 text-xs text-[#eb6b5d]">
              {error}
            </div>
          )}

          {successMsg && (
            <div className="rounded-[3px] border border-emerald-500/40 bg-emerald-950/40 p-2 text-xs font-bold text-emerald-300">
              {successMsg}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-[5px] border border-[#c6372e] bg-[#c6372e] py-2.5 text-xs font-black uppercase tracking-wider text-[#fffcf5] shadow-[3px_3px_0_#10150f] transition hover:brightness-110 disabled:opacity-50"
          >
            {loading
              ? "Verwerken…"
              : mode === "login"
                ? "Inloggen"
                : "Account Maken"}
          </button>
        </form>

        <p className="mt-3 text-center text-[10px] text-[#b6bbaa]">
          Geen reclame, geen cookies van derden. Veilige
          Argon2id-wachtwoordhashing.
        </p>
      </div>
    </div>
  );
}
