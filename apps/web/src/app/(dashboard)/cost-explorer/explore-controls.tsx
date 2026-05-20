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

interface Props {
  groupBy: string;
  range: string;
  provider: string;
}

const selectClass =
  "rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";

export function ExploreControls({ groupBy, range, provider }: Props) {
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

      {provider && (
        <div className="flex items-center gap-1.5 rounded-full border bg-accent px-3 py-1 text-sm">
          <span className="text-muted-foreground">Provider:</span>
          <span className="font-medium">{provider}</span>
          <button
            onClick={() => update("provider", "")}
            className="ml-1 text-muted-foreground hover:text-foreground"
            aria-label="Remove provider filter"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
