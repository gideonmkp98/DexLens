export function CardSkeleton() {
  return (
    <div className="flex flex-col rounded-xl border border-slate-200/90 bg-white p-2 shadow-sm dark:border-white/10 dark:bg-zinc-900/90 sm:p-2.5">
      <div className="relative aspect-card w-full animate-pulse rounded-lg bg-slate-200 dark:bg-zinc-800" />
      <div className="mt-2.5 space-y-2 px-1">
        <div className="h-3.5 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-zinc-800" />
        <div className="flex items-center justify-between border-t border-slate-100 pt-1.5 dark:border-white/5">
          <div className="h-2.5 w-16 animate-pulse rounded bg-slate-200 dark:bg-zinc-800" />
          <div className="h-2.5 w-8 animate-pulse rounded bg-slate-200 dark:bg-zinc-800" />
        </div>
      </div>
    </div>
  );
}

export function CardGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-3.5 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function SetSkeleton() {
  return (
    <div className="flex flex-col rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-zinc-900/90">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 animate-pulse rounded-lg bg-slate-200 dark:bg-zinc-800" />
        <div className="flex-1 space-y-1.5">
          <div className="h-4 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-zinc-800" />
          <div className="h-2.5 w-1/3 animate-pulse rounded bg-slate-200/70 dark:bg-zinc-800/60" />
        </div>
      </div>
    </div>
  );
}

export function SetGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <SetSkeleton key={i} />
      ))}
    </div>
  );
}
