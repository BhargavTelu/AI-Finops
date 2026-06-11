"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Lightbulb,
  ArrowRight,
  Check,
  X,
  TrendingDown,
  Layers,
  Zap,
  CircleDollarSign,
  Loader2,
} from "lucide-react";
import { useAuth } from "@clerk/nextjs";

import { createApiClient } from "@/lib/api-client";
import type { RecommendationRead, RecommendationStatus, RecommendationType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { StaggerGrid, StaggerItem } from "@/components/motion-wrapper";

// ── Type config ───────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<
  RecommendationType,
  { label: string; icon: React.ElementType; styles: string }
> = {
  model_swap: {
    label: "Model swap",
    icon: TrendingDown,
    styles: "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400",
  },
  caching: {
    label: "Prompt caching",
    icon: Layers,
    styles: "bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-400",
  },
  batch: {
    label: "Batch API",
    icon: Zap,
    styles: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  },
  other: {
    label: "Other",
    icon: Lightbulb,
    styles: "bg-muted text-muted-foreground",
  },
};

// ── Effort config - derived from recommendation type ──────────────────────────
// model_swap = Easy (config change only), caching/batch = Medium (code change needed),
// other = Hard (effort unknown)

const EFFORT_CONFIG: Record<
  RecommendationType,
  { label: string; className: string }
> = {
  model_swap: {
    label: "Easy",
    className: "bg-success-subtle text-success border-success/20",
  },
  caching: {
    label: "Medium",
    className: "bg-warning-subtle text-warning border-warning/20",
  },
  batch: {
    label: "Medium",
    className: "bg-warning-subtle text-warning border-warning/20",
  },
  other: {
    label: "Hard",
    className: "bg-muted text-muted-foreground border-border",
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtSavings(raw: string | null): string | null {
  if (!raw) return null;
  const n = parseFloat(raw);
  if (n <= 0) return null;
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}k/mo`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/mo`;
}

function fmtTotalSavings(total: number): string {
  if (total >= 1000) return `$${(total / 1000).toFixed(1)}k/mo`;
  return `$${total.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/mo`;
}

// ── Badges ────────────────────────────────────────────────────────────────────

function TypeBadge({ type }: { type: RecommendationType }) {
  const { label, icon: Icon, styles } = TYPE_CONFIG[type] ?? TYPE_CONFIG.other;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        styles
      )}
    >
      <Icon className="h-3 w-3" strokeWidth={2} />
      {label}
    </span>
  );
}

function EffortBadge({ type }: { type: RecommendationType }) {
  const { label, className } = EFFORT_CONFIG[type] ?? EFFORT_CONFIG.other;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        className
      )}
    >
      {label}
    </span>
  );
}

// ── Effort filter pills ───────────────────────────────────────────────────────

type EffortLevel = "Easy" | "Medium" | "Hard";

const EFFORT_PILL_STYLES: Record<EffortLevel, { base: string; active: string }> = {
  Easy: {
    base: "border-success/20 text-success hover:bg-success-subtle",
    active: "bg-success-subtle border-success/20 text-success",
  },
  Medium: {
    base: "border-warning/20 text-warning hover:bg-warning-subtle",
    active: "bg-warning-subtle border-warning/20 text-warning",
  },
  Hard: {
    base: "border-border text-muted-foreground hover:bg-muted",
    active: "bg-muted border-border text-foreground",
  },
};

function EffortFilterPills({
  selected,
  onChange,
}: {
  selected: Set<EffortLevel>;
  onChange: (next: Set<EffortLevel>) => void;
}) {
  function toggle(level: EffortLevel) {
    const next = new Set(selected);
    if (next.has(level)) next.delete(level);
    else next.add(level);
    onChange(next);
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Effort:</span>
      {(["Easy", "Medium", "Hard"] as EffortLevel[]).map((level) => {
        const isActive = selected.has(level);
        const styles = EFFORT_PILL_STYLES[level];
        return (
          <button
            key={level}
            onClick={() => toggle(level)}
            aria-pressed={isActive}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
              isActive ? styles.active : cn("bg-background", styles.base)
            )}
          >
            {level}
          </button>
        );
      })}
    </div>
  );
}

// ── Confidence bar ────────────────────────────────────────────────────────────

