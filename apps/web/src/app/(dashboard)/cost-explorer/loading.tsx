export default function CostExplorerLoading() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="flex items-start justify-between">
        <div className="space-y-1.5">
          <div className="h-5 w-36 animate-pulse rounded-md bg-muted" />
          <div className="h-3.5 w-52 animate-pulse rounded-md bg-muted" />
        </div>
        {/* Export button skeleton */}
        <div className="h-8 w-28 animate-pulse rounded-lg bg-muted" />
      </div>

      {/* Filter bar skeleton */}
      <div className="flex flex-wrap gap-2">
        {[80, 96, 72].map((w, i) => (
          <div
            key={i}
            className="h-8 animate-pulse rounded-lg bg-muted"
            style={{ width: `${w}px` }}
          />
        ))}
      </div>

      {/* Table skeleton */}
      <div className="rounded-xl border border-border/60 bg-card">
        {/* Table header — 6 columns: Dimension, Cost, Requests, Tokens, Avg/1K, % Total */}
        <div className="flex gap-4 border-b border-border/60 px-4 py-3">
          {[200, 96, 80, 96, 88, 80].map((w, i) => (
            <div key={i} className="h-3.5 animate-pulse rounded-md bg-muted" style={{ width: `${w}px` }} />
          ))}
        </div>
        {/* Rows */}
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-4 border-b border-border/40 px-4 py-3.5 last:border-0"
          >
            <div className="h-3.5 w-48 animate-pulse rounded-md bg-muted" />
            <div className="h-3.5 w-24 animate-pulse rounded-md bg-muted" />
            <div className="h-3.5 w-20 animate-pulse rounded-md bg-muted" />
            <div className="h-3.5 w-24 animate-pulse rounded-md bg-muted" />
            <div className="h-3.5 w-22 animate-pulse rounded-md bg-muted" />
            <div className="h-2.5 w-20 animate-pulse rounded-full bg-muted" />
          </div>
        ))}
      </div>
    </div>
  );
}
