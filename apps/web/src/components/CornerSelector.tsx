"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { CropCorners, Point } from "@/lib/api";

interface CornerSelectorProps {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  corners: CropCorners;
  onChange: (corners: CropCorners) => void;
  disabled?: boolean;
}

type CornerKey = "top_left" | "top_right" | "bottom_right" | "bottom_left";

const CORNER_LABELS: Record<CornerKey, { name: string; short: string }> = {
  top_left: { name: "Top-Left", short: "TL" },
  top_right: { name: "Top-Right", short: "TR" },
  bottom_right: { name: "Bottom-Right", short: "BR" },
  bottom_left: { name: "Bottom-Left", short: "BL" },
};

function clamp(val: number, min: number = 0.0, max: number = 1.0): number {
  return Math.max(min, Math.min(max, val));
}

function crossProduct(p1: Point, p2: Point, p3: Point): number {
  const v1x = p2.x - p1.x;
  const v1y = p2.y - p1.y;
  const v2x = p3.x - p2.x;
  const v2y = p3.y - p2.y;
  return v1x * v2y - v1y * v2x;
}

function segmentsIntersect(
  p1: Point,
  p2: Point,
  p3: Point,
  p4: Point
): boolean {
  const ccw = (a: Point, b: Point, c: Point) =>
    (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x);
  return (
    ccw(p1, p3, p4) !== ccw(p2, p3, p4) && ccw(p1, p2, p3) !== ccw(p1, p2, p4)
  );
}

function isValidQuad(c: CropCorners): boolean {
  const pts: Point[] = [c.top_left, c.top_right, c.bottom_right, c.bottom_left];

  for (let i = 0; i < 4; i++) {
    for (let j = i + 1; j < 4; j++) {
      const p1 = pts[i];
      const p2 = pts[j];
      if (p1 && p2) {
        const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
        if (dist < 0.01) return false;
      }
    }
  }

  if (
    segmentsIntersect(c.top_left, c.top_right, c.bottom_right, c.bottom_left) ||
    segmentsIntersect(c.top_right, c.bottom_right, c.bottom_left, c.top_left)
  ) {
    return false;
  }

  const cp1 = crossProduct(c.bottom_left, c.top_left, c.top_right);
  const cp2 = crossProduct(c.top_left, c.top_right, c.bottom_right);
  const cp3 = crossProduct(c.top_right, c.bottom_right, c.bottom_left);
  const cp4 = crossProduct(c.bottom_right, c.bottom_left, c.top_left);

  const allPositive = cp1 > 0 && cp2 > 0 && cp3 > 0 && cp4 > 0;
  const allNegative = cp1 < 0 && cp2 < 0 && cp3 < 0 && cp4 < 0;

  return allPositive || allNegative;
}

