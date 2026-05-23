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
import { CalendarDays, BarChart2, TrendingUp, Receipt } from "lucide-react";

import type { DashboardSummary, ExploreRow, PeriodSummary } from "@/lib/types";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function fmtCost(raw: string | number): string {
  const n = typeof raw === "string" ? parseFloat(raw) : raw;
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// SparklineChart — tiny Recharts line, no axes, no grid
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
// DeltaBadge — ±% badge below the cost value
// ---------------------------------------------------------------------------

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="text-xs text-muted-foreground">— no prior data</span>;
  }
  const up = pct > 0;
  const neutral = pct === 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${
        neutral
          ? "text-muted-foreground"
          : up
            ? "text-red-600 dark:text-red-400"
            : "text-emerald-600 dark:text-emerald-400"
      }`}
    >
      {neutral ? "=" : up ? "↑" : "↓"}
      {Math.abs(pct).toFixed(1)}% vs prior
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
    defaultIconColor: "text-slate-600 dark:text-slate-400",
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

// Budget-status icon styling overrides (applied to MTD card only)
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
    <div className="flex flex-col rounded-xl border border-border/60 bg-card p-5">
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
          <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">
            {fmtCost(period.total_cost_usd)}
          </p>
          <div className="mt-1">
            <DeltaBadge pct={period.pct_change} />
          </div>
        </div>
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${iconBg}`}>
          <Icon className={`h-4 w-4 ${iconColor}`} strokeWidth={2} />
        </div>
      </div>
      {/* Sparkline — only renders when there are ≥2 data points */}
      <div className="mt-3">
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
// ProviderDonut — Recharts PieChart for spend-by-provider
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
      <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No provider data yet.</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={52}
          outerRadius={78}
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
          contentStyle={{ fontSize: "12px" }}
        />
        <Legend
          iconSize={8}
          iconType="circle"
          formatter={(name: string) =>
            name.charAt(0).toUpperCase() + name.slice(1)
          }
          wrapperStyle={{ fontSize: "12px" }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// DashboardCharts — existing 30d area chart + top-10 bar chart (unchanged)
// ---------------------------------------------------------------------------

// Pivot row shape expected by Tremor: { date: string, [model]: number }
export type ChartRow = Record<string, string | number>;

interface BarRow {
  model: string;
  cost: number;
}

interface Props {
  chartData: ChartRow[];
  models: string[];
  barData: BarRow[];
}

const costFormatter = (value: number) =>
  value === 0 ? "$0" : value < 0.01 ? `$${value.toFixed(6)}` : `$${value.toFixed(4)}`;

const costBarFormatter = (value: number) => `$${value.toFixed(2)}`;

export function DashboardCharts({ chartData, models, barData }: Props) {
  return (
    <div className="space-y-4">
      {/* 30-day cost trend */}
      <div className="rounded-xl border border-border/60 bg-card p-5">
        <div className="mb-4">
          <h2 className="text-sm font-medium">Cost trend</h2>
          <p className="text-xs text-muted-foreground">Daily spend by model over 30 days</p>
        </div>
        {chartData.length === 0 ? (
          <div className="flex h-60 items-center justify-center rounded-lg border border-dashed border-border">
            <p className="text-sm text-muted-foreground">No data for this period.</p>
          </div>
        ) : (
          <AreaChart
            data={chartData}
            index="date"
            categories={models}
            valueFormatter={costFormatter}
            className="h-64"
            showLegend={models.length > 1}
            showGridLines
            curveType="monotone"
          />
        )}
      </div>

      {/* Cost by model */}
      <div className="rounded-xl border border-border/60 bg-card p-5">
        <div className="mb-4">
          <h2 className="text-sm font-medium">Cost by model</h2>
          <p className="text-xs text-muted-foreground">Top 10 models by total spend</p>
        </div>
        {barData.length === 0 ? (
          <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border">
            <p className="text-sm text-muted-foreground">No data for this period.</p>
          </div>
        ) : (
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
        )}
      </div>
    </div>
  );
}
