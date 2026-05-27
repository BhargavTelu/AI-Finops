"use client";

import {
  AreaChart,
  BarChart,
} from "@tremor/react";
import {
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  CalendarDays,
  BarChart2,
  TrendingUp,
  Receipt,
  Bell,
  ChevronRight,
} from "lucide-react";
import Link from "next/link";

import type { AnomalyRead, DashboardSummary, ExploreRow, PeriodSummary } from "@/lib/types";
import { EmptyState } from "@/components/empty-state";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function fmtCost(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(2)}`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// SparklineChart — tiny Recharts line used inside KPI cards
// ---------------------------------------------------------------------------

function SparklineChart({ data, up }: { data: number[]; up: boolean | null }) {
  if (data.length < 2) return null;
  const color = up === null ? "#94a3b8" : up ? "#ef4444" : "#10b981";
  const chartData = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// DeltaBadge — color-coded ±% pill under each KPI number
// ---------------------------------------------------------------------------

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="text-xs text-muted-foreground">No prior data</span>;
  }
  const up = pct > 0;
  const neutral = pct === 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${
        neutral
          ? "bg-muted text-muted-foreground"
          : up
            ? "bg-red-50 text-red-600 dark:bg-red-950/30 dark:text-red-400"
            : "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400"
      }`}
    >
      {neutral ? "=" : up ? "↑" : "↓"}&nbsp;{Math.abs(pct).toFixed(1)}% vs prior
    </span>
  );
}

// ---------------------------------------------------------------------------
// DashboardStatCards — four cost-period cards with sparklines + delta badges
// ---------------------------------------------------------------------------

interface StatCardsProps {
  periods: DashboardSummary;
  sparklines: {
    day: number[];
    week: number[];
    month: number[];
    mtd: number[];
  };
  budgetStatus: "healthy" | "warning" | "over";
}

interface CardDef {
  key: keyof Pick<DashboardSummary, "day" | "week" | "month" | "mtd">;
  icon: React.ElementType;
  defaultIconColor: string;
  defaultIconBg: string;
  sparklineKey: keyof StatCardsProps["sparklines"];
}

const CARD_DEFS: CardDef[] = [
  {
    key: "day",
    icon: CalendarDays,
    defaultIconColor: "text-slate-500 dark:text-slate-400",
    defaultIconBg: "bg-slate-100 dark:bg-slate-800",
    sparklineKey: "day",
  },
  {
    key: "week",
    icon: BarChart2,
    defaultIconColor: "text-blue-600 dark:text-blue-400",
    defaultIconBg: "bg-blue-50 dark:bg-blue-950/60",
    sparklineKey: "week",
  },
  {
    key: "month",
    icon: TrendingUp,
    defaultIconColor: "text-violet-600 dark:text-violet-400",
    defaultIconBg: "bg-violet-50 dark:bg-violet-950/60",
    sparklineKey: "month",
  },
  {
    key: "mtd",
    icon: Receipt,
    defaultIconColor: "text-emerald-600 dark:text-emerald-400",
    defaultIconBg: "bg-emerald-50 dark:bg-emerald-950/60",
    sparklineKey: "mtd",
  },
];

const BUDGET_ICON: Record<
  "healthy" | "warning" | "over",
  { iconColor: string; iconBg: string }
> = {
  healthy: {
    iconColor: "text-emerald-600 dark:text-emerald-400",
    iconBg: "bg-emerald-50 dark:bg-emerald-950/60",
  },
  warning: {
    iconColor: "text-amber-600 dark:text-amber-400",
    iconBg: "bg-amber-50 dark:bg-amber-950/60",
  },
  over: {
    iconColor: "text-red-600 dark:text-red-400",
    iconBg: "bg-red-50 dark:bg-red-950/60",
  },
};

function SingleStatCard({
  period,
  icon: Icon,
  iconColor,
  iconBg,
  sparkline,
  budgetDot,
}: {
  period: PeriodSummary;
  icon: React.ElementType;
  iconColor: string;
  iconBg: string;
  sparkline: number[];
  budgetDot?: "healthy" | "warning" | "over";
}) {
  const up = period.pct_change === null ? null : period.pct_change > 0;

  return (
    <div className="flex flex-col rounded-xl border border-border/60 bg-card p-6 shadow-card transition-shadow duration-200 hover:shadow-card-hover">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              {period.period_label}
            </p>
            {budgetDot && budgetDot !== "healthy" && (
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  budgetDot === "over" ? "bg-red-500" : "bg-amber-400"
                }`}
              />
            )}
          </div>
          {/* Primary KPI number — large, bold, monospace */}
          <p className="mt-3 text-3xl font-bold tracking-tight text-mono">
            {fmtCost(period.total_cost_usd)}
          </p>
          <div className="mt-2">
            <DeltaBadge pct={period.pct_change} />
          </div>
        </div>
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${iconBg}`}
        >
          <Icon className={`h-5 w-5 ${iconColor}`} strokeWidth={1.75} />
        </div>
      </div>
      {/* Sparkline — only renders when ≥2 data points exist */}
      <div className="mt-4">
        <SparklineChart data={sparkline} up={up} />
      </div>
    </div>
  );
}

