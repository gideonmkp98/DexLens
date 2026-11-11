"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import AuthModal from "@/components/AuthModal";
import { useAuth } from "@/contexts/AuthContext";
import {
  classifyInvitationError,
  extractInvitationToken,
  sanitizeInvitationUrl,
  validateInvitation,
} from "@/lib/invitation";

export type InviteUIState =
  | "loading"
  | "valid"
  | "invalid"
  | "expired"
  | "revoked"
  | "already_used"
  | "email_mismatch"
  | "success";

function InviteContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { status: authStatus, user, register, logout } = useAuth();

  const [state, setState] = useState<InviteUIState>("loading");
  const [maskedEmail, setMaskedEmail] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Form fields
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
    confirmPassword?: string;
  }>({});
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Auth modal toggle for login redirection
  const [showLoginModal, setShowLoginModal] = useState<boolean>(false);

  // Auto-redirect timer for success state
  const [redirectCountdown, setRedirectCountdown] = useState<number>(3);

  // Keep token strictly in memory - never render or log
  const tokenRef = useRef<string | null>(null);
  const initialValidationAttempted = useRef<boolean>(false);
  const emailInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (initialValidationAttempted.current) return;
    initialValidationAttempted.current = true;

    if (typeof window === "undefined") return;

    // 1. Extract token safely (fragment #token= / #invite= prioritized over searchParams)
    const hash = window.location.hash || "";
    const search = window.location.search || searchParams.toString() || "";
    const extractedToken = extractInvitationToken(hash, search);

    // 2. Scrub browser history immediately so the token does not linger in URL or referrer
    if (hash || search.includes("token") || search.includes("invite")) {
      const cleanUrl = sanitizeInvitationUrl(window.location.href);
      window.history.replaceState(null, "", cleanUrl);
    }

    if (!extractedToken) {
      setState("invalid");
      setErrorMessage(
        "Geen uitnodigingstoken gevonden. Controleer de link in je uitnodigingsmail."
      );
      return;
    }

    tokenRef.current = extractedToken;

    // 3. Validate with backend endpoint
    let isMounted = true;
    setState("loading");

    validateInvitation(extractedToken)
      .then((res) => {
        if (!isMounted) return;

        if (res.valid) {
          setMaskedEmail(res.masked_email || null);
          setState("valid");
          setTimeout(() => {
            emailInputRef.current?.focus();
          }, 100);
        } else {
          const reason = classifyInvitationError(res.message);
          setState(reason);
          setErrorMessage(
            res.message || "Deze uitnodiging is niet langer geldig."
          );
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setState("invalid");
        setErrorMessage(
          "Er kon geen verbinding worden gemaakt met de verificatieserver. Probeer het later opnieuw."
        );
      });

    return () => {
      isMounted = false;
    };
  }, [searchParams]);

  // Handle auto-redirect on success
  useEffect(() => {
    if (state !== "success") return;

    if (redirectCountdown <= 0) {
      router.push("/scan");
      return;
    }

    const timer = setTimeout(() => {
      setRedirectCountdown((prev) => prev - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [state, redirectCountdown, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    const currentToken = tokenRef.current;
    if (!currentToken) {
      setState("invalid");
      setErrorMessage("Uitnodigingstoken ontbreekt. Herlaad de uitnodigingslink.");
      return;
    }

    // Client-side validations
    const errors: {
      email?: string;
      password?: string;
      confirmPassword?: string;
    } = {};

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !trimmedEmail.includes("@") || !trimmedEmail.includes(".")) {
      errors.email = "Vul een geldig e-mailadres in.";
    }

    if (password.length < 8) {
      errors.password = "Wachtwoord moet minimaal 8 tekens bevatten.";
    }

    if (password !== confirmPassword) {
      errors.confirmPassword = "Wachtwoorden komen niet overeen.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await register({
        email: trimmedEmail,
        password,
        invite_token: currentToken,
      });

      setState("success");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Registreren mislukt.";

      if (
        msg.includes("niet geldig voor dit e-mailadres") ||
        msg.includes("INVITATION_EMAIL_MISMATCH")
      ) {
        setState("email_mismatch");
        setErrorMessage(
          "Dit e-mailadres komt niet overeen met het uitgenodigde adres. Vul het e-mailadres in waarop je de uitnodiging hebt ontvangen."
        );
      } else if (
        msg.includes("al in gebruik") ||
        msg.includes("EMAIL_ALREADY_EXISTS")
      ) {
        setFieldErrors({
          email:
            "Er bestaat al een account met dit e-mailadres. Log in om je uitnodiging te activeren.",
        });
      } else if (msg.includes("verlopen")) {
        setState("expired");
        setErrorMessage("Deze uitnodiging is inmiddels verlopen.");
      } else if (msg.includes("al gebruikt") || msg.includes("geaccepteerd")) {
        setState("already_used");
        setErrorMessage("Deze uitnodiging is al geaccepteerd.");
      } else if (msg.includes("ingetrokken")) {
        setState("revoked");
        setErrorMessage("Deze uitnodiging is ingetrokken.");
      } else {
        setErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-[calc(100vh-140px)] w-full max-w-xl flex-col items-center justify-center px-4 py-12 sm:px-6"
    >
      <div className="w-full rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-6 text-[#f3efdf] shadow-[7px_7px_0_#10150f] sm:p-8">
        {/* Brand Header */}
        <div className="flex items-start justify-between gap-4 border-b border-[#f3efdf]/15 pb-5">
          <div className="flex items-start gap-3.5">
            <span
              className="pokeball brand-ball mt-0.5 !h-8 !w-8 shrink-0"
              aria-hidden="true"
            />
            <div>
              <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#f1ca53]">
                DexLens Bèta • Exclusieve Toegang
              </p>
              <h1 className="font-serif text-[24px] font-bold leading-tight tracking-[-0.02em] text-[#f3efdf] sm:text-[27px]">
                {state === "loading" && "Uitnodiging Verifiëren…"}
                {(state === "valid" || state === "email_mismatch") &&
                  "Activeer je Bèta Toegang"}
                {state === "invalid" && "Ongeldige Uitnodiging"}
                {state === "expired" && "Uitnodiging Verlopen"}
                {state === "revoked" && "Uitnodiging Ingetrokken"}
                {state === "already_used" && "Uitnodiging Reeds Gebruikt"}
                {state === "success" && "Welkom bij DexLens!"}
              </h1>
            </div>
          </div>
        </div>

        {/* Existing Session Notice */}
        {authStatus === "authenticated" && user && state !== "success" && (
          <div className="mt-5 rounded-[4px] border border-[#f1ca53]/30 bg-[#171c16] p-3 text-[13px] text-[#f3efdf]">
            <p>
              Je bent momenteel ingelogd als{" "}
              <strong className="font-mono text-[#f1ca53]">{user.email}</strong>.
            </p>
            <p className="mt-1 text-[11px] text-[#b6bbaa]">
              Wil je deze uitnodiging koppelen aan een ander account?{" "}
              <button
                type="button"
                onClick={() => logout()}
                className="font-bold underline hover:text-[#f1ca53]"
              >
                Log dan eerst uit
              </button>
              .
            </p>
          </div>
        )}

        {/* STATE: LOADING */}
        {state === "loading" && (
          <div
            role="status"
            aria-live="polite"
            className="flex flex-col items-center justify-center py-12 text-center"
          >
            <div
              className="pokeball mb-4 h-12 w-12 animate-spin border-[#f1ca53]"
              aria-hidden="true"
              style={{ animationDuration: "1.2s" }}
            />
            <p className="font-mono text-[12px] font-bold uppercase tracking-[0.14em] text-[#f1ca53]">
              Bezig met controleren…
            </p>
            <p className="mt-2 text-[13px] text-[#b6bbaa]">
              Een ogenblik geduld terwijl we je persoonlijke uitnodigingstoken verifiëren.
            </p>
          </div>
        )}

        {/* STATE: VALID OR EMAIL MISMATCH (REGISTRATION FORM) */}
        {(state === "valid" || state === "email_mismatch") && (
          <div className="mt-6">
            <p className="text-[13px] leading-relaxed text-[#b6bbaa]">
              Gefeliciteerd! Je hebt een persoonlijke uitnodiging ontvangen voor de
              exclusieve DexLens bèta. Maak hieronder je account aan om direct te
              starten met scannen.
            </p>

            {/* Masked Email Badge */}
            {maskedEmail && (
              <div className="mt-4 rounded-[4px] border border-[#f1ca53]/35 bg-[#171c16] px-4 py-3">
                <span className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#f1ca53]">
                  Uitgenodigd E-mailadres
                </span>
                <p className="mt-0.5 font-mono text-[14px] font-bold text-[#f3efdf]">
                  {maskedEmail}
                </p>
                <p className="mt-1 text-[11px] text-[#8f9587]">
                  Om veiligheidsredenen moet je registratie overeenkomen met dit e-mailadres.
                </p>
              </div>
            )}

            {/* Email Mismatch Alert */}
            {state === "email_mismatch" && (
              <div
                role="alert"
                aria-live="assertive"
                className="mt-4 rounded-[4px] border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 px-3.5 py-3 text-[13px] leading-relaxed text-[#ff9387]"
              >
                <p className="font-bold">E-mailadres komt niet overeen</p>
                <p className="mt-1 text-[12px]">
                  {errorMessage ||
                    "Dit uitnodigingstoken is niet geldig voor het ingevulde e-mailadres. Controleer of je het adres gebruikt waarop je de uitnodiging hebt ontvangen."}
                </p>
              </div>
            )}

            {/* General Form Error Alert */}
            {errorMessage && state === "valid" && (
              <div
                role="alert"
                aria-live="assertive"
                className="mt-4 rounded-[4px] border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 px-3.5 py-3 text-[13px] leading-relaxed text-[#ff9387]"
              >
                {errorMessage}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
              <div>
                <label
                  className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
                  htmlFor="invite-email"
                >
                  Je E-mailadres
                </label>
                <input
                  id="invite-email"
                  ref={emailInputRef}
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (state === "email_mismatch") setState("valid");
                    if (fieldErrors.email) {
                      setFieldErrors((prev) => ({ ...prev, email: undefined }));
                    }
                  }}
                  required
                  autoComplete="email"
                  placeholder="verzamelaar@voorbeeld.nl"
                  aria-invalid={Boolean(fieldErrors.email || state === "email_mismatch")}
                  aria-describedby={
                    fieldErrors.email ? "invite-email-error" : undefined
                  }
                  className={`mt-2 w-full rounded-[4px] border bg-[#171c16] px-4 py-3.5 text-[15px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:outline-none focus:ring-1 ${
                    fieldErrors.email || state === "email_mismatch"
                      ? "border-[#eb6b5d] focus:border-[#eb6b5d] focus:ring-[#eb6b5d]/40"
                      : "border-[#f3efdf]/25 focus:border-[#f1ca53] focus:ring-[#f1ca53]/40"
                  }`}
                />
                {fieldErrors.email && (
                  <p
                    id="invite-email-error"
                    className="mt-1 text-[12px] text-[#ff9387]"
                  >
                    {fieldErrors.email}
                  </p>
                )}
              </div>

              <div>
                <label
                  className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
                  htmlFor="invite-password"
                >
                  Kies een Wachtwoord (minimaal 8 tekens)
                </label>
                <input
                  id="invite-password"
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (fieldErrors.password) {
                      setFieldErrors((prev) => ({
                        ...prev,
                        password: undefined,
                      }));
                    }
                  }}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  placeholder="••••••••"
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={
                    fieldErrors.password ? "invite-password-error" : undefined
                  }
                  className={`mt-2 w-full rounded-[4px] border bg-[#171c16] px-4 py-3.5 text-[15px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:outline-none focus:ring-1 ${
                    fieldErrors.password
                      ? "border-[#eb6b5d] focus:border-[#eb6b5d] focus:ring-[#eb6b5d]/40"
                      : "border-[#f3efdf]/25 focus:border-[#f1ca53] focus:ring-[#f1ca53]/40"
                  }`}
                />
                {fieldErrors.password && (
                  <p
                    id="invite-password-error"
                    className="mt-1 text-[12px] text-[#ff9387]"
                  >
                    {fieldErrors.password}
                  </p>
                )}
              </div>

              <div>
                <label
                  className="block font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-[#d8dacd]"
                  htmlFor="invite-confirm-password"
                >
                  Bevestig Wachtwoord
                </label>
                <input
                  id="invite-confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    if (fieldErrors.confirmPassword) {
                      setFieldErrors((prev) => ({
                        ...prev,
                        confirmPassword: undefined,
                      }));
                    }
                  }}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  placeholder="••••••••"
                  aria-invalid={Boolean(fieldErrors.confirmPassword)}
                  aria-describedby={
                    fieldErrors.confirmPassword
                      ? "invite-confirm-password-error"
                      : undefined
                  }
                  className={`mt-2 w-full rounded-[4px] border bg-[#171c16] px-4 py-3.5 text-[15px] leading-5 text-[#f3efdf] placeholder:text-[#b6bbaa]/45 focus:outline-none focus:ring-1 ${
                    fieldErrors.confirmPassword
                      ? "border-[#eb6b5d] focus:border-[#eb6b5d] focus:ring-[#eb6b5d]/40"
                      : "border-[#f3efdf]/25 focus:border-[#f1ca53] focus:ring-[#f1ca53]/40"
                  }`}
                />
                {fieldErrors.confirmPassword && (
                  <p
                    id="invite-confirm-password-error"
                    className="mt-1 text-[12px] text-[#ff9387]"
                  >
                    {fieldErrors.confirmPassword}
                  </p>
                )}
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full rounded-[5px] border border-[#c6372e] bg-[#c6372e] px-5 py-3.5 text-[13px] font-black uppercase tracking-[0.12em] text-[#fffcf5] shadow-[4px_4px_0_#10150f] transition hover:-translate-y-0.5 hover:brightness-110 disabled:translate-y-0 disabled:opacity-50"
                >
                  {isSubmitting
                    ? "Bezig met activeren…"
                    : "Account Activeren & Starten"}
                </button>
              </div>
            </form>

            <div className="mt-6 border-t border-[#f3efdf]/10 pt-4 text-center">
              <p className="text-[11px] leading-relaxed text-[#8f9587]">
                Geen reclame of cookies van derden.
                <br className="hidden sm:block" /> Je wachtwoord wordt veilig
                beschermd met Argon2id.
              </p>
            </div>
          </div>
        )}

        {/* STATE: INVALID */}
        {state === "invalid" && (
          <div className="mt-6 space-y-4">
            <div className="rounded-[4px] border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 px-4 py-3.5 text-[13px] leading-relaxed text-[#ff9387]">
              <p className="font-bold">Uitnodiging ongeldig of niet gevonden</p>
              <p className="mt-1">
                {errorMessage ||
                  "Dit uitnodigingstoken is niet geldig. Controleer of je de volledige link uit je uitnodigingsmail hebt geopend."}
              </p>
            </div>
            <p className="text-[13px] leading-relaxed text-[#b6bbaa]">
              Uitnodigingen zijn eenmalig en hoofdlettergevoelig. Vraag een nieuwe
              uitnodiging aan bij de beheerder als je link beschadigd is.
            </p>
            <div className="mt-6 flex flex-col gap-3 pt-2 sm:flex-row">
              <Link
                href="/"
                className="flex-1 rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-center text-[13px] font-bold uppercase tracking-[0.12em] text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:border-[#f1ca53] hover:text-[#f1ca53]"
              >
                Naar Startpagina
              </Link>
              <button
                type="button"
                onClick={() => setShowLoginModal(true)}
                className="flex-1 rounded-[5px] border border-[#c6372e] bg-[#c6372e] px-4 py-3 text-center text-[13px] font-black uppercase tracking-[0.12em] text-[#fffcf5] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:brightness-110"
              >
                Inloggen
              </button>
            </div>
          </div>
        )}

        {/* STATE: EXPIRED */}
        {state === "expired" && (
          <div className="mt-6 space-y-4">
            <div className="rounded-[4px] border border-amber-500/40 bg-amber-950/30 px-4 py-3.5 text-[13px] leading-relaxed text-amber-200">
              <p className="font-bold">Uitnodiging is verlopen</p>
              <p className="mt-1">
                De geldigheidsduur van deze persoonlijke uitnodiging is verstreken.
              </p>
            </div>
            <p className="text-[13px] leading-relaxed text-[#b6bbaa]">
              Om veiligheidsredenen verlopen bètatoegangscodes na een bepaalde periode.
              Neem contact op met de beheerder of degene die je heeft uitgenodigd om een
              nieuwe uitnodiging te ontvangen.
            </p>
            <div className="mt-6 flex flex-col gap-3 pt-2 sm:flex-row">
              <Link
                href="/"
                className="flex-1 rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-center text-[13px] font-bold uppercase tracking-[0.12em] text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:border-[#f1ca53] hover:text-[#f1ca53]"
              >
                Naar Startpagina
              </Link>
              <button
                type="button"
                onClick={() => setShowLoginModal(true)}
                className="flex-1 rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-center text-[13px] font-bold uppercase tracking-[0.12em] text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:border-[#f1ca53] hover:text-[#f1ca53]"
              >
                Bestaand Account Inloggen
              </button>
            </div>
          </div>
        )}

        {/* STATE: REVOKED */}
        {state === "revoked" && (
          <div className="mt-6 space-y-4">
            <div className="rounded-[4px] border border-[#eb6b5d]/40 bg-[#eb6b5d]/10 px-4 py-3.5 text-[13px] leading-relaxed text-[#ff9387]">
              <p className="font-bold">Uitnodiging ingetrokken</p>
              <p className="mt-1">
                Deze persoonlijke uitnodiging is door de beheerder ingetrokken.
              </p>
            </div>
            <p className="text-[13px] leading-relaxed text-[#b6bbaa]">
              Deze link kan niet meer worden gebruikt voor registratie. Neem contact op
              met ondersteuning als je denkt dat dit een vergissing is.
            </p>
            <div className="mt-6 pt-2">
              <Link
                href="/"
                className="block w-full rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-center text-[13px] font-bold uppercase tracking-[0.12em] text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:border-[#f1ca53] hover:text-[#f1ca53]"
              >
                Naar Startpagina
              </Link>
            </div>
          </div>
        )}

        {/* STATE: ALREADY USED */}
        {state === "already_used" && (
          <div className="mt-6 space-y-4">
            <div className="rounded-[4px] border border-blue-500/40 bg-blue-950/30 px-4 py-3.5 text-[13px] leading-relaxed text-blue-200">
              <p className="font-bold">Deze uitnodiging is al geaccepteerd</p>
              <p className="mt-1">
                Er is al een verzamelaarsaccount geactiveerd met deze uitnodiging.
              </p>
            </div>
            <p className="text-[13px] leading-relaxed text-[#b6bbaa]">
              Als dit jouw uitnodiging was, kun je direct inloggen met je
              geregistreerde e-mailadres en wachtwoord.
            </p>
            <div className="mt-6 flex flex-col gap-3 pt-2 sm:flex-row">
              <button
                type="button"
                onClick={() => setShowLoginModal(true)}
                className="flex-1 rounded-[5px] border border-[#c6372e] bg-[#c6372e] px-4 py-3 text-center text-[13px] font-black uppercase tracking-[0.12em] text-[#fffcf5] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:brightness-110"
              >
                Inloggen
              </button>
              <Link
                href="/"
                className="flex-1 rounded-[5px] border border-[#f3efdf]/25 bg-[#171c16] px-4 py-3 text-center text-[13px] font-bold uppercase tracking-[0.12em] text-[#f3efdf] shadow-[3px_3px_0_#10150f] transition hover:-translate-y-0.5 hover:border-[#f1ca53] hover:text-[#f1ca53]"
              >
                Naar Startpagina
              </Link>
            </div>
          </div>
        )}

        {/* STATE: SUCCESS */}
        {state === "success" && (
          <div className="mt-6 space-y-5 text-center">
            <div className="rounded-[4px] border border-emerald-500/40 bg-emerald-950/40 p-5 text-emerald-300">
              <span className="pokeball mx-auto mb-3 !h-10 !w-10" aria-hidden="true" />
              <p className="font-serif text-[20px] font-bold text-[#f3efdf]">
                Uitnodiging Succesvol Geactiveerd!
              </p>
              <p className="mt-2 text-[13px] leading-relaxed text-emerald-200">
                Je account is aangemaakt en je hebt nu volledige toegang tot de
                DexLens bètacollectie en scanner.
              </p>
            </div>

            <p className="text-[12px] text-[#8f9587]">
              Je wordt over{" "}
              <strong className="text-[#f1ca53]">{redirectCountdown}</strong> seconden
              automatisch doorgestuurd naar de scanner…
            </p>

            <div className="pt-2">
              <Link
                href="/scan"
                className="inline-flex w-full items-center justify-center rounded-[5px] border border-[#c6372e] bg-[#c6372e] px-5 py-3.5 text-[13px] font-black uppercase tracking-[0.12em] text-[#fffcf5] shadow-[4px_4px_0_#10150f] transition hover:-translate-y-0.5 hover:brightness-110"
              >
                Direct naar de Scanner →
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Global Auth Modal for Login / Account Access */}
      <AuthModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        initialMode="login"
        onSuccess={() => {
          setShowLoginModal(false);
          router.push("/scan");
        }}
      />
    </main>
  );
}

function InviteLoadingFallback() {
  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-[calc(100vh-140px)] w-full max-w-xl flex-col items-center justify-center px-4 py-12 sm:px-6"
    >
      <div className="w-full rounded-[7px] border border-[#f3efdf]/30 bg-[#20251f] p-8 text-[#f3efdf] shadow-[7px_7px_0_#10150f]">
        <div className="flex items-center gap-3">
          <span className="pokeball brand-ball !h-8 !w-8 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#f1ca53]">
              DexLens Bèta
            </p>
            <h1 className="font-serif text-[24px] font-bold text-[#f3efdf]">
              Uitnodiging Laden…
            </h1>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={<InviteLoadingFallback />}>
      <InviteContent />
    </Suspense>
  );
}
