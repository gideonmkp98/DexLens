export default function ViewfinderGuide() {
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
      <div className="relative aspect-card w-full max-w-[280px] rounded-2xl border border-sky-400/40 shadow-[0_0_0_9999px_rgba(7,11,21,0.7)] sm:max-w-[310px]">
        {/* Precision Optical Corner Brackets with cyan glow */}
        <div className="border-l-3 border-t-3 absolute -left-1 -top-1 h-6 w-6 rounded-tl-lg border-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]" />
        <div className="border-r-3 border-t-3 absolute -right-1 -top-1 h-6 w-6 rounded-tr-lg border-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]" />
        <div className="border-b-3 border-l-3 absolute -bottom-1 -left-1 h-6 w-6 rounded-bl-lg border-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]" />
        <div className="border-b-3 border-r-3 absolute -bottom-1 -right-1 h-6 w-6 rounded-br-lg border-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]" />

        {/* Center Target Indicator */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="h-3 w-3 rounded-full border border-sky-400/60 bg-sky-400/20" />
        </div>

        {/* Friendly Collector Guide Label */}
        <div className="absolute inset-x-0 bottom-5 text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-slate-950/85 px-3 py-1 text-[11px] font-bold text-sky-300 shadow-md backdrop-blur-md">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />
            Houd kaart binnen het kader
          </span>
        </div>
      </div>
    </div>
  );
}
