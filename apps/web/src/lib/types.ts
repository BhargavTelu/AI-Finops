// Shared TypeScript types matching FastAPI Pydantic schemas.
// Decimal fields are serialised as strings over JSON — parse with Number() or parseFloat() when needed.

export interface IntegrationRead {
  id: string;
  org_id: string;
  provider: "openai" | "anthropic" | "gemini";
  display_name: string;
  status: "active" | "error" | "revoked";
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface UsageSummary {
  total_cost_usd: string; // Decimal → string
  total_requests: number;
  total_tokens: number;
  period_start: string; // date → ISO string
  period_end: string;
}

export interface DailyPoint {
  day: string; // date → ISO string
  cost_usd: string; // Decimal → string
  requests: number;
  group_key: string; // model name (or tag value in future)
}

export interface ExploreRow {
  group_key: string;
  total_cost_usd: string; // Decimal → string
  total_requests: number;
  total_tokens: number;
  pct_of_total: number; // 0–100
}

export type TagType = "feature" | "team" | "customer" | "env";
export type MatchType = "regex" | "substring" | "exact";

export interface Tag {
  id: string;
  org_id: string;
  type: TagType;
  name: string;
  color: string | null;
}

export interface TagRule {
  id: string;
  org_id: string;
  tag_id: string;
  match_type: MatchType;
  match_pattern: string;
  priority: number;
  enabled: boolean;
  tags?: { type: string; name: string } | null; // joined tag info from GET /tag-rules
}

export interface PreviewMatch {
  api_key_label: string;
  provider: string;
  model: string;
}
