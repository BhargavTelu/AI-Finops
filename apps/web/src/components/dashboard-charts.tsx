"use client";

import { useEffect, useState } from "react";
import {
  AreaChart,
} from "@tremor/react";
import {
  Area,
  AreaChart as RechartsAreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  ChevronRight,
} from "lucide-react";
import { animate, useReducedMotion } from "framer-motion";
import Link from "next/link";

import type {
  AnomalyRead,
  DashboardSummary,
  ExploreRow,
  ForecastResult,
  PeriodSummary,
} from "@/lib/types";
import { EmptyState } from "@/components/empty-state";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

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

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Concrete CSS color strings for Recharts SVG fills - resolved from the
// chart token palette so every chart follows the same series order.
const CHART = {
  1: "hsl(var(--chart-1))",
  2: "hsl(var(--chart-2))",
  3: "hsl(var(--chart-3))",
  4: "hsl(var(--chart-4))",
  5: "hsl(var(--chart-5))",
  6: "hsl(var(--chart-6))",
} as const;

const TOOLTIP_STYLE: React.CSSProperties = {
  fontSize: "12px",
  borderRadius: "8px",
  border: "none",
  backgroundColor: "hsl(var(--popover))",
  color: "hsl(var(--popover-foreground))",
  boxShadow: "var(--shadow-overlay)",
  padding: "8px 12px",
};

// ---------------------------------------------------------------------------
// CountUpValue - animates a financial figure from 0 on mount.
// SSR renders the final value (no hydration mismatch); the count-up only
// plays client-side and is skipped entirely under prefers-reduced-motion.
// ---------------------------------------------------------------------------

function CountUpValue({ value }: { value: number }) {
  const reduceMotion = useReducedMotion();
  const [display, setDisplay] = useState(() => fmtCost(value));

  useEffect(() => {
    if (reduceMotion || value === 0 || value < 0.01) {
      setDisplay(fmtCost(value));
      return;
    }
    const controls = animate(0, value, {
      duration: 0.7,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(fmtCost(v)),
    });
    return () => controls.stop();
  }, [value, reduceMotion]);

  return <span className="tabular">{display}</span>;
}

// ---------------------------------------------------------------------------
// SparklineChart - gradient area under each KPI number
// ---------------------------------------------------------------------------

function SparklineChart({
  data,
  up,
  gradientId,
}: {
  data: number[];
  up: boolean | null;
  gradientId: string;
}) {
  if (data.length < 2) return null;
  // Cost rising = critical tone, falling = success, flat/unknown = neutral
  const color =
    up === null ? CHART[6] : up ? "hsl(var(--critical))" : "hsl(var(--success))";
  const chartData = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={36}>
      <RechartsAreaChart data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#${gradientId})`}
          dot={false}
          isAnimationActive={false}
        />
      </RechartsAreaChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// DeltaBadge - color-coded ±% pill under each KPI number
// ---------------------------------------------------------------------------

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="text-xs text-muted-foreground">No prior data</span>;
  }
  const up = pct > 0;
  const neutral = pct === 0;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular ${
        neutral
          ? "bg-muted text-muted-foreground"
          : up
            ? "bg-critical-subtle text-critical"
            : "bg-success-subtle text-success"
      }`}
    >
      {!neutral &&
        (up ? (
          <ArrowUpRight className="h-3 w-3" aria-hidden />
        ) : (
          <ArrowDownRight className="h-3 w-3" aria-hidden />
        ))}
      {Math.abs(pct).toFixed(1)}% vs prior
    </span>
  );
}

// ---------------------------------------------------------------------------
// DashboardStatCards - four cost-period cards with sparklines + delta badges
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
  forecast?: ForecastResult | null;
}

const CARD_KEYS = ["day", "week", "month", "mtd"] as const;

function SingleStatCard({
  period,
  sparkline,
  gradientId,
  budgetDot,
}: {
  period: PeriodSummary;
  sparkline: number[];
  gradientId: string;
  budgetDot?: "healthy" | "warning" | "over";
}) {
  const up = period.pct_change === null ? null : period.pct_change > 0;

  return (
    <div className="flex flex-col rounded-xl bg-card p-6 shadow-card transition-shadow duration-200 hover:shadow-card-hover">
      <div className="flex items-center gap-1.5">
        <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          {period.period_label}
        </p>
        {budgetDot && budgetDot !== "healthy" && (
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              budgetDot === "over" ? "bg-critical" : "bg-warning"
            }`}
            role="img"
            aria-label={budgetDot === "over" ? "Over budget" : "Approaching budget limit"}
          />
        )}
      </div>
      {/* Primary KPI number - large display figure, tabular digits */}
      <p className="mt-3 text-3xl font-semibold tracking-tight text-foreground">
        <CountUpValue value={parseFloat(String(period.total_cost_usd))} />
      </p>
      <div className="mt-2">
        <DeltaBadge pct={period.pct_change} />
      </div>
      {/* Sparkline - only renders when ≥2 data points exist */}
      <div className="mt-4">
        <SparklineChart data={sparkline} up={up} gradientId={gradientId} />
      </div>
    </div>
  );
}