function ConfidenceBar({ confidence }: { confidence: string | null }) {
  if (!confidence) return null;
  const pct = Math.round(parseFloat(confidence) * 100);
  const barColor =
    pct >= 80 ? "bg-success" : pct >= 60 ? "bg-warning" : "bg-muted-foreground/40";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", barColor)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">{pct}% confidence</span>
    </div>
  );
}

// ── Status tabs ───────────────────────────────────────────────────────────────

const TABS: { label: string; value: RecommendationStatus }[] = [
  { label: "New", value: "new" },
  { label: "Applied", value: "applied" },
  { label: "Dismissed", value: "dismissed" },
];

function StatusTabs({ current }: { current: RecommendationStatus }) {
  const router = useRouter();
  return (
    <div role="tablist" className="flex gap-1 rounded-lg bg-muted/60 p-1 w-fit">
      {TABS.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          aria-selected={current === tab.value}
          onClick={() =>
            router.push(`/recommendations?status=${tab.value}`, { scroll: false })
          }
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

// ── Recommendation card ───────────────────────────────────────────────────────

interface CardProps {
  rec: RecommendationRead;
  onApply: (id: string) => void;
  onDismiss: (id: string) => void;
  pending: boolean;
}

function RecCard({ rec, onApply, onDismiss, pending }: CardProps) {
  const savings = fmtSavings(rec.projected_savings_usd);
  const isApplied = rec.status === "applied";
  const isDismissed = rec.status === "dismissed";
  const isResolved = isApplied || isDismissed;

  return (
    <div
      className={cn(
        "flex flex-col rounded-xl bg-card shadow-card transition-all hover:shadow-card-hover",
        isResolved && "opacity-70",
        pending && "opacity-60 pointer-events-none"
      )}
    >
      {/* Two-column layout: savings on left, content on right */}
      <div className="flex gap-5 p-5">
        {/* Left: savings + effort/type badges */}
        <div className="flex w-36 shrink-0 flex-col gap-3">
          <div className="flex flex-wrap gap-1.5">
            <EffortBadge type={rec.type} />
            <TypeBadge type={rec.type} />
          </div>

          {/* Savings - dominant visual per spec */}
          {savings && !isResolved && (
            <div>
              <p className="text-2xl font-bold text-success text-mono leading-tight">
                {savings}
              </p>
              <p className="text-xs text-muted-foreground">estimated savings</p>
            </div>
          )}

          {/* Resolved indicator */}
          {isApplied && (
            <div className="flex items-center gap-1.5">
              <Check className="h-4 w-4 shrink-0 text-success" />
              <div>
                <p className="text-sm font-medium text-success">Applied</p>
                {rec.resolved_at && (
                  <p className="text-xs text-muted-foreground">
                    {new Date(rec.resolved_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </p>
                )}
              </div>
            </div>
          )}

          {isDismissed && (
            <div className="flex items-center gap-1.5">
              <X className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-sm text-muted-foreground">Dismissed</p>
                {rec.resolved_at && (
                  <p className="text-xs text-muted-foreground">
                    {new Date(rec.resolved_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: title + description */}
        <div className="flex flex-1 flex-col gap-2 min-w-0">
          <h3 className="text-sm font-semibold leading-snug">{rec.title}</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{rec.description}</p>
        </div>
      </div>

      {/* Footer: confidence + actions */}
      <div className="flex items-center justify-between gap-4 border-t border-border/60 px-5 py-3">
        <ConfidenceBar confidence={rec.confidence} />

        {rec.status === "new" && (
          <div className="flex shrink-0 items-center gap-2">
            <Button
              size="sm"
              variant="default"
              disabled={pending}
              onClick={() => onApply(rec.id)}
              className="h-8 gap-1.5"
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              Apply
              {!pending && <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => onDismiss(rec.id)}
              className="h-8 text-muted-foreground hover:text-foreground"
            >
              Dismiss
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

export function RecommendationsLoading() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="space-y-1.5">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-80" />
      </div>

      {/* Filter + summary skeleton */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-9 w-56 rounded-lg" />
        <Skeleton className="h-5 w-52" />
      </div>

      {/* Card skeletons */}
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl bg-card shadow-card">
            <div className="flex gap-5 p-5">
              <div className="w-36 shrink-0 space-y-3">
                <div className="flex gap-1.5">
                  <Skeleton className="h-5 w-14 rounded-full" />
                  <Skeleton className="h-5 w-20 rounded-full" />
                </div>
                <Skeleton className="h-8 w-24" />
                <Skeleton className="h-3 w-28" />
              </div>
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-5/6" />
              </div>
            </div>
            <div className="flex items-center justify-between border-t border-border/60 px-5 py-3">
              <Skeleton className="h-4 w-32" />
              <div className="flex gap-2">
                <Skeleton className="h-8 w-24 rounded-md" />
                <Skeleton className="h-8 w-20 rounded-md" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  initialRecs: RecommendationRead[];
  status: RecommendationStatus;
}

export function RecommendationsClient({ initialRecs, status }: Props) {
  const { getToken } = useAuth();
  const [recs, setRecs] = useState<RecommendationRead[]>(initialRecs);
  const [error, setError] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [effortFilter, setEffortFilter] = useState<Set<EffortLevel>>(new Set());

  // Filter recs by selected effort levels (empty set = show all)
  const filteredRecs = useMemo(() => {
    if (effortFilter.size === 0) return recs;
    return recs.filter((r) => {
      const level = EFFORT_CONFIG[r.type]?.label as EffortLevel | undefined;
      return level !== undefined && effortFilter.has(level);
    });
  }, [recs, effortFilter]);

  // Total potential savings across all visible "new" recommendations (pre-filter)
  const totalSavings = useMemo(
    () =>
      recs.reduce(
        (sum, r) =>
          sum + (r.projected_savings_usd ? parseFloat(r.projected_savings_usd) : 0),
        0
      ),
    [recs]
  );

  async function handleAction(id: string, action: "applied" | "dismissed") {
    setPendingId(id);
    setError("");

    // Optimistic removal - revert on error
    setRecs((prev) => prev.filter((r) => r.id !== id));

    try {
      const token = await getToken();
      await createApiClient(token!).patch<RecommendationRead>(`/recommendations/${id}`, {
        status: action,
      });
    } catch (err: unknown) {
      setRecs(initialRecs);
      setError(err instanceof Error ? err.message : "Action failed. Please try again.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Recommendations"
        description="Rule-based savings opportunities - analyzed nightly from your LLM usage patterns"
      />

      {/* Filter row + summary bar */}
      <div className="flex flex-wrap items-center gap-4">
        <StatusTabs current={status} />
        {status === "new" && recs.length > 0 && (
          <EffortFilterPills selected={effortFilter} onChange={setEffortFilter} />
        )}
        {status === "new" && recs.length > 0 && totalSavings > 0 && (
          <p className="text-sm text-muted-foreground">
            <span className="font-semibold text-success text-mono">
              {fmtTotalSavings(totalSavings)}
            </span>{" "}
            estimated savings across {recs.length}{" "}
            {recs.length === 1 ? "recommendation" : "recommendations"}
          </p>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Content */}
      {recs.length === 0 ? (
        // No data for this status tab
        <EmptyState
          icon={status === "new" ? Lightbulb : CircleDollarSign}
          title={
            status === "new"
              ? "No recommendations yet"
              : status === "applied"
              ? "No applied recommendations"
              : "No dismissed recommendations"
          }
          description={
            status === "new"
              ? "Savings opportunities appear after your first nightly analysis. We look for model downgrade opportunities, caching candidates, and batch-eligible workloads."
              : status === "applied"
              ? "Recommendations you mark as applied will appear here."
              : "Recommendations you dismiss will appear here."
          }
          action={
            status === "new"
              ? { label: "Explore cost breakdown", href: "/cost-explorer" }
              : undefined
          }
        />
      ) : filteredRecs.length === 0 ? (
        // Data exists but hidden by effort filter
        <EmptyState
          icon={Lightbulb}
          title="No recommendations match this filter"
          description="Try selecting a different effort level or clear the filter to see all recommendations."
          action={{ label: "Clear filter", onClick: () => setEffortFilter(new Set()) }}
        />
      ) : (
        <StaggerGrid className="space-y-4">
          {filteredRecs.map((rec) => (
            <StaggerItem key={rec.id}>
              <RecCard
                rec={rec}
                onApply={(id) => handleAction(id, "applied")}
                onDismiss={(id) => handleAction(id, "dismissed")}
                pending={pendingId === rec.id}
              />
            </StaggerItem>
          ))}
        </StaggerGrid>
      )}

      {/* Link to cost explorer for applied/dismissed tabs */}
      {status !== "new" && recs.length > 0 && (
        <div className="pt-2 text-center">
          <Link
            href="/recommendations"
            className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
          >
            View new recommendations
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}
    </div>
  );
}
