export default function SlackLoading() {
  return (
    <div className="space-y-8">
      <div>
        <div className="h-7 w-12 animate-pulse rounded-md bg-muted" />
        <div className="mt-1.5 h-4 w-80 animate-pulse rounded-md bg-muted" />
      </div>
      <div className="rounded-lg border bg-card p-6 space-y-4">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 animate-pulse rounded-full bg-muted" />
          <div className="h-4 w-20 animate-pulse rounded-md bg-muted" />
        </div>
        <div className="space-y-2">
          <div className="h-3.5 w-48 animate-pulse rounded-md bg-muted" />
          <div className="h-3.5 w-36 animate-pulse rounded-md bg-muted" />
        </div>
        <div className="flex gap-3">
          <div className="h-9 w-48 animate-pulse rounded-md bg-muted" />
          <div className="h-9 w-24 animate-pulse rounded-md bg-muted" />
        </div>
      </div>
    </div>
  );
}
