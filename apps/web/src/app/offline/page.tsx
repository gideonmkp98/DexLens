import Link from "next/link";

export default function OfflinePage() {
  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-[70vh] max-w-xl flex-col items-center justify-center px-4 py-16 text-center"
    >
      <div className="card-slab max-w-md p-8">
        <span className="pokeball mx-auto mb-6" aria-hidden="true" />
        <span className="ink-badge red mb-3 inline-block">Geen Verbinding</span>
        <h1 className="font-serif text-2xl font-bold tracking-tight text-[#252923] dark:text-[#f3efdf]">
          DexLens is offline
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
          DexLens vereist een actieve internetverbinding voor optische
          tekenherkenning (OCR) en cataloguszoekopdrachten via TCGdex.
        </p>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-500">
          Zodra je netwerk hersteld is, kun je direct weer doorgaan met scannen.
        </p>
        <div className="mt-6 flex flex-col gap-2.5 sm:flex-row sm:justify-center">
          <Link href="/scan" className="ink-button red">
            Opnieuw Proberen
          </Link>
          <Link href="/" className="ink-button secondary">
            Naar Startpagina
          </Link>
        </div>
      </div>
    </main>
  );
}
