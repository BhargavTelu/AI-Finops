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
