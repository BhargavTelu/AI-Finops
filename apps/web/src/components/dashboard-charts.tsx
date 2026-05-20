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
    <div className="space-y-8">
      {/* 30-day cost trend */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-1 text-sm font-medium text-muted-foreground">Cost trend (30 days)</h2>
        {chartData.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">No data for this period.</p>
        ) : (
          <AreaChart
            data={chartData}
            index="date"
            categories={models}
            valueFormatter={costFormatter}
            className="mt-4 h-72"
            showLegend={models.length > 1}
            showGridLines
          />
        )}
      </div>

      {/* Cost by model */}
      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-1 text-sm font-medium text-muted-foreground">Cost by model (30 days)</h2>
        {barData.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">No data for this period.</p>
        ) : (
          <BarChart
            data={barData}
            index="model"
            categories={["cost"]}
            valueFormatter={costBarFormatter}
            layout="vertical"
            className="mt-4"
            style={{ height: `${Math.max(180, barData.length * 44)}px` }}
            showLegend={false}
            yAxisWidth={180}
          />
        )}
      </div>
    </div>
  );
}
