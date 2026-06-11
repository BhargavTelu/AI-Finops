import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"

interface DataTableSkeletonProps {
  /** Number of data rows to render (excluding the header row) */
  rows?: number
  /** Number of columns */
  columns?: number
  className?: string
}

/**
 * Table-shaped loading skeleton - used on every data-table page while fetching.
 * Matches the visual shape of the table so the layout doesn't shift on load.
 *
 * Usage:
 *   if (isLoading) return <DataTableSkeleton rows={5} columns={6} />
 */
export function DataTableSkeleton({
  rows = 5,
  columns = 4,
  className,
}: DataTableSkeletonProps) {
  return (
    <div className={cn("w-full overflow-hidden rounded-xl bg-card shadow-card", className)}>
      {/* Header row */}
      <div className="flex items-center gap-4 border-b bg-muted/50 px-4 py-3">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton
            key={i}
            // Last column is narrower (typically a status or action column)
            className={cn("h-4", i === columns - 1 ? "w-16" : "flex-1")}
          />
        ))}
      </div>

      {/* Data rows */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={rowIndex}
          className="flex items-center gap-4 border-b px-4 py-3.5 last:border-0"
        >
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton
              key={colIndex}
              className={cn(
                "h-4",
                colIndex === 0
                  ? "w-36" // first column - dimension name, wider
                  : colIndex === columns - 1
                    ? "w-16" // last column - action / status, narrower
                    : "flex-1"
              )}
            />
          ))}
        </div>
      ))}
    </div>
  )
}
