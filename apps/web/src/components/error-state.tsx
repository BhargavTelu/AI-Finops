import { AlertTriangle } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface ErrorStateProps {
  title?: string
  description?: string
  /** If provided, a retry button is shown */
  onRetry?: () => void
  className?: string
}

/**
 * Standard error state - shown when a data fetch fails.
 * Always provides a retry path so the user isn't stuck.
 *
 * Usage:
 *   <ErrorState
 *     description="Failed to load cost data."
 *     onRetry={() => refetch()}
 *   />
 */
export function ErrorState({
  title = "Something went wrong",
  description = "There was a problem loading this data.",
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 py-16 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-critical-subtle">
        <AlertTriangle
          className="h-6 w-6 text-critical"
          strokeWidth={1.5}
          aria-hidden
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="max-w-xs text-sm text-muted-foreground">{description}</p>
      </div>

      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