export function CornerSelector({
  imageUrl,
  imageWidth,
  imageHeight,
  corners,
  onChange,
  disabled = false,
}: CornerSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [activeCorner, setActiveCorner] = useState<CornerKey | null>(null);
  const [imgLoaded, setImgLoaded] = useState(false);

  useEffect(() => {
    if (imgRef.current && imgRef.current.complete) {
      setImgLoaded(true);
    }
  }, [imageUrl]);

  const validConvex = isValidQuad(corners);

  const getRelativeCoords = useCallback(
    (clientX: number, clientY: number): Point | null => {
      if (!containerRef.current) return null;
      const rect = containerRef.current.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return null;

      const x = clamp((clientX - rect.left) / rect.width);
      const y = clamp((clientY - rect.top) / rect.height);
      return { x, y };
    },
    []
  );

  const handlePointerDown = (corner: CornerKey, e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    setActiveCorner(corner);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!activeCorner || disabled) return;
      e.preventDefault();
      const coords = getRelativeCoords(e.clientX, e.clientY);
      if (!coords) return;

      const updated: CropCorners = {
        ...corners,
        [activeCorner]: coords,
      };
      onChange(updated);
    },
    [activeCorner, disabled, corners, getRelativeCoords, onChange]
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (activeCorner) {
        try {
          (e.target as HTMLElement).releasePointerCapture(e.pointerId);
        } catch {
          // Ignore
        }
        setActiveCorner(null);
      }
    },
    [activeCorner]
  );

  const handleKeyDown = (corner: CornerKey, e: React.KeyboardEvent) => {
    if (disabled) return;
    const step = e.shiftKey ? 0.02 : 0.005;
    let dx = 0;
    let dy = 0;

    switch (e.key) {
      case "ArrowUp":
        dy = -step;
        break;
      case "ArrowDown":
        dy = step;
        break;
      case "ArrowLeft":
        dx = -step;
        break;
      case "ArrowRight":
        dx = step;
        break;
      default:
        return;
    }

    e.preventDefault();
    const current = corners[corner];
    const updatedPoint: Point = {
      x: clamp(current.x + dx),
      y: clamp(current.y + dy),
    };

    onChange({
      ...corners,
      [corner]: updatedPoint,
    });
  };

  useEffect(() => {
    const handleGlobalPointerUp = () => {
      if (activeCorner) setActiveCorner(null);
    };
    window.addEventListener("pointerup", handleGlobalPointerUp);
    return () => {
      window.removeEventListener("pointerup", handleGlobalPointerUp);
    };
  }, [activeCorner]);

  const polygonPoints = `${corners.top_left.x * 1000},${corners.top_left.y * 1000} ${corners.top_right.x * 1000},${corners.top_right.y * 1000} ${corners.bottom_right.x * 1000},${corners.bottom_right.y * 1000} ${corners.bottom_left.x * 1000},${corners.bottom_left.y * 1000}`;

  return (
    <div className="flex flex-col items-center">
      {/* Interactive image container */}
      <div
        ref={containerRef}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        className={`relative max-h-[70vh] w-full max-w-lg touch-none select-none overflow-hidden rounded-2xl border border-slate-200/80 bg-slate-900 shadow-md dark:border-slate-800 ${
          disabled ? "opacity-60" : ""
        }`}
        style={{
          aspectRatio:
            imageWidth && imageHeight
              ? `${imageWidth} / ${imageHeight}`
              : "3 / 4",
        }}
      >
        {/* Source Image */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imgRef}
          src={imageUrl}
          alt="Scan to adjust corners"
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgLoaded(true)}
          className={`pointer-events-none h-full w-full select-none object-contain transition-opacity duration-200 ${
            imgLoaded ? "opacity-100" : "opacity-40 blur-sm"
          }`}
          draggable={false}
        />

        {/* SVG Polygon Overlay */}
        <svg
          viewBox="0 0 1000 1000"
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
        >
          <polygon
            points={polygonPoints}
            className={`transition-colors duration-150 ${
              validConvex
                ? "fill-sky-500/20 stroke-sky-400 stroke-[3]"
                : "stroke-dasharray-[8,4] fill-rose-500/25 stroke-rose-500 stroke-[3]"
            }`}
          />
        </svg>

        {/* Interactive Corner Handles */}
        {(
          [
            "top_left",
            "top_right",
            "bottom_right",
            "bottom_left",
          ] as CornerKey[]
        ).map((key) => {
          const pt = corners[key];
          const isActive = activeCorner === key;
          const info = CORNER_LABELS[key];

          return (
            <div
              key={key}
              role="slider"
              tabIndex={disabled ? -1 : 0}
              aria-label={`${info.name} (${Math.round(pt.x * 100)}%, ${Math.round(pt.y * 100)}%)`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(pt.x * 100)}
              onPointerDown={(e) => handlePointerDown(key, e)}
              onKeyDown={(keyEvent) => handleKeyDown(key, keyEvent)}
              style={{
                left: `${pt.x * 100}%`,
                top: `${pt.y * 100}%`,
              }}
              className={`absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center ${
                disabled
                  ? "cursor-default"
                  : "cursor-grab active:cursor-grabbing"
              } focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-400`}
            >
              <div className="flex h-11 w-11 items-center justify-center">
                <div
                  className={`flex h-7 w-7 items-center justify-center rounded-full border-2 font-mono text-[10px] font-bold shadow-lg transition-transform ${
                    validConvex
                      ? "border-white bg-sky-500 text-white shadow-sky-500/50"
                      : "border-rose-400 bg-rose-600 text-white shadow-rose-500/50"
                  } ${isActive ? "scale-125 ring-4 ring-sky-300/60" : "hover:scale-110"}`}
                >
                  {info.short}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Convexity / Geometry Warning if invalid */}
      {!validConvex && (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-950/40 px-3.5 py-2 text-xs font-medium text-rose-300">
          <svg
            className="h-4 w-4 shrink-0 text-rose-400"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
            />
          </svg>
          <span>
            Corners must form a valid four-sided polygon without intersecting
            lines.
          </span>
        </div>
      )}

      {/* Accessibility instruction */}
      <p className="mt-3 text-center text-xs text-slate-500 dark:text-zinc-400">
        Drag the 4 corner handles to align framing. Arrow keys nudge selected
        corner.
      </p>
    </div>
  );
}
