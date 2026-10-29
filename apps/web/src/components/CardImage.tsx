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
      <div className={`card-image card-image-missing ${className}`}>
        <div className="missing-image-icon">
          <svg
            className="h-5 w-5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <rect width="14" height="18" x="5" y="3" rx="2" />
            <path d="m9 10 2 2 4-4" />
          </svg>
        </div>
        <span className="missing-image-name">{alt}</span>
        <span className="missing-image-label">Geen afbeelding</span>
      </div>
    );
  }

  if (useFallbackImg) {
    return (
      <div className={`card-image ${className}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          className="card-image-content"
          onError={() => setHasTotalError(true)}
          loading={priority ? "eager" : "lazy"}
        />
      </div>
    );
  }

  return (
    <div className={`card-image ${className}`}>
      <Image
        src={src}
        alt={alt}
        fill
        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
        priority={priority}
        loading={priority ? undefined : "lazy"}
        className="card-image-content object-contain"
        onError={() => setUseFallbackImg(true)}
      />
    </div>
  );
}
