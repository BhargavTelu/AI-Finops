import { Skeleton } from "@/components/ui/skeleton";

// Loading skeleton for the tags settings page — matches the Tags + Tag Rules table layout.
export default function TagsLoading() {
  return (
    <div className="space-y-10">
      {/* ── Tags section ── */}
      <section className="space-y-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-12" />
            <Skeleton className="h-4 w-64" />
          </div>
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>

        {/* Tags table skeleton */}
        <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
          {/* Table header */}
          <div className="flex items-center gap-4 border-b border-border/60 bg-muted/40 px-4 py-3">
            <Skeleton className="h-3 w-14" />
            <Skeleton className="h-3 w-10 ml-8" />
            <Skeleton className="h-3 w-12 ml-8" />
          </div>
          {/* Table rows */}
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="flex items-center gap-4 border-b border-border/40 last:border-0 px-4 py-3"
            >
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-5 w-16 rounded-full ml-6" />
              <Skeleton className="h-4 w-4 rounded-full ml-6" />
            </div>
          ))}
        </div>
      </section>

      {/* Separator */}
      <div className="h-px bg-border" />

      {/* ── Tag Rules section ── */}
      <section className="space-y-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-4 w-80" />
          </div>
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>

        {/* Rules table skeleton */}
        <div className="rounded-xl border border-border/60 bg-card overflow-hidden">
          {/* Table header */}
          <div className="flex items-center gap-6 border-b border-border/60 bg-muted/40 px-4 py-3">
            <Skeleton className="h-3 w-14" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-14" />
            <Skeleton className="h-3 w-20" />
          </div>
          {/* Table rows */}
          {[1, 2].map((i) => (
            <div
              key={i}
              className="flex items-center gap-6 border-b border-border/40 last:border-0 px-4 py-3"
            >
              <Skeleton className="h-4 w-8 text-mono" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-5 w-28 rounded font-mono" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
