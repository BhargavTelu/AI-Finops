"use client";

import { useState, useTransition, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  Bell,
  Check,
  CheckCircle2,
  X,
  ArrowRight,
} from "lucide-react";
import { useAuth } from "@clerk/nextjs";

import { createApiClient } from "@/lib/api-client";
import type { AnomalyRead, AnomalyStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/ui/status-badge";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCost(raw: string): string {
  const n = parseFloat(raw);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function absoluteTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function generateTitle(anomaly: AnomalyRead): string {
  const labels: Record<string, string> = {
    model: "Model",
    feature: "Feature",
    team: "Team",
    customer: "Customer",
    provider: "Provider",
  };
  const label = labels[anomaly.scope_kind] ?? "Cost";
  const value = anomaly.scope_value ?? anomaly.scope_kind;
  return `${label} cost spike — ${value}`;
}

function generateDescription(anomaly: AnomalyRead): string {
  return `Spend jumped +${anomaly.spike_pct}% vs 7-day average — ${fmtCost(anomaly.baseline_usd)}/day baseline → ${fmtCost(anomaly.actual_usd)} actual`;
}

function buildContextTags(context: Record<string, unknown> | null): string | null {
  if (!context) return null;
  const parts: string[] = [];
  const keys = ["feature_tag", "team_tag", "customer_tag"] as const;
  for (const k of keys) {
    const v = context[k];
    if (v && typeof v === "string") parts.push(v);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

// ── Severity mapping ──────────────────────────────────────────────────────────

const SEVERITY_STRIP: Record<string, string> = {
  low: "bg-warning",
  medium: "bg-warning",
  high: "bg-critical",
};

const SEVERITY_BADGE_STATUS = {
  low: "warning",
  medium: "warning",
  high: "critical",
} as const;

const SEVERITY_BADGE_LABEL: Record<string, string> = {
  low: "Low",
  medium: "Warning",
  high: "Critical",
};

// ── Status tabs ───────────────────────────────────────────────────────────────

const STATUS_TABS: { label: string; value: AnomalyStatus }[] = [
  { label: "Open", value: "open" },
  { label: "Acknowledged", value: "acked" },
  { label: "Dismissed", value: "dismissed" },
];

function StatusTabs({ current }: { current: AnomalyStatus }) {
  const router = useRouter();
  return (
    <div className="flex gap-1 rounded-lg bg-muted/60 p-1 w-fit">
      {STATUS_TABS.map((tab) => (
        <button
          key={tab.value}
          onClick={() => router.push(`/anomalies?status=${tab.value}`)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-150",
            current === tab.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ── Alert card ────────────────────────────────────────────────────────────────

interface AlertCardProps {
  anomaly: AnomalyRead;
  showActions: boolean;
  isLoading: boolean;
  onAcknowledge: (id: string) => void;
  onDismiss: (id: string) => void;
}

function AlertCard({
  anomaly,
  showActions,
  isLoading,
  onAcknowledge,
  onDismiss,
}: AlertCardProps) {
  const contextTags = buildContextTags(anomaly.context);
  const title = generateTitle(anomaly);
  const description = anomaly.explanation ?? generateDescription(anomaly);
  const stripClass = SEVERITY_STRIP[anomaly.severity] ?? "bg-muted-foreground/40";
  const badgeStatus = SEVERITY_BADGE_STATUS[anomaly.severity as keyof typeof SEVERITY_BADGE_STATUS] ?? "warning";
  const badgeLabel = SEVERITY_BADGE_LABEL[anomaly.severity] ?? anomaly.severity;
  const isAcknowledged = anomaly.status === "acked";

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border bg-card shadow-card transition-shadow hover:shadow-card-hover",
        isAcknowledged && "opacity-60"
      )}
    >
      <div className="flex">
        {/* Left severity strip — 4px, amber for low/medium, red for high */}
        <div className={cn("w-1 shrink-0", stripClass)} aria-hidden />

        {/* Card content */}
        <div className="flex flex-1 flex-col gap-3 p-5">
          {/* Header: badge + timestamp + action buttons */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={badgeStatus} label={badgeLabel} />
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-default text-xs text-muted-foreground">
                      {relativeTime(anomaly.detected_at)}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p className="text-xs">{absoluteTime(anomaly.detected_at)}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>

            {showActions && (
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  disabled={isLoading}
                  onClick={() => onAcknowledge(anomaly.id)}
                >
                  <Check className="h-3.5 w-3.5" />
                  Acknowledge
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                  disabled={isLoading}
                  onClick={() => onDismiss(anomaly.id)}
                  aria-label="Dismiss alert"
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}

            {isAcknowledged && (
              <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                <Check className="h-3.5 w-3.5 text-success" />
                Acknowledged
              </span>
            )}
          </div>

          {/* Title + context tags */}
          <div>
            <p className="font-semibold leading-snug">{title}</p>
            {contextTags && (
              <p className="mt-0.5 text-xs text-muted-foreground">{contextTags}</p>
            )}
          </div>

          {/* Description */}
          <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>

          {/* Footer link */}
          <Link
            href="/cost-explorer"
            className="inline-flex w-fit items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            View in Cost Explorer
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  initialAnomalies: AnomalyRead[];
  status: AnomalyStatus;
}

export function AnomaliesClient({ initialAnomalies, status }: Props) {
  const { getToken } = useAuth();
  const [anomalies, setAnomalies] = useState(initialAnomalies);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [isAckingAll, setIsAckingAll] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  async function handleStatusUpdate(id: string, newStatus: "acked" | "dismissed") {
    setError(null);
    setLoadingId(id);
    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        await api.patch(`/anomalies/${id}`, { status: newStatus });
        // Remove from current tab — it now belongs in a different tab
        setAnomalies((prev) => prev.filter((a) => a.id !== id));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Update failed");
      } finally {
        setLoadingId(null);
      }
    });
  }

  async function handleAcknowledgeAll() {
    if (anomalies.length === 0) return;
    setError(null);
    setIsAckingAll(true);
    try {
      const token = await getToken();
      const api = createApiClient(token!);
      await Promise.all(
        anomalies.map((a) => api.patch(`/anomalies/${a.id}`, { status: "acked" }))
      );
      setAnomalies([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to acknowledge all alerts");
    } finally {
      setIsAckingAll(false);
    }
  }

  const filteredAnomalies = useMemo(() => {
    if (severityFilter === "all") return anomalies;
    return anomalies.filter((a) => a.severity === severityFilter);
  }, [anomalies, severityFilter]);

  // Count critical (high) open alerts for the summary banner
  const criticalCount = useMemo(
    () => anomalies.filter((a) => a.severity === "high").length,
    [anomalies]
  );

  const isAnyLoading = isPending || isAckingAll;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts & Anomalies"
        description="Cost spikes detected by nightly statistical analysis (rolling 7-day mean + 2σ)"
        actions={
          status === "open" && anomalies.length > 0 ? (
            <Button
              size="sm"
              variant="outline"
              disabled={isAnyLoading}
              onClick={handleAcknowledgeAll}
              className="gap-1.5"
            >
              <Check className="h-3.5 w-3.5" />
              Acknowledge all
            </Button>
          ) : undefined
        }
      />

      {/* Critical summary banner — only for open, unacknowledged critical alerts */}
      {criticalCount > 0 && status === "open" && (
        <div className="flex items-center gap-3 rounded-lg border border-critical/30 bg-critical-subtle px-4 py-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-critical" aria-hidden />
          <span className="text-sm font-medium text-critical">
            {criticalCount} critical{" "}
            {criticalCount === 1 ? "alert needs" : "alerts need"} attention
          </span>
        </div>
      )}

      {/* Filter row: status tabs + severity dropdown */}
      <div className="flex flex-wrap items-center gap-3">
        <StatusTabs current={status} />
        <Select value={severityFilter} onValueChange={setSeverityFilter}>
          <SelectTrigger className="h-9 w-36 text-sm">
            <SelectValue placeholder="All severities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All severities</SelectItem>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="high">Critical</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Error banner for action failures */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
          {error}
          <button className="ml-auto underline" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Alert list or empty state */}
      {filteredAnomalies.length === 0 ? (
        anomalies.length > 0 ? (
          // Data exists but is hidden by the severity filter
          <EmptyState
            icon={Bell}
            title="No alerts match this filter"
            description="Try adjusting the severity filter to see more results."
            action={{ label: "Clear filter", onClick: () => setSeverityFilter("all") }}
          />
        ) : (
          // Truly no data for this status
          <EmptyState
            icon={status === "open" ? CheckCircle2 : Bell}
            title={
              status === "open"
                ? "All clear — no open alerts"
                : status === "acked"
                ? "No acknowledged alerts"
                : "No dismissed alerts"
            }
            description={
              status === "open"
                ? "Detection runs nightly. It requires 14+ days of spend history per scope."
                : status === "acked"
                ? "Alerts you acknowledge will appear here."
                : "Alerts you dismiss will appear here."
            }
          />
        )
      ) : (
        <div className="space-y-3">
          {filteredAnomalies.map((anomaly) => (
            <AlertCard
              key={anomaly.id}
              anomaly={anomaly}
              showActions={status === "open"}
              isLoading={(loadingId === anomaly.id && isPending) || isAckingAll}
              onAcknowledge={(id) => handleStatusUpdate(id, "acked")}
              onDismiss={(id) => handleStatusUpdate(id, "dismissed")}
            />
          ))}
        </div>
      )}
    </div>
  );
}