export function DashboardStatCards({ periods, sparklines, budgetStatus }: StatCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {CARD_DEFS.map((def) => {
        const isMtd = def.key === "mtd";
        const { iconColor, iconBg } = isMtd
          ? BUDGET_ICON[budgetStatus]
          : { iconColor: def.defaultIconColor, iconBg: def.defaultIconBg };

        return (
          <SingleStatCard
            key={def.key}
            period={periods[def.key]}
            icon={def.icon}
            iconColor={iconColor}
            iconBg={iconBg}
            sparkline={sparklines[def.sparklineKey]}
            budgetDot={isMtd ? budgetStatus : undefined}
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProviderDonut — Recharts PieChart for spend-by-provider breakdown
// ---------------------------------------------------------------------------

const PROVIDER_COLORS: Record<string, string> = {
  openai: "#10b981",    // emerald-500
  anthropic: "#8b5cf6", // violet-500
  gemini: "#f59e0b",    // amber-500
};
const FALLBACK_COLOR = "#94a3b8"; // slate-400

export function ProviderDonut({ rows }: { rows: ExploreRow[] }) {
  const chartData = rows
    .filter((r) => parseFloat(r.total_cost_usd) > 0)
    .map((r) => ({
      name: r.group_key || "Unknown",
      value: parseFloat(r.total_cost_usd),
      pct: r.pct_of_total,
    }));

  if (chartData.length === 0) {
    return (
      <div className="flex h-[180px] items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No provider data yet.</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={190}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="45%"
          innerRadius={52}
          outerRadius={76}
          paddingAngle={3}
          dataKey="value"
          isAnimationActive={false}
        >
          {chartData.map((entry, i) => (
            <Cell
              key={i}
              fill={PROVIDER_COLORS[entry.name.toLowerCase()] ?? FALLBACK_COLOR}
            />
          ))}
        </Pie>
        <Tooltip
          formatter={(value: number) => [`$${value.toFixed(2)}`, "Cost"]}
          contentStyle={{ fontSize: "12px", borderRadius: "8px" }}
        />
        <Legend
          iconSize={8}
          iconType="circle"
          formatter={(name: string) => name.charAt(0).toUpperCase() + name.slice(1)}
          wrapperStyle={{ fontSize: "12px" }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// SpendTrendChart — 30d / 7d / 90d area chart (just the chart, card in page.tsx)
// ---------------------------------------------------------------------------

// Pivot row shape expected by Tremor: { date: string, [model]: number }
export type ChartRow = Record<string, string | number>;

const costFormatter = (value: number) =>
  value === 0 ? "$0" : value < 0.01 ? `$${value.toFixed(6)}` : `$${value.toFixed(2)}`;

/**
 * Shorten raw model+token-type labels so they fit in the chart legend.
 * e.g. "gpt-4o-2024-08-06, cached input" → "gpt-4o · cached input"
 *      "claude-3-5-haiku-20241022, output" → "claude-3-5-haiku · output"
 */
function shortenModelLabel(label: string): string {
  const commaIdx = label.indexOf(", ");
  if (commaIdx === -1) {
    // No token type — just strip trailing date suffixes
    return label
      .replace(/-\d{8}$/, "")          // strip -20241022
      .replace(/-\d{4}-\d{2}-\d{2}$/, ""); // strip -2024-08-06
  }
  const model = label.slice(0, commaIdx);
  const tokenType = label.slice(commaIdx + 2);
  const shortModel = model
    .replace(/-\d{8}$/, "")            // strip -20241022
    .replace(/-\d{4}-\d{2}-\d{2}$/, "") // strip -2024-08-06
    .replace(/-\d{4}$/, "");            // strip trailing -2024
  return `${shortModel} · ${tokenType}`;
}

interface SpendTrendProps {
  chartData: ChartRow[];
  models: string[];
}

export function SpendTrendChart({ chartData, models }: SpendTrendProps) {
  if (chartData.length === 0) {
    return (
      <div className="flex h-60 items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No data for this period.</p>
      </div>
    );
  }

  // Map raw model keys → shortened display labels. Tremor uses the category
  // string as both the data key and the legend text, so we must rename the keys
  // in the data rows to avoid long strings overflowing the legend / tooltip.
  const labelMap = new Map(models.map((m) => [m, shortenModelLabel(m)]));
  const shortLabels = models.map((m) => labelMap.get(m) ?? m);
  const renamedData: ChartRow[] = chartData.map((row) => {
    const newRow: ChartRow = { date: row.date as string };
    for (const m of models) {
      newRow[labelMap.get(m) ?? m] = (row[m] as number) ?? 0;
    }
    return newRow;
  });

  return (
    <AreaChart
      data={renamedData}
      index="date"
      categories={shortLabels}
      valueFormatter={costFormatter}
      className="h-72"
      showLegend={models.length > 1}
      showGridLines
      curveType="monotone"
    />
  );
}

// ---------------------------------------------------------------------------
// TopModelsChart — top-10 horizontal bar chart (just the chart)
// ---------------------------------------------------------------------------

interface BarRow {
  model: string;
  cost: number;
}

interface TopModelsProps {
  barData: BarRow[];
}

const costBarFormatter = (value: number) => `$${value.toFixed(2)}`;

export function TopModelsChart({ barData }: TopModelsProps) {
  if (barData.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No model data for this period.</p>
      </div>
    );
  }
  return (
    <BarChart
      data={barData}
      index="model"
      categories={["cost"]}
      valueFormatter={costBarFormatter}
      layout="vertical"
      style={{ height: `${Math.max(180, barData.length * 44)}px` }}
      showLegend={false}
      yAxisWidth={180}
    />
  );
}

// ---------------------------------------------------------------------------
// RecentAlertsWidget — last 5 open anomalies with severity color coding
// ---------------------------------------------------------------------------

interface AlertsProps {
  anomalies: AnomalyRead[];
}

const SEVERITY_CONFIG: Record<
  AnomalyRead["severity"],
  { borderColor: string; dotColor: string }
> = {
  high: {
    borderColor: "border-l-red-500",
    dotColor: "bg-red-500",
  },
  medium: {
    borderColor: "border-l-amber-500",
    dotColor: "bg-amber-500",
  },
  low: {
    borderColor: "border-l-sky-500",
    dotColor: "bg-sky-500",
  },
};

export function RecentAlertsWidget({ anomalies }: AlertsProps) {
  const openAlerts = anomalies.filter((a) => a.status === "open").slice(0, 5);

  return (
    <div className="flex flex-col rounded-xl border border-border/60 bg-card p-6 shadow-card">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Recent alerts</h2>
          <p className="text-xs text-muted-foreground">Open anomalies and budget warnings</p>
        </div>
        {openAlerts.length > 0 && (
          <span className="rounded-full bg-critical-subtle px-2 py-0.5 text-xs font-medium text-critical">
            {openAlerts.length} open
          </span>
        )}
      </div>

      {openAlerts.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center">
          <EmptyState
            icon={Bell}
            title="All clear"
            description="No open alerts right now."
            className="py-4"
          />
        </div>
      ) : (
        <>
          <div className="flex-1 space-y-2">
            {openAlerts.map((alert) => {
              const cfg = SEVERITY_CONFIG[alert.severity];
              const spike = alert.spike_pct.toFixed(0);
              const baseline = parseFloat(alert.baseline_usd).toFixed(2);
              const actual = parseFloat(alert.actual_usd).toFixed(2);
              return (
                <div
                  key={alert.id}
                  className={`flex items-start gap-3 rounded-lg border-l-4 bg-muted/30 px-3 py-2.5 ${cfg.borderColor}`}
                >
                  <div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${cfg.dotColor}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-foreground capitalize">
                      {alert.scope_kind.replace("_", " ")}
                      {alert.scope_value ? ` · ${alert.scope_value}` : ""}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {alert.explanation ??
                        `↑ ${spike}% vs baseline ($${baseline} → $${actual})`}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {timeAgo(alert.detected_at)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
          <Link
            href="/anomalies"
            className="mt-4 flex items-center gap-1 text-xs font-medium text-primary transition-colors duration-150 hover:text-primary/80"
          >
            View all alerts
            <ChevronRight className="h-3 w-3" />
          </Link>
        </>
      )}
    </div>
  );
}
