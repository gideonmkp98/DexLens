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
  const [hasError, setHasError] = useState(false);

  if (!src || hasError) {
    return (
      <div
        className={`flex aspect-[2.5/3.5] w-full flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-100 p-3 text-center text-slate-400 ${className}`}
      >
        <span className="mb-1 text-2xl">🃏</span>
        <span className="line-clamp-2 text-xs font-medium text-slate-500">
          {alt}
        </span>
        <span className="mt-1 text-[10px] text-slate-400">
          No image preview
        </span>
      </div>
    );
  }

  return (
    <div
      className={`relative aspect-[2.5/3.5] w-full overflow-hidden rounded-lg bg-slate-100 shadow-sm ${className}`}
    >
      <Image
        src={src}
        alt={alt}
        fill
        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 25vw, 20vw"
        priority={priority}
        loading={priority ? undefined : "lazy"}
        className="object-contain transition duration-200 hover:scale-105"
        onError={() => setHasError(true)}
      />
    </div>
  );
}
