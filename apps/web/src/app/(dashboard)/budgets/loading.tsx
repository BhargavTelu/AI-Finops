import { Skeleton } from "@/components/ui/skeleton";

export default function BudgetsLoading() {
  return (
    <div className="space-y-6">
      {/* PageHeader skeleton */}
      <div className="flex items-start justify-between">
        <div className="space-y-1.5">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-9 w-32 rounded-lg" />
      </div>

      {/* Budget card grid skeleton - 2 columns on sm+ */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex flex-col rounded-xl border bg-card">
            {/* Card body */}
            <div className="flex flex-col gap-4 p-6">
              {/* Header row */}
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1.5">
                  <Skeleton className="h-5 w-36" />
                  <Skeleton className="h-3.5 w-24" />
                </div>
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>

              {/* Spend number */}
              <div className="space-y-1.5">
                <Skeleton className="h-8 w-32" />
                <Skeleton className="h-4 w-44" />
              </div>

              {/* Progress bar */}
              <div className="space-y-1.5">
                <Skeleton className="h-2 w-full rounded-full" />
                <div className="flex justify-between">
                  <Skeleton className="h-3.5 w-28" />
                  <Skeleton className="h-3.5 w-8" />
                </div>
              </div>

              {/* Days left */}
              <Skeleton className="h-3.5 w-36" />
            </div>

            {/* Separator */}
            <div className="h-px w-full bg-border" />

            {/* Footer */}
            <div className="flex items-center justify-between px-4 py-3">
              <Skeleton className="h-8 w-16 rounded-md" />
              <Skeleton className="h-8 w-16 rounded-md" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
