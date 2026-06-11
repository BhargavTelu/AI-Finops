import { Skeleton } from "@/components/ui/skeleton";

export default function AnomaliesLoading() {
  return (
    <div className="space-y-6">
      {/* PageHeader skeleton */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1.5">
          <Skeleton className="h-6 w-44" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-9 w-36 shrink-0" />
      </div>

      {/* Filter row skeleton */}
      <div className="flex items-center gap-3">
        <div className="flex gap-1 rounded-lg bg-muted/60 p-1">
          <Skeleton className="h-8 w-14 rounded-md" />
          <Skeleton className="h-8 w-28 rounded-md" />
          <Skeleton className="h-8 w-24 rounded-md" />
        </div>
        <Skeleton className="h-9 w-36 rounded-md" />
      </div>

      {/* Alert card skeletons (4 cards) */}
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="overflow-hidden rounded-xl bg-card shadow-card">
            <div className="flex">
              {/* Left strip */}
              <div className="w-1 shrink-0 bg-muted" />
              {/* Content */}
              <div className="flex flex-1 flex-col gap-3 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-5 w-20 rounded-full" />
                    <Skeleton className="h-3 w-14" />
                  </div>
                  <div className="flex gap-1.5">
                    <Skeleton className="h-7 w-28 rounded-md" />
                    <Skeleton className="h-7 w-7 rounded-md" />
                  </div>
                </div>
                <Skeleton className="h-5 w-56" />
                <div className="space-y-1.5">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                </div>
                <Skeleton className="h-4 w-40" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
