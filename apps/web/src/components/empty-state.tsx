import { type LucideIcon } from "lucide-react"
import Link from "next/link"
import type { Route } from "next"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface EmptyStateAction {
  label: string
  /** Provide href for link navigation or onClick for in-page actions */
  href?: string
  onClick?: () => void
}

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: EmptyStateAction
  className?: string
}

/**
 * Standard empty state — shown on every page when data arrays are empty.
 * Never leave a page blank. Always provide a path forward via the action CTA.
 *
 * Usage:
 *   <EmptyState
 *     icon={KeyRound}
 *     title="No API keys connected"
 *     description="Connect your first provider key to start tracking spend."
 *     action={{ label: "Add integration", href: "/settings/integrations" }}
 *   />
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 py-16 text-center",
        className
      )}
    >
      {Icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
          <Icon className="h-6 w-6 text-muted-foreground" strokeWidth={1.5} />
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {description && (
          <p className="max-w-xs text-sm text-muted-foreground">{description}</p>
        )}
      </div>

      {action && (
        action.href ? (
          <Button asChild size="sm">
            <Link href={action.href as Route<string>}>{action.label}</Link>
          </Button>
        ) : (
          <Button size="sm" onClick={action.onClick}>
            {action.label}
          </Button>
        )
      )}
    </div>
  )
}
