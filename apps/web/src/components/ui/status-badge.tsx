import { cn } from "@/lib/utils"
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  MinusCircle,
  Info,
} from "lucide-react"

export type StatusType =
  | "active"
  | "inactive"
  | "error"
  | "syncing"
  | "warning"
  | "critical"
  | "info"

interface StatusBadgeProps {
  status: StatusType
  label?: string
  className?: string
}

const STATUS_CONFIG: Record<
  StatusType,
  { icon: React.ElementType; classes: string; defaultLabel: string }
> = {
  active: {
    icon: CheckCircle2,
    // green: success-subtle bg, success text
    classes: "bg-success-subtle text-success border-success/20",
    defaultLabel: "Active",
  },
  inactive: {
    icon: MinusCircle,
    // gray: muted bg, muted-foreground text
    classes: "bg-muted text-muted-foreground border-border",
    defaultLabel: "Inactive",
  },
  error: {
    icon: XCircle,
    // red: critical-subtle bg, critical text
    classes: "bg-critical-subtle text-critical border-critical/20",
    defaultLabel: "Error",
  },
  syncing: {
    icon: Loader2,
    // blue: info-subtle bg, info text
    classes: "bg-info-subtle text-info border-info/20",
    defaultLabel: "Syncing",
  },
  warning: {
    icon: AlertTriangle,
    // amber: warning-subtle bg, warning text
    classes: "bg-warning-subtle text-warning border-warning/20",
    defaultLabel: "Warning",
  },
  critical: {
    icon: XCircle,
    // red: same as error but distinct semantic meaning (alert severity)
    classes: "bg-critical-subtle text-critical border-critical/20",
    defaultLabel: "Critical",
  },
  info: {
    icon: Info,
    // blue: info-subtle bg, info text
    classes: "bg-info-subtle text-info border-info/20",
    defaultLabel: "Info",
  },
}

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  const displayLabel = label ?? config.defaultLabel

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        config.classes,
        className
      )}
    >
      <Icon
        className={cn(
          "h-3 w-3 shrink-0",
          // Spinner animation only for syncing state
          status === "syncing" && "animate-spin"
        )}
        aria-hidden
      />
      {displayLabel}
    </span>
  )
}
