import { Skeleton } from "@/components/ui/skeleton";

// Loading skeleton for the Slack settings page — matches the slack-client.tsx card layout.
export default function SlackLoading() {
  return (
    <div className="space-y-8">
      {/* Section header */}
      <div className="space-y-1.5">
        <Skeleton className="h-5 w-10" />
        <Skeleton className="h-4 w-80" />
      </div>

      {/* Connection status card */}
      <div className="rounded-xl border bg-card shadow-card">
        {/* Card header: channel + badge + actions */}
        <div className="flex items-center justify-between gap-4 p-6">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg" />
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-5 w-14 rounded-full" />
              </div>
              <Skeleton className="h-3.5 w-36" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-24 rounded-lg" />
            <Skeleton className="h-8 w-24 rounded-lg" />
          </div>
        </div>

        {/* Separator */}
        <div className="h-px bg-border/60" />

        {/* Mute toggle row */}
        <div className="flex items-center justify-between gap-6 px-6 py-5">
          <div className="space-y-1.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3.5 w-64" />
          </div>
          <Skeleton className="h-6 w-11 rounded-full" />
        </div>
      </div>

      {/* Feature list */}
      <div className="space-y-3">
        <Skeleton className="h-4 w-28" />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="flex gap-3 rounded-lg border border-border/60 bg-card px-4 py-3"
            >
              <Skeleton className="mt-0.5 h-4 w-4 shrink-0 rounded-full" />
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-72" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
