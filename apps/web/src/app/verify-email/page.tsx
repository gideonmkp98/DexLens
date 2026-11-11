"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type VerificationState = "loading" | "success" | "error";

export default function VerifyEmailPage() {
  const [state, setState] = useState<VerificationState>("loading");
  const [message, setMessage] = useState("Je e-mailadres wordt bevestigd…");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setState("error");
      setMessage("Deze verificatielink mist een geldige token.");
      return;
    }

    const controller = new AbortController();
    void fetch(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(
            body?.detail?.message ||
              "De verificatielink is ongeldig of verlopen."
          );
        }
        setState("success");
        setMessage(body.message || "Je e-mailadres is bevestigd.");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState("error");
        setMessage(
          error instanceof Error
            ? error.message
            : "E-mailverificatie is mislukt."
        );
      });

    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-xl items-center px-5 py-16">
      <section className="border-border bg-surface shadow-card w-full rounded-3xl border p-8 text-center sm:p-12">
        <div
          className={`mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full text-2xl ${
            state === "success"
              ? "bg-emerald-500/15 text-emerald-400"
              : state === "error"
                ? "bg-red-500/15 text-red-400"
                : "bg-accent/15 text-accent"
          }`}
          aria-hidden="true"
        >
          {state === "loading" ? "…" : state === "success" ? "✓" : "!"}
        </div>
        <p className="text-muted mb-2 font-mono text-xs uppercase tracking-[0.18em]">
          Accountbeveiliging
        </p>
        <h1 className="text-foreground mb-4 text-3xl font-black">
          {state === "loading"
            ? "Even controleren"
            : state === "success"
              ? "E-mail bevestigd"
              : "Link niet geldig"}
        </h1>
        <p role={state === "error" ? "alert" : "status"} className="text-muted">
          {message}
        </p>
        {state !== "loading" && (
          <Link
            href="/"
            className="bg-accent mt-8 inline-flex min-h-11 items-center justify-center rounded-xl px-6 font-bold text-white transition hover:brightness-110"
          >
            Terug naar DexLens
          </Link>
        )}
      </section>
    </main>
  );
}
