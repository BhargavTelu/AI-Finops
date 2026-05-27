import { cn } from "@/lib/utils"

interface PageHeaderProps {
  title: string
  description?: string
  /** Right-aligned slot — pass Button(s) or filter controls */
  actions?: React.ReactNode
  className?: string
}

/**
 * Consistent page-level header used on every route.
 * Title + optional description on the left; action buttons/controls on the right.
 *
 * Usage:
 *   <PageHeader
 *     title="Dashboard"
 *     description="LLM spend overview for your organisation"
 *     actions={<Button>Export</Button>}
 *   />
 */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        className
      )}
    >
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>

      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  )
}
