"use client";

import { useRouter, useSearchParams } from "next/navigation";

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

// Dimensions that can carry an active filter badge
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
  "rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";

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

  const activeBadges = Object.entries(FILTER_DIMENSIONS).filter(
    ([dim]) => activeFilters[dim],
  );

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Group by</span>
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
      </label>

      <label className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Period</span>
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
      </label>

      {activeBadges.map(([dim, label]) => (
        <div
          key={dim}
          className="flex items-center gap-1.5 rounded-full border bg-accent px-3 py-1 text-sm"
        >
          <span className="text-muted-foreground">{label}:</span>
          <span className="font-medium">{activeFilters[dim]}</span>
          <button
            onClick={() => update(dim, "")}
            className="ml-1 text-muted-foreground hover:text-foreground"
            aria-label={`Remove ${label} filter`}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
