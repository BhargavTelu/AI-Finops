"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lightbulb, ArrowRight, CheckCircle2, XCircle, TrendingDown, Layers, Zap } from "lucide-react";
import { useAuth } from "@clerk/nextjs";

import { createApiClient } from "@/lib/api-client";
import type { RecommendationRead, RecommendationStatus, RecommendationType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// ── Type badge ──────────────────────────────────────────────────────────────

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

// ── Savings badge ────────────────────────────────────────────────────────────

function SavingsBadge({ savings }: { savings: string | null }) {
  if (!savings) return null;
  const n = parseFloat(savings);
  if (n <= 0) return null;
  const label =
    n >= 1000
      ? `$${(n / 1000).toFixed(1)}k/mo`
      : `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/mo`;
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
      Save {label}
    </span>
  );
}

// ── Confidence bar ───────────────────────────────────────────────────────────

function ConfidenceBar({ confidence }: { confidence: string | null }) {
  if (!confidence) return null;
  const pct = Math.round(parseFloat(confidence) * 100);
  const color =
    pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-400" : "bg-muted-foreground/40";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">{pct}% confidence</span>
    </div>
  );
}

// ── Status tabs ──────────────────────────────────────────────────────────────

const TABS: { label: string; value: RecommendationStatus }[] = [
  { label: "New", value: "new" },
  { label: "Applied", value: "applied" },
  { label: "Dismissed", value: "dismissed" },
];

function StatusTabs({ current }: { current: RecommendationStatus }) {
  const router = useRouter();
  return (
    <div className="flex gap-1 rounded-lg bg-muted/60 p-1">
      {TABS.map((tab) => (
        <button
          key={tab.value}
          onClick={() =>
            router.push(`/recommendations?status=${tab.value}`, { scroll: false })
          }
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

// ── Recommendation card ──────────────────────────────────────────────────────

interface CardProps {
  rec: RecommendationRead;
  onApply: (id: string) => void;
  onDismiss: (id: string) => void;
  pending: boolean;
}

function RecCard({ rec, onApply, onDismiss, pending }: CardProps) {
  return (
    <div className="rounded-xl border bg-card p-5 transition-shadow hover:shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TypeBadge type={rec.type} />
        <SavingsBadge savings={rec.projected_savings_usd} />
      </div>

      <h3 className="mb-1 text-sm font-semibold leading-snug">{rec.title}</h3>
      <p className="mb-4 text-sm text-muted-foreground leading-relaxed">{rec.description}</p>

      <div className="mb-4">
        <ConfidenceBar confidence={rec.confidence} />
      </div>

      {rec.status === "new" && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="default"
            disabled={pending}
            onClick={() => onApply(rec.id)}
            className="h-8 gap-1.5"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Mark applied
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() => onDismiss(rec.id)}
            className="h-8 gap-1.5"
          >
            <XCircle className="h-3.5 w-3.5" />
            Dismiss
          </Button>
        </div>
      )}

      {rec.status !== "new" && (
        <p className="text-xs text-muted-foreground">
          {rec.status === "applied" ? "Marked as applied" : "Dismissed"}
          {rec.resolved_at
            ? ` on ${new Date(rec.resolved_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}`
            : ""}
        </p>
      )}
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ status }: { status: RecommendationStatus }) {
  if (status === "new") {
    return (
      <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 dark:bg-emerald-950/40">
          <Lightbulb className="h-7 w-7 text-emerald-500" strokeWidth={1.5} />
        </div>
        <h2 className="text-base font-medium">No recommendations yet</h2>
        <p className="mt-2 max-w-xs text-sm text-muted-foreground">
          Savings opportunities appear after your first nightly analysis. We look for model
          downgrade opportunities, caching candidates, and batch-eligible workloads.
        </p>
        <Link
          href="/cost-explorer"
          className="mt-5 inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          Explore cost breakdown <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    );
  }
  return (
    <div className="flex min-h-[200px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 text-center">
      <p className="text-sm text-muted-foreground">
        No {status === "applied" ? "applied" : "dismissed"} recommendations yet.
      </p>
    </div>
  );
}

// ── Loading skeleton ─────────────────────────────────────────────────────────

export function RecommendationsLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <Skeleton className="h-9 w-64" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border bg-card p-5 space-y-3">
            <div className="flex gap-2">
              <Skeleton className="h-5 w-24 rounded-full" />
              <Skeleton className="h-5 w-20 rounded-full" />
            </div>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-4/6" />
            <div className="flex gap-2 pt-1">
              <Skeleton className="h-8 w-28" />
              <Skeleton className="h-8 w-20" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main client component ────────────────────────────────────────────────────

interface Props {
  initialRecs: RecommendationRead[];
  status: RecommendationStatus;
}

export function RecommendationsClient({ initialRecs, status }: Props) {
  const { getToken } = useAuth();
  const [recs, setRecs] = useState<RecommendationRead[]>(initialRecs);
  const [error, setError] = useState("");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  async function handleAction(id: string, action: "applied" | "dismissed") {
    setPendingId(id);
    setError("");

    // Optimistic removal from the current list
    setRecs((prev) => prev.filter((r) => r.id !== id));

    try {
      const token = await getToken();
      await createApiClient(token!).patch<RecommendationRead>(
        `/recommendations/${id}`,
        { status: action }
      );
    } catch (err: unknown) {
      // Revert optimistic update on error
      setRecs(initialRecs);
      setError(err instanceof Error ? err.message : "Action failed. Please try again.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <StatusTabs current={status} />

      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {recs.length === 0 ? (
        <EmptyState status={status} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {recs.map((rec) => (
            <RecCard
              key={rec.id}
              rec={rec}
              onApply={(id) => startTransition(() => { handleAction(id, "applied"); })}
              onDismiss={(id) => startTransition(() => { handleAction(id, "dismissed"); })}
              pending={pendingId === rec.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
