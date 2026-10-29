export function CardSkeleton() {
  return (
    <div className="card-skeleton">
      <div className="skeleton-card-art" />
      <div className="skeleton-copy">
        <div className="skeleton-line wide" />
        <div className="skeleton-meta">
          <div className="skeleton-line medium" />
          <div className="skeleton-line short" />
        </div>
      </div>
    </div>
  );
}

export function CardGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="card-grid">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

export function SetSkeleton() {
  return (
    <div className="set-skeleton">
      <div className="set-skeleton-row">
        <div className="skeleton-symbol" />
        <div className="skeleton-copy">
          <div className="skeleton-line wide" />
          <div className="skeleton-line short" />
        </div>
      </div>
    </div>
  );
}

export function SetGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="set-grid">
      {Array.from({ length: count }).map((_, i) => (
        <SetSkeleton key={i} />
      ))}
    </div>
  );
}
