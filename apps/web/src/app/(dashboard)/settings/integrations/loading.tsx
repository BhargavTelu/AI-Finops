export default function IntegrationsLoading() {
  return (
    <div className="space-y-6">
      <div className="h-5 w-32 animate-pulse rounded-md bg-muted" />

      {/* Form card skeleton */}
      <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4">
        <div className="h-4 w-40 animate-pulse rounded-md bg-muted" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-9 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
        <div className="h-9 w-36 animate-pulse rounded-lg bg-muted" />
      </div>

      {/* Table skeleton */}
      <div className="rounded-xl border border-border/60 bg-card">
        <div className="flex gap-4 border-b border-border/60 px-4 py-3">
          {[120, 100, 80, 100, 60].map((w, i) => (
            <div key={i} className="h-3.5 animate-pulse rounded-md bg-muted" style={{ width: `${w}px` }} />
          ))}
        </div>
        {[1, 2].map((i) => (
          <div key={i} className="flex items-center gap-4 border-b border-border/40 px-4 py-3.5 last:border-0">
            <div className="h-3.5 w-28 animate-pulse rounded-md bg-muted" />
            <div className="h-3.5 w-24 animate-pulse rounded-md bg-muted" />
            <div className="h-5 w-16 animate-pulse rounded-full bg-muted" />
            <div className="h-3.5 w-24 animate-pulse rounded-md bg-muted" />
            <div className="h-7 w-16 animate-pulse rounded-lg bg-muted" />
          </div>
        ))}
      </div>
    </div>
  );
}
