// ─────────────────────────────────────────────────────────────────────────────
// Database row types - matches the schema in infra/migrations/
// Used only in server-side code that queries Supabase directly.
// ─────────────────────────────────────────────────────────────────────────────

export interface UserRow {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
}

export interface OrganizationRow {
  id: string;
  name: string;
  plan: string;
  trial_ends_at: string | null;
  created_at: string;
}

export interface OrganizationMemberRow {
  id: string;
  org_id: string;
  user_id: string;
  role: string;
  created_at: string;
}

export interface IntegrationRow {
  id: string;
  org_id: string;
  provider: string;
  display_name: string;
  api_key_enc: Uint8Array; // never sent to frontend
  status: string;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface DailyCostSummaryRow {
  id: string;
  org_id: string;
  day: string;
  provider: string;
  model: string;
  feature_tag: string;
  team_tag: string;
  customer_tag: string;
  env_tag: string;
  total_cost_usd: string; // numeric comes back as string from pg
  total_requests: string;
  total_tokens: string;
}

export interface BillingRow {
  org_id: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  plan: string;
  status: string;
  current_period_end: string | null;
}
