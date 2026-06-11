import { auth } from "@clerk/nextjs/server";
import { TrendingUp } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import {
  DashboardStatCards,
  ProviderDonut,
  SpendTrendChart,
  TopModelsChart,
  RecentAlertsWidget,
  type ChartRow,
} from "@/components/dashboard-charts";
import { ActivationChecklist } from "@/components/activation-checklist";
import { PageMotion } from "@/components/motion-wrapper";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { PeriodSelector } from "./period-selector";
import type {
  AnomalyRead,
  BudgetRead,
  DailyPoint,
  DashboardSummary,
  ExploreRow,
  ForecastResult,
  OnboardingStatus,
} from "@/lib/types";

const VALID_RANGE = new Set(["7d", "30d", "90d"]);

const RANGE_LABELS: Record<string, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
};

function fmtDay(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function fmtCost(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return usd.format(n);
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string }>;
}) {
  const params = await searchParams;
  const range = VALID_RANGE.has(params.range ?? "") ? (params.range ?? "30d") : "30d";

  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const [dashboard, timeseries, providers, budgets, anomalies, forecast, onboarding] =
    await Promise.all([
      api.get<DashboardSummary>("/usage/dashboard").catch(() => null),
      api
        .get<DailyPoint[]>(`/usage/timeseries?range=${range}&group_by=model`)
        .catch(() => [] as DailyPoint[]),
      api
        .get<ExploreRow[]>(`/usage/explore?group_by=provider&range=${range}`)
        .catch(() => [] as ExploreRow[]),
      api.get<BudgetRead[]>("/budgets").catch(() => [] as BudgetRead[]),
      api.get<AnomalyRead[]>("/anomalies").catch(() => [] as AnomalyRead[]),
      // 404 until there is enough data to forecast - render no card then.
      api.get<ForecastResult>("/usage/forecast").catch(() => null),
      api.get<OnboardingStatus>("/onboarding/status").catch(() => null),
    ]);

  // Empty state - no integrations connected or no data yet. The activation
  // checklist matters most here: it is the new org's map to first value.
  if (!dashboard || dashboard.month.total_requests === 0) {
    return (
      <PageMotion>
        <div className="space-y-6">
          <PageHeader
            title="Dashboard"
            description="LLM spend overview for your organisation"
            actions={<PeriodSelector range={range} />}
          />
          {onboarding && <ActivationChecklist status={onboarding} />}
          <EmptyState
            icon={TrendingUp}
            title="No spend data yet"
            description="Connect an integration to start tracking your LLM API costs across models and providers."
            action={{ label: "Connect integration", href: "/settings/integrations" }}
          />
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

  // ── Derive sparklines from timeseries ────────────────────────────────────
  const dailyTotals = new Map<string, number>();
  for (const point of timeseries) {
    dailyTotals.set(point.day, (dailyTotals.get(point.day) ?? 0) + parseFloat(point.cost_usd));
  }
  const sortedDays = [...dailyTotals.entries()].sort(([a], [b]) => a.localeCompare(b));
  const allDailyCosts = sortedDays.map(([, cost]) => cost);

  const thisMonthPrefix = new Date().toISOString().slice(0, 7);
  const sparklines = {
    day: allDailyCosts.slice(-2),
    week: allDailyCosts.slice(-7),
    month: allDailyCosts,
    mtd: sortedDays
      .filter(([day]) => day.startsWith(thisMonthPrefix))
      .map(([, cost]) => cost),
  };

  // ── Pivot timeseries for area chart ──────────────────────────────────────
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

  // ── Top-10 bar chart data ─────────────────────────────────────────────────
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

  // ── Provider total for card header ────────────────────────────────────────
  const totalProviderCost = providers.reduce(
    (sum, r) => sum + parseFloat(r.total_cost_usd),
    0,
  );

  const rangeLabel = RANGE_LABELS[range] ?? range;

  return (
    <PageMotion>
      <div className="space-y-6">
        {/* ── Page header with period selector ─────────────────────────── */}
        <PageHeader
          title="Dashboard"
          description="LLM spend overview · all providers · complete days only (UTC)"
          actions={<PeriodSelector range={range} />}
        />

        {/* ── Activation checklist (hidden once complete or dismissed) ──── */}
        {onboarding && <ActivationChecklist status={onboarding} />}

        {/* ── KPI stat cards (+ month-end forecast when available) ─────── */}
        <DashboardStatCards
          periods={dashboard}
          sparklines={sparklines}
          budgetStatus={budgetStatus}
          forecast={forecast}
        />

        {/* ── Spend trend (2/3 width) + Provider split (1/3 width) ─────── */}
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Spend trend area chart */}
          <div className="rounded-xl bg-card p-6 shadow-card lg:col-span-2">
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-foreground">Spend trend</h2>
              <p className="text-xs text-muted-foreground">
                Daily spend by model · {rangeLabel}
              </p>
            </div>
            <SpendTrendChart chartData={chartData} models={models} />
          </div>

          {/* Provider split donut */}
          <div className="rounded-xl bg-card p-6 shadow-card">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground">By provider</h2>
                <p className="text-xs text-muted-foreground">{rangeLabel} share</p>
              </div>
              <span className="text-sm font-semibold text-mono">
                {fmtCost(totalProviderCost)}
              </span>
            </div>
            <ProviderDonut rows={providers} />
          </div>
        </div>

        {/* ── Top models (1/2) + Recent alerts (1/2) ───────────────────── */}
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Top-10 models bar chart */}
          <div className="rounded-xl bg-card p-6 shadow-card">
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-foreground">Cost by model</h2>
              <p className="text-xs text-muted-foreground">
                Top 10 models · {rangeLabel}
              </p>
            </div>
            <TopModelsChart barData={barData} />
          </div>

          {/* Recent open anomalies */}
          <RecentAlertsWidget anomalies={anomalies} />
        </div>
      </div>
    </PageMotion>
  );
}
