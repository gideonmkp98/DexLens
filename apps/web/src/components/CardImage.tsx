"use client";

import { useState } from "react";
import Image from "next/image";

interface CardImageProps {
  src: string | null;
  alt: string;
  className?: string;
  priority?: boolean;
}

export default function CardImage({
  src,
  alt,
  className = "",
  priority = false,
}: CardImageProps) {
  const [useFallbackImg, setUseFallbackImg] = useState(false);
  const [hasTotalError, setHasTotalError] = useState(false);

  if (!src || hasTotalError) {
    return (
      <div
        className={`relative flex aspect-card w-full flex-col items-center justify-center overflow-hidden rounded-xl border border-slate-200/80 bg-gradient-to-br from-slate-100 to-slate-200/50 p-3 text-center text-slate-400 dark:border-white/10 dark:from-slate-900/60 dark:to-slate-950 ${className}`}
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200/80 bg-white/80 shadow-sm backdrop-blur-sm dark:border-white/10 dark:bg-slate-800/80">
          <svg
            className="h-5 w-5 text-amber-500/80"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <rect width="14" height="18" x="5" y="3" rx="2" />
            <path d="m9 10 2 2 4-4" />
          </svg>
        </div>
        <span className="mt-2 line-clamp-1 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
          {alt}
        </span>
        <span className="mt-0.5 rounded-full bg-slate-200/70 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-slate-500 dark:bg-white/10 dark:text-slate-400">
          Geen afbeelding
        </span>
      </div>
    );
  }

  if (useFallbackImg) {
    return (
      <div
        className={`relative aspect-card w-full overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-950 ${className}`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          className="h-full w-full object-contain transition-transform duration-200 ease-out group-hover:scale-[1.03]"
          onError={() => setHasTotalError(true)}
          loading={priority ? "eager" : "lazy"}
        />
      </div>
    );
  }

  return (
    <div
      className={`relative aspect-card w-full overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-950 ${className}`}
    >
      <Image
        src={src}
        alt={alt}
        fill
        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
        priority={priority}
        loading={priority ? undefined : "lazy"}
        className="object-contain transition-transform duration-200 ease-out group-hover:scale-[1.03]"
        onError={() => setUseFallbackImg(true)}
      />
    </div>
  );
}

