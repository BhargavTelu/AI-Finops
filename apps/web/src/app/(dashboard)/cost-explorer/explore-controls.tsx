"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { X, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";

const GROUP_BY_OPTIONS = [
  { value: "model", label: "Model" },
  { value: "provider", label: "Provider" },
  { value: "feature_tag", label: "Feature Tag" },
  { value: "team_tag", label: "Team Tag" },
  { value: "customer_tag", label: "Customer Tag" },
  { value: "env_tag", label: "Env Tag" },
] as const;

const RANGE_OPTIONS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
] as const;

// Dimension filter badges - these appear when a row drill-down is active
const FILTER_DIMENSIONS: Record<string, string> = {
  provider: "Provider",
  model: "Model",
  feature_tag: "Feature",
  team_tag: "Team",
  customer_tag: "Customer",
  env_tag: "Env",
};

interface Props {
  groupBy: string;
  range: string;
  activeFilters: Record<string, string>;
}

const selectClass =
  "h-9 rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground shadow-sm transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 hover:border-ring/50";

export function ExploreControls({ groupBy, range, activeFilters }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function update(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    router.push(`/cost-explorer?${params.toString()}`);
  }

  function resetFilters() {
    const params = new URLSearchParams();
    params.set("group_by", groupBy);
    params.set("range", range);
    router.push(`/cost-explorer?${params.toString()}`);
  }

  const activeBadges = Object.entries(FILTER_DIMENSIONS).filter(
    ([dim]) => activeFilters[dim],
  );
  const activeFilterCount = activeBadges.length;

  return (
    <div className="flex flex-col gap-3">
      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Group by</span>
          <select
            className={selectClass}
            value={groupBy}
            onChange={(e) => update("group_by", e.target.value)}
          >
            {GROUP_BY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Period</span>
          <select
            className={selectClass}
            value={range}
            onChange={(e) => update("range", e.target.value)}
          >
            {RANGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* Reset button - only shown when dimension filters are active */}
        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={resetFilters}
            className="h-9 gap-1.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
            Reset filters
            <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
              {activeFilterCount}
            </span>
          </Button>
        )}
      </div>

      {/* Active dimension filter badges */}
      {activeBadges.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Filtered by:</span>
          {activeBadges.map(([dim, label]) => (
            <div
              key={dim}
              className="flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-3 py-1 text-xs"
            >
              <span className="text-muted-foreground">{label}:</span>
              <span className="font-semibold text-foreground">{activeFilters[dim]}</span>
              <button
                onClick={() => update(dim, "")}
                className="ml-0.5 rounded-full p-0.5 text-muted-foreground transition-colors duration-150 hover:bg-background hover:text-foreground"
                aria-label={`Remove ${label} filter`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
