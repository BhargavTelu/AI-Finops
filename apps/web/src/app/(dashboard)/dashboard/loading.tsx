export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="flex items-start justify-between">
        <div className="space-y-1.5">
          <div className="h-5 w-28 animate-pulse rounded-md bg-muted" />
          <div className="h-3.5 w-56 animate-pulse rounded-md bg-muted" />
        </div>
        {/* Period selector skeleton */}
        <div className="h-8 w-28 animate-pulse rounded-lg bg-muted" />
      </div>

      {/* Four stat cards skeleton (1 → 2 → 4 columns) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border border-border/60 bg-card p-6">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <div className="h-3 w-20 animate-pulse rounded-md bg-muted" />
                <div className="h-8 w-28 animate-pulse rounded-md bg-muted" />
                <div className="h-5 w-24 animate-pulse rounded-full bg-muted" />
              </div>
              <div className="h-10 w-10 animate-pulse rounded-lg bg-muted" />
            </div>
            {/* Sparkline placeholder */}
            <div className="mt-4 h-8 animate-pulse rounded-md bg-muted" />
          </div>
        ))}
      </div>

      {/* Spend trend (2/3) + Provider donut (1/3) */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-border/60 bg-card p-6 lg:col-span-2">
          <div className="mb-4 space-y-1.5">
            <div className="h-4 w-24 animate-pulse rounded-md bg-muted" />
            <div className="h-3 w-40 animate-pulse rounded-md bg-muted" />
          </div>
          <div className="h-64 animate-pulse rounded-lg bg-muted" />
        </div>
        <div className="rounded-xl border border-border/60 bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="space-y-1.5">
              <div className="h-4 w-20 animate-pulse rounded-md bg-muted" />
              <div className="h-3 w-16 animate-pulse rounded-md bg-muted" />
            </div>
            <div className="h-4 w-16 animate-pulse rounded-md bg-muted" />
          </div>
          <div className="h-48 animate-pulse rounded-lg bg-muted" />
        </div>
      </div>

      {/* Top models (1/2) + Recent alerts (1/2) */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-border/60 bg-card p-6">
          <div className="mb-4 space-y-1.5">
            <div className="h-4 w-24 animate-pulse rounded-md bg-muted" />
            <div className="h-3 w-36 animate-pulse rounded-md bg-muted" />
          </div>
          <div className="h-44 animate-pulse rounded-lg bg-muted" />
        </div>
        <div className="rounded-xl border border-border/60 bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="space-y-1.5">
              <div className="h-4 w-28 animate-pulse rounded-md bg-muted" />
              <div className="h-3 w-44 animate-pulse rounded-md bg-muted" />
            </div>
            <div className="h-5 w-12 animate-pulse rounded-full bg-muted" />
          </div>
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
