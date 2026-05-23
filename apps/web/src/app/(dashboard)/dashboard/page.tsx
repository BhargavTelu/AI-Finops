import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { TrendingUp, ArrowRight } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import {
  DashboardCharts,
  DashboardStatCards,
  ProviderDonut,
  type ChartRow,
} from "@/components/dashboard-charts";
import { PageMotion } from "@/components/motion-wrapper";
import type { BudgetRead, DailyPoint, DashboardSummary, ExploreRow } from "@/lib/types";

function fmtDay(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function fmtCost(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(2)}`;
}

export default async function DashboardPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const [dashboard, timeseries, providers, budgets] = await Promise.all([
    api.get<DashboardSummary>("/usage/dashboard").catch(() => null),
    api.get<DailyPoint[]>("/usage/timeseries?range=30d&group_by=model").catch(
      () => [] as DailyPoint[],
    ),
    api.get<ExploreRow[]>("/usage/explore?group_by=provider&range=30d").catch(
      () => [] as ExploreRow[],
    ),
    api.get<BudgetRead[]>("/budgets").catch(() => [] as BudgetRead[]),
  ]);

  // Empty state — no integrations connected or no data yet
  if (!dashboard || dashboard.month.total_requests === 0) {
    return (
      <PageMotion>
        <div className="flex h-full min-h-[400px] flex-col items-center justify-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
            <TrendingUp className="h-7 w-7 text-primary" strokeWidth={1.5} />
          </div>
          <h2 className="text-lg font-semibold">No spend data yet</h2>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            Connect an integration to start tracking your LLM API costs across models and providers.
          </p>
          <Link
            href="/settings/integrations"
            className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Connect integration
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </PageMotion>
    );
  }

  // ── Budget status for MTD card color coding ──────────────────────────────
  const globalBudget = budgets.find((b) => b.scope_type === "global");
  const budgetStatus: "healthy" | "warning" | "over" = globalBudget
    ? globalBudget.spent_pct >= 100
      ? "over"
      : globalBudget.spent_pct >= globalBudget.alert_at_pct
        ? "warning"
        : "healthy"
    : "healthy";

  // ── Sparklines — derive total-per-day from the timeseries ─────────────────
  // timeseries has one row per (day, model); aggregate to total cost per day.
  const dailyTotals = new Map<string, number>();
  for (const point of timeseries) {
    dailyTotals.set(point.day, (dailyTotals.get(point.day) ?? 0) + parseFloat(point.cost_usd));
  }
  const sortedDays = [...dailyTotals.entries()].sort(([a], [b]) => a.localeCompare(b));
  const allDailyCosts = sortedDays.map(([, cost]) => cost);

  // Current calendar month prefix (YYYY-MM) for MTD sparkline
  const thisMonthPrefix = new Date().toISOString().slice(0, 7);

  const sparklines = {
    day: allDailyCosts.slice(-2),   // last 2 days so there's a direction to show
    week: allDailyCosts.slice(-7),
    month: allDailyCosts,
    mtd: sortedDays
      .filter(([day]) => day.startsWith(thisMonthPrefix))
      .map(([, cost]) => cost),
  };

  // ── Pivot timeseries for 30d area chart ──────────────────────────────────
  const models = [...new Set(timeseries.map((p) => p.group_key))].sort();
  const dayMap = new Map<string, ChartRow>();
  for (const point of timeseries) {
    const label = fmtDay(point.day);
    if (!dayMap.has(point.day)) dayMap.set(point.day, { date: label });
    const row = dayMap.get(point.day)!;
    row[point.group_key] = parseFloat(point.cost_usd);
  }
  const chartData = [...dayMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, row]) => row);

  // ── Top-10 by-model bar chart ─────────────────────────────────────────────
  const modelTotals = new Map<string, number>();
  for (const point of timeseries) {
    modelTotals.set(
      point.group_key,
      (modelTotals.get(point.group_key) ?? 0) + parseFloat(point.cost_usd),
    );
  }
  const barData = [...modelTotals.entries()]
    .map(([model, cost]) => ({
      model: model.length > 28 ? model.slice(0, 26) + "…" : model,
      cost,
    }))
    .sort((a, b) => b.cost - a.cost)
    .slice(0, 10);

  // ── MoM comparison values ─────────────────────────────────────────────────
  const momPct = dashboard.mom_pct_change;
  const lastMonthCost = parseFloat(dashboard.last_month_cost_usd);

  return (
    <PageMotion>
      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            All providers · complete days only (UTC)
          </p>
        </div>

        {/* Four time-window stat cards with sparklines */}
        <DashboardStatCards
          periods={dashboard}
          sparklines={sparklines}
          budgetStatus={budgetStatus}
        />

        {/* MoM callout + provider donut row */}
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Month-over-month comparison */}
          <div className="rounded-xl border border-border/60 bg-card p-5">
            <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Month over month
            </p>
            {momPct === null ? (
              <>
                <p className="mt-2 text-2xl font-semibold text-muted-foreground">—</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  No prior-month data yet
                </p>
              </>
            ) : (
              <>
                <p
                  className={`mt-2 text-2xl font-semibold tabular-nums ${
                    momPct > 0
                      ? "text-red-600 dark:text-red-400"
                      : "text-emerald-600 dark:text-emerald-400"
                  }`}
                >
                  {momPct > 0 ? "+" : ""}
                  {momPct.toFixed(1)}%
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  vs {fmtCost(lastMonthCost)} same period last month
                </p>
              </>
            )}
          </div>

          {/* Spend by provider donut */}
          <div className="rounded-xl border border-border/60 bg-card p-5">
            <div className="mb-3">
              <h2 className="text-sm font-medium">Spend by provider</h2>
              <p className="text-xs text-muted-foreground">30-day share</p>
            </div>
            <ProviderDonut rows={providers} />
          </div>
        </div>

        {/* 30d trend + top-10 model charts */}
        <DashboardCharts chartData={chartData} models={models} barData={barData} />
      </div>
    </PageMotion>
  );
}
