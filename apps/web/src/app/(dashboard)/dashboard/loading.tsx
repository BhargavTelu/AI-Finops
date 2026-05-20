export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="space-y-1.5">
        <div className="h-5 w-28 animate-pulse rounded-md bg-muted" />
        <div className="h-3.5 w-44 animate-pulse rounded-md bg-muted" />
      </div>

      {/* Stat cards skeleton */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-xl border border-border/60 bg-card p-5">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <div className="h-3 w-20 animate-pulse rounded-md bg-muted" />
                <div className="h-7 w-32 animate-pulse rounded-md bg-muted" />
                <div className="h-3 w-24 animate-pulse rounded-md bg-muted" />
              </div>
              <div className="h-9 w-9 animate-pulse rounded-lg bg-muted" />
            </div>
          </div>
        ))}
      </div>

      {/* Chart skeletons */}
      <div className="space-y-4">
        {[280, 220].map((h, i) => (
          <div key={i} className="rounded-xl border border-border/60 bg-card p-5">
            <div className="mb-4 space-y-1">
              <div className="h-4 w-24 animate-pulse rounded-md bg-muted" />
              <div className="h-3 w-48 animate-pulse rounded-md bg-muted" />
            </div>
            <div
              className="animate-pulse rounded-lg bg-muted"
              style={{ height: `${h}px` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
