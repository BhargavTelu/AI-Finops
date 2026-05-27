import { auth } from "@clerk/nextjs/server";
import { BarChart3 } from "lucide-react";

import { createApiClient } from "@/lib/api-client";
import type { ExploreRow } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { PageMotion } from "@/components/motion-wrapper";
import { ExploreControls } from "./explore-controls";
import { ExploreTable } from "./explore-table";
import { ExportButton } from "./export-button";

const VALID_GROUP_BY = new Set([
  "provider",
  "model",
  "feature_tag",
  "team_tag",
  "customer_tag",
  "env_tag",
]);

const VALID_RANGE = new Set(["7d", "30d", "90d"]);

const FILTER_DIMS = [
  "provider",
  "model",
  "feature_tag",
  "team_tag",
  "customer_tag",
  "env_tag",
] as const;
type FilterDim = (typeof FILTER_DIMS)[number];
type RawParams = { group_by?: string; range?: string } & Partial<Record<FilterDim, string>>;

function fmtCost(raw: number): string {
  if (raw === 0) return "$0.00";
  if (raw < 0.01) return `$${raw.toFixed(6)}`;
  return `$${raw.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const RANGE_LABELS: Record<string, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
};

export default async function CostExplorerPage({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}) {
  const params = await searchParams;
  const groupBy =
    VALID_GROUP_BY.has(params.group_by ?? "") ? (params.group_by ?? "model") : "model";
  const range = VALID_RANGE.has(params.range ?? "") ? (params.range ?? "30d") : "30d";

  const activeFilters: Record<string, string> = {};
  for (const dim of FILTER_DIMS) {
    const val = params[dim];
    if (val) activeFilters[dim] = val;
  }

  const { getToken } = await auth();
  const token = await getToken();
  const api = createApiClient(token!);

  const qs = new URLSearchParams({ range, group_by: groupBy });
  for (const [dim, val] of Object.entries(activeFilters)) {
    qs.set(dim, val);
  }

  const rows = await api
    .get<ExploreRow[]>(`/usage/explore?${qs.toString()}`)
    .catch(() => [] as ExploreRow[]);

  const grandTotal = rows.reduce((s, r) => s + parseFloat(r.total_cost_usd), 0);

  return (
    <PageMotion>
      <div className="space-y-6">
        {/* Page header */}
        <PageHeader
          title="Cost Explorer"
          description="Break down your LLM spend by provider, model, or tag."
          actions={<ExportButton rows={rows} groupBy={groupBy} />}
        />

        {/* Filter controls */}
        <ExploreControls groupBy={groupBy} range={range} activeFilters={activeFilters} />

        {rows.length === 0 ? (
          Object.keys(activeFilters).length > 0 ? (
            /* Filtered but no results */
            <div className="rounded-xl border border-border/60 bg-card p-12">
              <EmptyState
                icon={BarChart3}
                title="No results match your filters"
                description="Try adjusting or removing your active filters to see more data."
              />
            </div>
          ) : (
            /* No data at all */
            <div className="rounded-xl border border-border/60 bg-card p-12">
              <EmptyState
                icon={BarChart3}
                title="No cost data yet"
                description="Connect an API key to start tracking your LLM spend across models, providers, and tags."
                action={{ label: "Add integration", href: "/settings/integrations" }}
              />
            </div>
          )
        ) : (
          <>
            {/* Summary bar */}
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <p>
                Showing{" "}
                <span className="font-medium text-foreground">{rows.length}</span>{" "}
                {rows.length === 1 ? "row" : "rows"} ·{" "}
                {RANGE_LABELS[range] ?? range} · Total:{" "}
                <span className="text-mono font-semibold text-foreground">
                  {fmtCost(grandTotal)}
                </span>
              </p>
            </div>

            {/* Data table */}
            <ExploreTable rows={rows} groupBy={groupBy} />
          </>
        )}
      </div>
    </PageMotion>
  );
}
