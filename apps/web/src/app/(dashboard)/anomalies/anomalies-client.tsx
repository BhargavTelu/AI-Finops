"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, XCircle } from "lucide-react";
import { useAuth } from "@clerk/nextjs";

import { createApiClient } from "@/lib/api-client";
import type { AnomalyRead, AnomalyStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

// ── Severity badge ─────────────────────────────────────────────────────────────

const SEVERITY_STYLES: Record<string, string> = {
  low: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  medium: "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-400",
  high: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400",
};

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        SEVERITY_STYLES[severity] ?? "bg-muted text-muted-foreground"
      )}
    >
      {severity}
    </span>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtCost(raw: string): string {
  const n = parseFloat(raw);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Status tabs ────────────────────────────────────────────────────────────────

const TABS: { label: string; value: AnomalyStatus }[] = [
  { label: "Open", value: "open" },
  { label: "Acknowledged", value: "acked" },
  { label: "Dismissed", value: "dismissed" },
];

function StatusTabs({ current }: { current: AnomalyStatus }) {
  const router = useRouter();

  return (
    <div className="flex gap-1 rounded-lg bg-muted/60 p-1 w-fit">
      {TABS.map((tab) => (
        <button
          key={tab.value}
          onClick={() => router.push(`/anomalies?status=${tab.value}`)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
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

// ── Main component ─────────────────────────────────────────────────────────────

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

  async function handleStatusUpdate(id: string, newStatus: "acked" | "dismissed") {
    setError(null);
    setLoadingId(id);
    startTransition(async () => {
      try {
        const token = await getToken();
        const api = createApiClient(token!);
        await api.patch(`/anomalies/${id}`, { status: newStatus });
        // Remove from current tab view — it now belongs in a different tab.
        setAnomalies((prev) => prev.filter((a) => a.id !== id));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Update failed");
      } finally {
        setLoadingId(null);
      }
    });
  }

  return (
    <div className="space-y-4">
      <StatusTabs current={status} />

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <XCircle className="h-4 w-4 shrink-0" />
          {error}
          <button className="ml-auto underline" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {anomalies.length === 0 ? (
        <EmptyState status={status} />
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40">
              <tr>
                <th className="w-8 px-2 py-3" />
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Time</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Scope</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Spike</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Baseline</th>
                <th className="px-4 py-3 text-right font-medium text-muted-foreground">Actual</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Severity</th>
                {status === "open" && (
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Actions</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y">
              {anomalies.map((anomaly) => (
                <AnomalyRow
                  key={anomaly.id}
                  anomaly={anomaly}
                  showActions={status === "open"}
                  isLoading={loadingId === anomaly.id && isPending}
                  onUpdate={handleStatusUpdate}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Row ────────────────────────────────────────────────────────────────────────

interface RowProps {
  anomaly: AnomalyRead;
  showActions: boolean;
  isLoading: boolean;
  onUpdate: (id: string, status: "acked" | "dismissed") => void;
}

function AnomalyRow({ anomaly, showActions, isLoading, onUpdate }: RowProps) {
  const [expanded, setExpanded] = useState(false);
  const scopeLabel = anomaly.scope_value ?? anomaly.scope_kind;
  const contextTags = buildContextTags(anomaly.context);
  const hasExplanation = Boolean(anomaly.explanation);
  const colSpan = showActions ? 8 : 7;

  return (
    <>
      <tr className={cn("hover:bg-muted/20", expanded && "bg-muted/10")}>
        {/* Expand toggle — only shown when an explanation exists */}
        <td className="px-2 py-4 text-center">
          {hasExplanation && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label={expanded ? "Collapse explanation" : "Expand explanation"}
            >
              {expanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
          )}
        </td>
        <td className="px-4 py-4 text-muted-foreground whitespace-nowrap">
          {fmtDate(anomaly.detected_at)}
        </td>
        <td className="px-4 py-4">
          <div className="font-medium">{scopeLabel}</div>
          {contextTags && (
            <div className="mt-0.5 text-xs text-muted-foreground">{contextTags}</div>
          )}
        </td>
        <td className="px-4 py-4 text-right tabular-nums font-medium text-red-600 dark:text-red-400">
          +{anomaly.spike_pct}%
        </td>
        <td className="px-4 py-4 text-right tabular-nums text-muted-foreground">
          {fmtCost(anomaly.baseline_usd)}/day
        </td>
        <td className="px-4 py-4 text-right tabular-nums font-medium">
          {fmtCost(anomaly.actual_usd)}
        </td>
        <td className="px-4 py-4">
          <SeverityBadge severity={anomaly.severity} />
        </td>
        {showActions && (
          <td className="px-4 py-4">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1.5 text-xs"
                disabled={isLoading}
                onClick={() => onUpdate(anomaly.id, "acked")}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Ack
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                disabled={isLoading}
                onClick={() => onUpdate(anomaly.id, "dismissed")}
              >
                <XCircle className="h-3.5 w-3.5" />
                Dismiss
              </Button>
            </div>
          </td>
        )}
      </tr>

      {/* Collapsible explanation row */}
      {expanded && anomaly.explanation && (
        <tr className="bg-muted/5">
          <td />
          <td colSpan={colSpan - 1} className="px-4 pb-4 pt-1">
            <p className="text-sm text-muted-foreground leading-relaxed">
              {anomaly.explanation}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

// Build a compact tag context string from the context jsonb, e.g. "chat-v2 · backend"
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

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState({ status }: { status: AnomalyStatus }) {
  const messages: Record<AnomalyStatus, { title: string; body: string }> = {
    open: {
      title: "No anomalies detected",
      body: "Detection runs nightly after aggregation. It requires 14+ days of spend history per model.",
    },
    acked: {
      title: "No acknowledged anomalies",
      body: "Anomalies you mark as acknowledged will appear here.",
    },
    dismissed: {
      title: "No dismissed anomalies",
      body: "Anomalies you dismiss will appear here.",
    },
  };

  const { title, body } = messages[status];

  return (
    <div className="flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-50 dark:bg-amber-950/40">
        <AlertTriangle className="h-7 w-7 text-amber-500" strokeWidth={1.5} />
      </div>
      <h2 className="text-base font-medium">{title}</h2>
      <p className="mt-2 max-w-xs text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
