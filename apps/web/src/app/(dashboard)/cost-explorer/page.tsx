import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { createApiClient } from "@/lib/api-client";
import type { ExploreRow } from "@/lib/types";
import { ExploreControls } from "./explore-controls";
import { ExploreTable } from "./explore-table";

const VALID_GROUP_BY = new Set([
  "provider",
  "model",
  "feature_tag",
  "team_tag",
  "customer_tag",
  "env_tag",
]);

const VALID_RANGE = new Set(["7d", "30d", "90d"]);

// Dimension filter params accepted by GET /usage/explore
const FILTER_DIMS = ["provider", "model", "feature_tag", "team_tag", "customer_tag", "env_tag"] as const;
type FilterDim = (typeof FILTER_DIMS)[number];
type RawParams = { group_by?: string; range?: string } & Partial<Record<FilterDim, string>>;

export default async function CostExplorerPage({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}) {
  const params = await searchParams;
  const groupBy = VALID_GROUP_BY.has(params.group_by ?? "") ? (params.group_by ?? "model") : "model";
  const range = VALID_RANGE.has(params.range ?? "") ? (params.range ?? "30d") : "30d";

  // Collect active dimension filters; strip empty strings
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Cost Explorer</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Break down your LLM spend by provider, model, or tag.
        </p>
      </div>

      <ExploreControls groupBy={groupBy} range={range} activeFilters={activeFilters} />

      {rows.length === 0 ? (
        <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
          No spend data for this period.{" "}
          <Link href="/settings/integrations" className="underline hover:text-foreground">
            Connect an integration
          </Link>{" "}
          to start tracking costs.
        </div>
      ) : (
        <ExploreTable rows={rows} groupBy={groupBy} />
      )}
    </div>
  );
}
