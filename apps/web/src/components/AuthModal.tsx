"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  normalizeEmail,
  normalizeUsername,
  validateEmail,
  validatePassword,
  validateRegistration,
} from "@/lib/authValidation";

export interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void | Promise<void>;
  initialMode?: "login" | "register";
}

export default function AuthModal({
  isOpen,
  onClose,
  onSuccess,
  initialMode = "login",
}: AuthModalProps) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [username, setUsername] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [passwordConfirm, setPasswordConfirm] = useState<string>("");
  const [acceptedPolicies, setAcceptedPolicies] = useState<boolean>(true);
  const [betaCode, setBetaCode] = useState<string>("");
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setMode(initialMode);
      setError(null);
      setSuccessMsg(null);
      setBetaCode("");
      if (typeof window !== "undefined" && window.location.hash) {
        const hash = window.location.hash.substring(1);
        const params = new URLSearchParams(hash);
        const token = params.get("token") || params.get("invite");
        if (token) {
          setInviteToken(token);
          setMode("register");
        }
      }
      const timer = setTimeout(() => {
        if (
          !document.activeElement ||
          document.activeElement === document.body ||
          document.activeElement.tagName === "BUTTON"
        ) {
          emailInputRef.current?.focus();
        }
      }, 50);
      return () => clearTimeout(timer);
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

    const trimmedEmail = normalizeEmail(email);

    if (mode === "register") {
      const trimmedUsername = normalizeUsername(username);
      const valResult = validateRegistration({
        username: trimmedUsername || undefined,
        email: trimmedEmail,
        password,
        passwordConfirmation: passwordConfirm || undefined,
        acceptedPolicies,
      });

      if (!valResult.valid) {
        setError(valResult.error || "Validatiefout.");
        return;
      }

      setLoading(true);
      try {
        await register({
          email: trimmedEmail,
          password,
          username: trimmedUsername || undefined,
          password_confirmation: passwordConfirm || undefined,
          accepted_policies: acceptedPolicies,
          beta_code: betaCode.trim() || undefined,
          invite_token: inviteToken || undefined,
        });
        setSuccessMsg("Account succesvol aangemaakt!");

        if (onSuccess) {
          await onSuccess();
        }

        // Smooth visual feedback before closing modal
        await new Promise((resolve) => setTimeout(resolve, 250));
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Er ging iets mis.");
      } finally {
        setLoading(false);
      }
    } else {
      const emailVal = validateEmail(trimmedEmail);
      if (!emailVal.valid) {
        setError(emailVal.error || "Vul een geldig e-mailadres in.");
        return;
      }

      const passVal = validatePassword(password, 8);
      if (!passVal.valid) {
        setError(
          passVal.error || "Wachtwoord moet minimaal 8 tekens bevatten."
        );
        return;
      }

      setLoading(true);
      try {
        await login({ email: trimmedEmail, password });
        setSuccessMsg("Succesvol ingelogd!");

        if (onSuccess) {
          await onSuccess();
        }

        // Smooth visual feedback before closing modal
        await new Promise((resolve) => setTimeout(resolve, 250));
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Er ging iets mis.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
      aria-describedby="auth-modal-description"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm sm:p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] px-5 py-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f] sm:px-8 sm:py-8">
        {/* Header */}
        <div className="flex items-start justify-between gap-6 border-b border-[#f3efdf]/15 pb-5">
          <div className="flex min-w-0 items-start gap-3.5">
            <span
              className="pokeball brand-ball mt-0.5 !h-8 !w-8"
              aria-hidden="true"
            />
            <div>
              <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#f1ca53]">
                Jouw kaarten. Jouw collectie.
              </p>
              <h2
                id="auth-modal-title"
                className="font-serif text-[24px] font-bold leading-tight tracking-[-0.02em] text-[#f3efdf] sm:text-[27px]"
              >
                {mode === "login" ? "Welkom terug" : "Maak je account"}
              </h2>
              <p
                id="auth-modal-description"
                className="mt-2 max-w-[30ch] text-[13px] leading-relaxed text-[#b6bbaa]"
              >
                {mode === "login"
                  ? "Log in om verder te gaan met je scans en verzameling."
                  : "Bewaar je scans en neem je collectie mee naar ieder apparaat."}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[4px] border border-[#f3efdf]/25 text-sm font-bold text-[#b6bbaa] transition hover:border-[#f1ca53] hover:text-[#f3efdf]"
            aria-label="Sluit inlogscherm"
          >
            ✕
          </button>
        </div>

        {/* Tab switcher */}
        <div className="mt-6 flex rounded-[4px] border border-[#f3efdf]/20 bg-[#171c16] p-1">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`flex-1 rounded-[3px] px-3 py-2.5 text-[13px] font-bold tracking-wide transition ${
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
            className={`flex-1 rounded-[3px] px-3 py-2.5 text-[13px] font-bold tracking-wide transition ${
              mode === "register"
                ? "bg-[#252923] text-[#f1ca53] shadow-[1px_1px_0_#10150f]"
                : "text-[#b6bbaa] hover:text-[#f3efdf]"
            }`}
          >
            Registreren
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate className="mt-7 space-y-4">
          {mode === "register" && (
            <div>
              <label
                className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
                htmlFor="auth-username"
              >
                Gebruikersnaam (optioneel)
              </label>
              <input
                id="auth-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="bijv. pokeverzamelaar"
                aria-invalid={!!error && error.includes("Gebruikersnaam")}
                className="mt-1.5 w-full rounded-[4px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-[14px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:border-[#f1ca53] focus:outline-none focus:ring-1 focus:ring-[#f1ca53]/40"
              />
              <p className="mt-1 text-[11px] text-[#8f9587]">
                3-30 tekens (letters, cijfers, streepjes en underscores).
              </p>
            </div>
          )}

          <div>
            <label
              className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
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
              aria-invalid={!!error && error.includes("e-mailadres")}
              className="mt-1.5 w-full rounded-[4px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-[14px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:border-[#f1ca53] focus:outline-none focus:ring-1 focus:ring-[#f1ca53]/40"
            />
          </div>

          {mode === "register" && (
            <div>
              <label
                className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
                htmlFor="auth-beta-code"
              >
                Bètacode of Uitnodiging{" "}
                <span className="font-normal normal-case text-[#8f9587]">
                  (optioneel tenzij vereist)
                </span>
              </label>
              <input
                id="auth-beta-code"
                type="text"
                value={betaCode}
                onChange={(e) => setBetaCode(e.target.value)}
                placeholder="BETA-XXXX-XXXX"
                className="mt-2 w-full rounded-[4px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3.5 font-mono text-[15px] uppercase leading-5 text-[#f3efdf] placeholder:font-sans placeholder:normal-case placeholder:text-[#b6bbaa]/45 focus:border-[#f1ca53] focus:outline-none focus:ring-1 focus:ring-[#f1ca53]/40"
              />
            </div>
          )}

          <div>
            <label
              className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
              htmlFor="auth-password"
            >
              {mode === "register"
                ? "Wachtwoord (minimaal 15 tekens)"
                : "Wachtwoord"}
            </label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "register" ? 15 : 8}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              placeholder="•••••••••••••••"
              aria-invalid={!!error && error.includes("Wachtwoord")}
              aria-describedby={
                mode === "register" ? "password-policy-hint" : undefined
              }
              className="mt-1.5 w-full rounded-[4px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-[14px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:border-[#f1ca53] focus:outline-none focus:ring-1 focus:ring-[#f1ca53]/40"
            />
            {mode === "register" && (
              <p
                id="password-policy-hint"
                className="mt-1 text-[11px] text-[#8f9587]"
              >
                Minimaal 15 tekens. Wachtwoordzinnen en wachtwoordmanagers zijn
                toegestaan.
              </p>
            )}
          </div>

          {mode === "register" && (
            <div>
              <label
                className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
                htmlFor="auth-password-confirm"
              >
                Bevestig wachtwoord
              </label>
              <input
                id="auth-password-confirm"
                type="password"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                autoComplete="new-password"
                placeholder="•••••••••••••••"
                aria-invalid={!!error && error.includes("overeen")}
                className="mt-1.5 w-full rounded-[4px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-[14px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:border-[#f1ca53] focus:outline-none focus:ring-1 focus:ring-[#f1ca53]/40"
              />
            </div>
          )}

          {mode === "register" && (
            <div className="flex items-start gap-3 pt-1">
              <input
                id="auth-policies"
                type="checkbox"
                checked={acceptedPolicies}
                onChange={(e) => setAcceptedPolicies(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-[#f3efdf]/30 bg-[#171c16] text-[#f1ca53] focus:ring-[#f1ca53]"
              />
              <label
                htmlFor="auth-policies"
                className="text-[12px] leading-relaxed text-[#d8dacd]"
              >
                Ik ga akkoord met de{" "}
                <a
                  href="/terms"
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-[#f1ca53]"
                >
                  gebruiksvoorwaarden
                </a>{" "}
                en het{" "}
                <a
                  href="/privacy"
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-[#f1ca53]"
                >
                  privacybeleid
                </a>
                .
              </label>
            </div>
          )}

          {error && (
            <div
              role="alert"
              aria-live="assertive"
              className="rounded-[4px] border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 px-3.5 py-3 text-[13px] leading-relaxed text-[#ff9387]"
            >
              {error}
            </div>
          )}

          {successMsg && (
            <div
              role="status"
              className="rounded-[4px] border border-emerald-500/40 bg-emerald-950/40 px-3.5 py-3 text-[13px] font-bold leading-relaxed text-emerald-300"
            >
              {successMsg}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-[5px] border border-[#c6372e] bg-[#c6372e] px-5 py-3.5 text-[13px] font-black uppercase tracking-[0.12em] text-[#fffcf5] shadow-[4px_4px_0_#10150f] transition hover:-translate-y-0.5 hover:brightness-110 disabled:translate-y-0 disabled:opacity-50"
          >
            {loading
              ? "Verwerken…"
              : mode === "login"
                ? "Inloggen"
                : "Account Maken"}
          </button>
        </form>

        <div className="mt-6 border-t border-[#f3efdf]/10 pt-4 text-center">
          <p className="text-[11px] leading-relaxed text-[#8f9587]">
            Geen reclame of cookies van derden.
            <br className="hidden sm:block" /> Je wachtwoord wordt veilig
            beschermd met Argon2id en gecontroleerd tegen bekende datalekken.
          </p>
        </div>
      </div>
    </div>
  );
}
