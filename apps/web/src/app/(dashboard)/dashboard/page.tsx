import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { TrendingUp, Activity, Cpu, ArrowRight } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import { DashboardCharts, type ChartRow } from "@/components/dashboard-charts";
import { PageMotion, StaggerGrid, StaggerItem } from "@/components/motion-wrapper";
import type { DailyPoint, UsageSummary } from "@/lib/types";

function fmtDay(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function fmtCost(raw: string): string {
  const n = parseFloat(raw);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(2)}`;
}

function fmtNumber(n: number): string {
  return n.toLocaleString("en-US");
}

interface StatCardProps {
  label: string;
  value: string;
  sub: string;
  icon: React.ElementType;
  iconColor: string;
  iconBg: string;
}

function StatCard({ label, value, sub, icon: Icon, iconColor, iconBg }: StatCardProps) {
  return (
    <div className="rounded-xl border border-border/60 bg-card p-5 transition-shadow duration-200 hover:shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{sub}</p>
        </div>
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${iconBg}`}>
          <Icon className={`h-4 w-4 ${iconColor}`} strokeWidth={2} />
        </div>
      </div>
    </div>
  );
}

export default async function DashboardPage() {
  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const [summary, timeseries] = await Promise.all([
    api.get<UsageSummary>("/usage/summary?range=30d").catch(() => null),
    api.get<DailyPoint[]>("/usage/timeseries?range=30d&group_by=model").catch(() => [] as DailyPoint[]),
  ]);

  // Empty state
  if (!summary || summary.total_requests === 0) {
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

  // Pivot flat DailyPoint[] → Tremor chart format
  const models = [...new Set(timeseries.map((p) => p.group_key))].sort();

  const dayMap = new Map<string, ChartRow>();
  for (const point of timeseries) {
    const label = fmtDay(point.day);
    if (!dayMap.has(point.day)) {
      dayMap.set(point.day, { date: label });
    }
    const row = dayMap.get(point.day)!;
    row[point.group_key] = parseFloat(point.cost_usd);
  }
  const chartData = [...dayMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, row]) => row);

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

  return (
    <PageMotion>
      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Last 30 days · all providers</p>
        </div>

        {/* Stat cards */}
        <StaggerGrid className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StaggerItem>
            <StatCard
              label="Total spend"
              value={fmtCost(summary.total_cost_usd)}
              sub="30-day rolling"
              icon={TrendingUp}
              iconColor="text-blue-600 dark:text-blue-400"
              iconBg="bg-blue-50 dark:bg-blue-950/60"
            />
          </StaggerItem>
          <StaggerItem>
            <StatCard
              label="API requests"
              value={fmtNumber(summary.total_requests)}
              sub="30-day rolling"
              icon={Activity}
              iconColor="text-emerald-600 dark:text-emerald-400"
              iconBg="bg-emerald-50 dark:bg-emerald-950/60"
            />
          </StaggerItem>
          <StaggerItem>
            <StatCard
              label="Tokens used"
              value={fmtNumber(summary.total_tokens)}
              sub="30-day rolling"
              icon={Cpu}
              iconColor="text-violet-600 dark:text-violet-400"
              iconBg="bg-violet-50 dark:bg-violet-950/60"
            />
          </StaggerItem>
        </StaggerGrid>

        {/* Charts */}
        <DashboardCharts chartData={chartData} models={models} barData={barData} />
      </div>
    </PageMotion>
  );
}
