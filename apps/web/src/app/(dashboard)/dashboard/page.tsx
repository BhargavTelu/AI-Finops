import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { createApiClient } from "@/lib/api-client";
import { DashboardCharts, type ChartRow } from "@/components/dashboard-charts";
import type { DailyPoint, UsageSummary } from "@/lib/types";

// Format a date ISO string as "Jan 1" for chart axis labels
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
}

function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="rounded-lg border bg-card p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
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

  // Empty state — no data yet (no integrations connected or worker hasn't run)
  if (!summary || summary.total_requests === 0) {
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          No spend data yet.{" "}
          <Link href="/settings/integrations" className="underline hover:text-foreground">
            Connect an integration
          </Link>{" "}
          to start tracking your LLM costs.
        </p>
      </div>
    );
  }

  // Pivot flat DailyPoint[] → Tremor chart format
  // Collect unique models
  const models = [...new Set(timeseries.map((p) => p.group_key))].sort();

  // Build one row per day, with a column for each model's cost
  const dayMap = new Map<string, ChartRow>();
  for (const point of timeseries) {
    const label = fmtDay(point.day);
    if (!dayMap.has(point.day)) {
      dayMap.set(point.day, { date: label });
    }
    const row = dayMap.get(point.day)!;
    row[point.group_key] = parseFloat(point.cost_usd);
  }
  // Sort by day ascending
  const chartData = [...dayMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, row]) => row);

  // Bar chart: total cost per model over the period, top 10 descending
  const modelTotals = new Map<string, number>();
  for (const point of timeseries) {
    modelTotals.set(
      point.group_key,
      (modelTotals.get(point.group_key) ?? 0) + parseFloat(point.cost_usd),
    );
  }
  const barData = [...modelTotals.entries()]
    .map(([model, cost]) => ({
      // Truncate long model version suffixes for bar chart readability
      model: model.length > 28 ? model.slice(0, 26) + "…" : model,
      cost,
    }))
    .sort((a, b) => b.cost - a.cost)
    .slice(0, 10);

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="30d cost" value={fmtCost(summary.total_cost_usd)} />
        <StatCard label="30d requests" value={fmtNumber(summary.total_requests)} />
        <StatCard label="30d tokens" value={fmtNumber(summary.total_tokens)} />
      </div>

      {/* Charts (client component — Tremor requires browser rendering) */}
      <DashboardCharts chartData={chartData} models={models} barData={barData} />
    </div>
  );
}