function ForecastStatCard({ forecast }: { forecast: ForecastResult }) {
  const fmt = (raw: string) =>
    parseFloat(raw).toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    });

  return (
    <div className="flex flex-col rounded-xl bg-card p-6 shadow-card transition-shadow duration-200 hover:shadow-card-hover">
      <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
        Projected month-end
      </p>
      <p className="mt-3 text-3xl font-semibold tracking-tight text-foreground">
        <CountUpValue value={parseFloat(forecast.projected_month_end_usd)} />
      </p>
      <div className="mt-2">
        <DeltaBadge pct={forecast.delta_vs_last_month_pct} />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Range {fmt(forecast.confidence_low)} &ndash; {fmt(forecast.confidence_high)}
        {forecast.method === "trailing_30d_average" && " · based on trailing 30d"}
      </p>
    </div>
  );
}

export function DashboardStatCards({ periods, sparklines, budgetStatus, forecast }: StatCardsProps) {
  return (
    <div
      className={
        forecast
          ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
          : "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      }
    >
      {CARD_KEYS.map((key) => (
        <SingleStatCard
          key={key}
          period={periods[key]}
          sparkline={sparklines[key]}
          gradientId={`kpi-spark-${key}`}
          budgetDot={key === "mtd" ? budgetStatus : undefined}
        />
      ))}
      {forecast && <ForecastStatCard forecast={forecast} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProviderDonut - Recharts PieChart with center total for spend-by-provider
// ---------------------------------------------------------------------------

const PROVIDER_COLORS: Record<string, string> = {
  openai: CHART[3],    // teal
  anthropic: CHART[2], // violet
  gemini: CHART[4],    // amber
};

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

  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  return (
    <div>
      <div className="relative">
        <ResponsiveContainer width="100%" height={176}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={58}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
              strokeWidth={0}
              isAnimationActive
              animationDuration={600}
            >
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={
                    PROVIDER_COLORS[entry.name.toLowerCase()] ??
                    CHART[((i % 6) + 1) as 1 | 2 | 3 | 4 | 5 | 6]
                  }
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number) => [fmtCost(value), "Cost"]}
              contentStyle={TOOLTIP_STYLE}
              itemStyle={{ color: "hsl(var(--popover-foreground))" }}
              labelStyle={{ color: "hsl(var(--muted-foreground))" }}
            />
          </PieChart>
        </ResponsiveContainer>
        {/* Center total - the one number a CFO scans for */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <p className="text-lg font-semibold tracking-tight text-foreground tabular">
            {fmtCost(total)}
          </p>
          <p className="text-[11px] text-muted-foreground">total</p>
        </div>
      </div>
      {/* Legend with exact amounts - color is never the only signal */}
      <ul className="mt-3 space-y-1.5">
        {chartData.map((entry, i) => (
          <li key={entry.name} className="flex items-center gap-2 text-xs">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{
                backgroundColor:
                  PROVIDER_COLORS[entry.name.toLowerCase()] ??
                  CHART[((i % 6) + 1) as 1 | 2 | 3 | 4 | 5 | 6],
              }}
              aria-hidden
            />
            <span className="capitalize text-muted-foreground">{entry.name}</span>
            <span className="ml-auto font-medium text-foreground text-mono">
              {fmtCost(entry.value)}
            </span>
            <span className="w-10 text-right text-muted-foreground text-mono">
              {entry.pct.toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SpendTrendChart - 30d / 7d / 90d area chart (just the chart, card in page.tsx)
// ---------------------------------------------------------------------------

// Pivot row shape expected by Tremor: { date: string, [model]: number }
export type ChartRow = Record<string, string | number>;

// Tremor takes named palette colors; this order mirrors --chart-1..6
const TREMOR_SERIES_COLORS = ["blue", "violet", "teal", "amber", "rose", "slate", "cyan", "indigo", "fuchsia", "lime"];

const costFormatter = (value: number) =>
  value === 0 ? "$0" : value < 0.01 ? `$${value.toFixed(6)}` : usd.format(value);

// Custom tooltip for the Tremor AreaChart - uses design tokens so it works in
// both light and dark mode and stays visually consistent with the card surface.
interface SpendTooltipEntry {
  name?: string;
  category?: string;
  value: number;
  color: string;
}
interface SpendTooltipProps {
  payload: SpendTooltipEntry[] | undefined;
  active: boolean | undefined;
  label: string;
}

function SpendTrendTooltip({ payload, active, label }: SpendTooltipProps) {
  if (!active || !payload?.length) return null;
  const nonZero = payload.filter((e) => e.value > 0);
  if (nonZero.length === 0) return null;
  const total = nonZero.reduce((sum, e) => sum + e.value, 0);
  return (
    <div
      className="rounded-lg bg-popover px-3 py-2.5 shadow-overlay"
      style={{ minWidth: "170px", maxWidth: "260px" }}
    >
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <p className="text-xs font-semibold text-popover-foreground">{label}</p>
        {nonZero.length > 1 && (
          <p className="text-xs font-medium text-muted-foreground text-mono">
            {costFormatter(total)}
          </p>
        )}
      </div>
      <div className="space-y-1">
        {nonZero.map((entry) => {
          const key = entry.name ?? entry.category ?? "";
          return (
            <div key={key} className="flex items-center gap-2 text-xs">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="max-w-[120px] truncate text-muted-foreground">{key}</span>
              <span className="ml-auto pl-2 text-mono font-medium text-popover-foreground">
                {costFormatter(entry.value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Shorten raw model+token-type labels so they fit in the chart legend.
 * e.g. "gpt-4o-2024-08-06, cached input" → "gpt-4o · cached input"
 *      "claude-3-5-haiku-20241022, output" → "claude-3-5-haiku · output"
 */
function shortenModelLabel(label: string): string {
  const commaIdx = label.indexOf(", ");
  if (commaIdx === -1) {
    // No token type - just strip trailing date suffixes
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
      colors={TREMOR_SERIES_COLORS}
      valueFormatter={costFormatter}
      className="h-72"
      showLegend={models.length > 1}
      showGridLines
      curveType="monotone"
      // `any` cast: Tremor types customTooltip more narrowly than the props
      // it actually passes at runtime; our tooltip needs the extra fields.
      customTooltip={SpendTrendTooltip as any}
    />
  );
}

// ---------------------------------------------------------------------------
// TopModelsChart - top-10 horizontal bar chart (just the chart)
// ---------------------------------------------------------------------------

interface BarRow {
  model: string;
  cost: number;
}

interface TopModelsProps {
  barData: BarRow[];
}

export function TopModelsChart({ barData }: TopModelsProps) {
  if (barData.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No model data for this period.</p>
      </div>
    );
  }
  const chartHeight = Math.max(200, barData.length * 44);
  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart
        data={barData}
        layout="vertical"
        margin={{ top: 4, right: 52, left: 0, bottom: 4 }}
      >
        <XAxis
          type="number"
          tickFormatter={(v: number) => `$${v.toFixed(2)}`}
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="model"
          width={176}
          tick={{ fontSize: 12, fill: "hsl(var(--foreground))" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: "hsl(var(--muted))", opacity: 0.4 }}
          formatter={(value: number) => [fmtCost(value), "Cost"]}
          contentStyle={TOOLTIP_STYLE}
          itemStyle={{ color: "hsl(var(--popover-foreground))" }}
          labelStyle={{ fontWeight: 600, color: "hsl(var(--popover-foreground))" }}
        />
        <Bar
          dataKey="cost"
          fill={CHART[1]}
          radius={[0, 4, 4, 0]}
          maxBarSize={28}
          background={{ fill: "hsl(var(--muted))", opacity: 0.35, radius: 4 }}
          isAnimationActive
          animationDuration={600}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// RecentAlertsWidget - last 5 open anomalies with severity color coding
// ---------------------------------------------------------------------------

interface AlertsProps {
  anomalies: AnomalyRead[];
}

const SEVERITY_CONFIG: Record<
  AnomalyRead["severity"],
  { borderColor: string; dotColor: string }
> = {
  high: {
    borderColor: "border-l-critical",
    dotColor: "bg-critical",
  },
  medium: {
    borderColor: "border-l-warning",
    dotColor: "bg-warning",
  },
  low: {
    borderColor: "border-l-info",
    dotColor: "bg-info",
  },
};

export function RecentAlertsWidget({ anomalies }: AlertsProps) {
  const openAlerts = anomalies.filter((a) => a.status === "open").slice(0, 5);

  return (
    <div className="flex flex-col rounded-xl bg-card p-6 shadow-card">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Recent alerts</h2>
          <p className="text-xs text-muted-foreground">Open anomalies and budget warnings</p>
        </div>
        {openAlerts.length > 0 && (
          <span className="rounded-full bg-critical-subtle px-2 py-0.5 text-xs font-medium text-critical tabular">
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
                  className={`flex items-start gap-3 rounded-lg border-l-4 bg-muted/30 px-3 py-2.5 transition-colors duration-150 hover:bg-muted/50 ${cfg.borderColor}`}
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
                    <p className="mt-1 text-xs text-muted-foreground/80">
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
