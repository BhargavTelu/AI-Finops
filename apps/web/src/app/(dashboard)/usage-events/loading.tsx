import { Skeleton } from "@/components/ui/skeleton";

export default function UsageEventsLoading() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-6 w-36" />
        <Skeleton className="mt-1.5 h-4 w-80" />
      </div>

      {/* Table skeleton — matches the UsageEventsClient table layout */}
      <div className="overflow-hidden rounded-xl border">
        <div className="border-b bg-muted/40 px-4 py-3">
          <div className="grid grid-cols-8 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-4" />
            ))}
          </div>
        </div>
        <div className="divide-y">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="px-4 py-3">
              <div className="grid grid-cols-8 gap-4">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-5 w-14 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
