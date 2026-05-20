"use client";

import { AreaChart, BarChart } from "@tremor/react";

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
