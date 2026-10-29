"use client";

import Link from "next/link";
import React from "react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  actionHref?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export default function EmptyState({
  icon,
  title,
  description,
  actionHref,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        {icon || (
          <svg
            className="h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" strokeLinecap="round" />
          </svg>
        )}
      </div>

      <h3>{title}</h3>
      <p>{description}</p>

      {actionLabel && (actionHref || onAction) && (
        <div className="empty-state-action">
          {actionHref ? (
            <Link href={actionHref} className="ink-button red small">
              {actionLabel}
            </Link>
          ) : (
            <button
              type="button"
              onClick={onAction}
              className="ink-button red small"
            >
              {actionLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
