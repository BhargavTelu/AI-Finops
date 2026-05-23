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

export interface PeriodSummary {
  total_cost_usd: string; // Decimal → string
  total_requests: number;
  total_tokens: number;
  period_start: string;
  period_end: string;
  period_label: string;
  prev_period_cost_usd: string; // Decimal → string
  pct_change: number | null; // null when prev_period = 0
}

export interface DashboardSummary {
  day: PeriodSummary;
  week: PeriodSummary;
  month: PeriodSummary;
  mtd: PeriodSummary;
  mom_pct_change: number | null;
  last_month_cost_usd: string; // Decimal → string
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

export type BudgetScopeType =
  | "global"
  | "provider"
  | "model"
  | "feature_tag"
  | "team_tag"
  | "customer_tag"
  | "env_tag";

export interface BudgetRead {
  id: string;
  org_id: string;
  scope_type: BudgetScopeType;
  scope_value: string | null;
  monthly_limit: string; // Decimal → string
  alert_at_pct: number;
  hard_cap: boolean;
  created_at: string;
  updated_at: string;
  current_spend_mtd: string; // Decimal → string, computed by API
  spent_pct: number;         // 0–100+
}

export interface SlackStatus {
  connected: boolean;
  workspace_id?: string | null;
  channel_name?: string | null;
  channel_id?: string | null;
  installed_at?: string | null;
}

export interface UsageEventRead {
  id: string;
  provider: string;
  model: string;
  api_key_label: string | null;
  feature_tag: string | null;
  team_tag: string | null;
  customer_tag: string | null;
  env_tag: string | null;
  cost_usd: string; // Decimal → string
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  bucket_hour: string; // ISO datetime
  manual_override: boolean;
}

export type AnomalySeverity = "low" | "medium" | "high";
export type AnomalyStatus = "open" | "acked" | "dismissed";

export interface AnomalyRead {
  id: string;
  org_id: string;
  detected_at: string; // ISO datetime string
  scope_kind: string;
  scope_value: string | null;
  baseline_usd: string; // Decimal → string
  actual_usd: string;   // Decimal → string
  spike_pct: number;
  severity: AnomalySeverity;
  status: AnomalyStatus;
  context: Record<string, unknown> | null;
}
