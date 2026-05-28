// ─────────────────────────────────────────────────────────────────────────────
// API request / response types - mirrors Pydantic schemas in apps/api/src/api/schemas/
// Keep in sync manually until an OpenAPI code-gen step is added.
// ─────────────────────────────────────────────────────────────────────────────

export type Provider = "openai" | "anthropic" | "gemini";
export type IntegrationStatus = "active" | "error" | "revoked";
export type TagType = "feature" | "team" | "customer" | "env";
export type MatchType = "regex" | "substring" | "exact";
export type ScopeType = "global" | "tag" | "model";
export type AnomalySeverity = "low" | "medium" | "high";
export type AnomalyStatus = "open" | "acked" | "dismissed";
export type RecType = "model_swap" | "caching" | "batch" | "other";
export type RecStatus = "new" | "applied" | "dismissed";

// ── Integrations ──────────────────────────────────────────────────────────────
export interface Integration {
  id: string;
  orgId: string;
  provider: Provider;
  displayName: string;
  status: IntegrationStatus;
  lastSyncedAt: string | null;
  lastError: string | null;
  createdAt: string;
}

export interface CreateIntegrationBody {
  provider: Provider;
  displayName: string;
  apiKey: string; // cleared from client immediately after POST
}

// ── Usage ─────────────────────────────────────────────────────────────────────
export interface UsageSummary {
  totalCostUsd: number;
  totalRequests: number;
  totalTokens: number;
  periodStart: string;
  periodEnd: string;
}

export interface DailyPoint {
  day: string;
  costUsd: number;
  requests: number;
  groupKey: string;
}

export interface ForecastResult {
  projectedMonthEndUsd: number;
  confidenceLow: number;
  confidenceHigh: number;
  asOf: string;
}

// ── Tags ──────────────────────────────────────────────────────────────────────
export interface Tag {
  id: string;
  orgId: string;
  type: TagType;
  name: string;
  color: string | null;
}

export interface TagRule {
  id: string;
  orgId: string;
  tagId: string;
  matchType: MatchType;
  matchPattern: string;
  priority: number;
  enabled: boolean;
}

// ── Budgets ───────────────────────────────────────────────────────────────────
export interface Budget {
  id: string;
  orgId: string;
  scopeType: ScopeType;
  scopeValue: string | null;
  monthlyLimit: number;
  alertAtPct: number;
  hardCap: boolean;
}

// ── Anomalies ─────────────────────────────────────────────────────────────────
export interface Anomaly {
  id: string;
  orgId: string;
  detectedAt: string;
  scopeKind: string;
  scopeValue: string | null;
  baselineUsd: number;
  actualUsd: number;
  spikePct: number;
  severity: AnomalySeverity;
  status: AnomalyStatus;
  context: Record<string, unknown> | null;
}

// ── Recommendations ───────────────────────────────────────────────────────────
export interface Recommendation {
  id: string;
  orgId: string;
  type: RecType;
  title: string;
  description: string;
  projectedSavingsUsd: number | null;
  confidence: number | null;
  evidence: Record<string, unknown> | null;
  status: RecStatus;
  generatedAt: string;
}
