# Architecture - SpendOps AI

Companion to `project_spec.md`. How we build it.

## Stack

| Layer | Choice | Note |
|---|---|---|
| Frontend | Next.js 14 (App Router) + TS + Tailwind + shadcn/ui | Server components for dashboard |
| Charts | Tremor (blocks) + Recharts (custom) | |
| Tables | TanStack Table | Required for Cost Explorer pivot |
| Backend | FastAPI (Python 3.11) | Separate from Next.js - ingestion needs persistent workers |
| Jobs | Celery + Upstash Redis | Python parity with API |
| DB | Supabase Postgres + RLS | ClickHouse only if `usage_events` > 50M rows |
| Auth | Clerk | Multi-tenant orgs built-in |
| Billing | Stripe Checkout + Customer Portal | No custom billing UI |
| Email | Resend | |
| Storage | Cloudflare R2 | PDFs - SigV4 via httpx, no boto3 (`services/storage.py`) |
| PDF | fpdf2 | CFO report rendering - pure Python (WeasyPrint rejected: Pango native deps) |
| AI | Claude Haiku 4.5 | Recs, narratives - capped $0.05/org/day |
| Hosting | Vercel (web) + Railway (api + worker) | |
| Errors | Sentry | |
| Analytics | PostHog | Activation funnel |
| Secrets | Supabase Vault + pgcrypto AES-256-GCM | |

**Infra burn @ 50 customers:** ~$190–245/mo. Revenue $14,950/mo → 98% gross margin.

## Stack decisions (don't relitigate)

- **FastAPI over Next.js API routes:** ingestion needs long-running workers, not serverless.
- **Celery over BullMQ:** single Python stack end-to-end.
- **Clerk over Supabase Auth:** orgs primitive saves 2 weeks.
- **Postgres-only in MVP:** ClickHouse is V1 debt. Read aggregates from `daily_cost_summaries`, never raw `usage_events`, on the dashboard.
- **No GraphQL, no Redux, no microservices, no Kafka.** All premature.
- **No proxy mode in MVP.** Hard rule (saves 3 months + SOC 2).

## Topology

```
Browser ─► Next.js (Vercel) ─► FastAPI (Railway) ─► Supabase Postgres
                                    │                     ▲
                                    └─► Celery Workers ───┘
                                              │
                                              ├─► Provider Admin APIs
                                              ├─► Claude Haiku
                                              ├─► Resend, Slack
                                              └─► Stripe webhooks
```

| Component | Owns |
|---|---|
| Next.js | UI, SSR, Clerk sessions. No DB writes. |
| FastAPI | All business logic + DB writes. No UI. |
| Celery | Ingestion, aggregation, anomaly detection, AI calls, alerts. No HTTP. |
| Postgres | Source of truth. |
| Redis | Queue + short cache (≤1h) + rate-limit counters. |

## Repo

```
/apps
  /web        Next.js
  /api        FastAPI + Celery (shared code)
/packages
  /pricing    versioned pricing.yaml
  /types      shared TS ↔ Pydantic types
/infra
  /migrations Supabase SQL
  /scripts    bootstrap, seed, smoke
```

## DB Schema

UUIDv7 ids · `created_at`/`updated_at` on all tables · UTC timestamps · RLS on every org-scoped table.

```sql
-- IDENTITY (mirrors Clerk)
users (id uuid PK, clerk_id text unique, email text unique, full_name, created_at, updated_at)
organizations (id uuid PK, clerk_id text unique, name, plan text default 'trial', trial_ends_at, created_at, updated_at)
organization_members (id, org_id FK, user_id FK, role text default 'admin', UNIQUE(org_id, user_id))

-- INTEGRATIONS
integrations (
  id uuid PK, org_id FK, provider text,         -- 'openai'|'anthropic'|'gemini'
  display_name, api_key_enc bytea,              -- AES-256-GCM
  status text default 'active',                 -- active|error|revoked
  last_synced_at, last_error,
  UNIQUE(org_id, provider, display_name)
)
INDEX (org_id, status)

-- CORE ANALYTICS (high write)
usage_events (
  id uuid PK, org_id, integration_id FK,
  provider, model, api_key_label,
  feature_tag, team_tag, customer_tag, env_tag, -- denormalized after tag-rule eval
  input_tokens bigint, output_tokens bigint, cached_tokens bigint,
  cost_usd numeric(14,8), request_count int,
  bucket_hour timestamptz,                       -- floor UTC hour
  raw_meta jsonb, ingested_at
)
INDEX (org_id, bucket_hour DESC)
INDEX (org_id, feature_tag, bucket_hour DESC)
INDEX (org_id, model, bucket_hour DESC)

-- READ-OPTIMIZED ROLLUP (dashboard hits this first)
daily_cost_summaries (
  id uuid PK, org_id, day date,
  provider, model, feature_tag, team_tag, customer_tag, env_tag,
  total_cost_usd numeric(14,6), total_requests bigint, total_tokens bigint,
  UNIQUE(org_id, day, provider, model, feature_tag, team_tag, customer_tag, env_tag)
)
INDEX (org_id, day DESC)

-- TAGGING
tags (id, org_id, type, name, color, UNIQUE(org_id, type, name))
tag_rules (id, org_id, tag_id FK, match_type, match_pattern, priority int default 100, enabled bool)
INDEX (org_id, enabled, priority)

-- INTELLIGENCE
budgets (
  id, org_id, scope_type, scope_value,          -- scope_type: global|provider|model|feature_tag|team_tag|customer_tag|env_tag
  monthly_limit numeric(12,2), alert_at_pct int default 80, hard_cap bool, created_by,
  notified_80_at timestamptz,                    -- last time 80% alert sent; NULL = never; guards once-per-month re-send
  notified_100_at timestamptz,                   -- last time 100% alert sent; same guard
  created_at, updated_at
)
anomalies (id, org_id, detected_at, scope_kind, scope_value, baseline_usd, actual_usd, spike_pct, severity, status default 'open', context jsonb, notified_at)
INDEX (org_id, detected_at DESC)
recommendations (id, org_id, type, title, description, projected_savings_usd, confidence, evidence jsonb, status default 'new', generated_at, resolved_at)
INDEX (org_id, status, projected_savings_usd DESC)

-- INTEGRATIONS (3rd party)
slack_integrations (id, org_id unique, workspace_id, channel_id, channel_name, bot_token_enc, installed_by)
billing (org_id PK FK, stripe_customer_id, stripe_subscription_id, plan, status, current_period_end)
reports (id, org_id, type, period_start, period_end, r2_object_key, generated_at)
INDEX (org_id, period_start DESC)
audit_events (id, org_id, actor_user_id, action, target_kind, target_id, metadata jsonb, at)
INDEX (org_id, at DESC)
```

**RLS template (apply everywhere):**
```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
CREATE POLICY <t>_iso ON <t> USING (org_id = (auth.jwt()->>'org_id')::uuid);
```

## API (all `/api/v1/*`, Clerk session except webhooks)

```
# Integrations
POST   /integrations                    add provider key
GET    /integrations                    list
DELETE /integrations/:id                remove
POST   /integrations/:id/test           revalidate + backfill

# Usage
GET    /usage/summary?range=30d         headline numbers
GET    /usage/timeseries?range=30d&group_by=model
GET    /usage/explore                   pivot data
GET    /usage/forecast                  linear projection
# CSV export is client-side (cost-explorer/export-button.tsx) - no server endpoint

# Tags
GET/POST/PATCH/DELETE /tags
GET/POST/PATCH/DELETE /tag-rules
POST   /tag-rules/preview               dry-run

# Budgets · Anomalies · Recs
GET/POST/PATCH/DELETE /budgets
GET    /anomalies?status=open
PATCH  /anomalies/:id                   ack/dismiss
GET    /recommendations?status=new
PATCH  /recommendations/:id             apply/dismiss

# Slack
GET    /slack/status                    connection state (connected, workspace, channel)
POST   /slack/oauth/callback            exchange code → encrypt token → upsert slack_integrations
POST   /slack/disconnect                revoke token (best-effort) + delete row

# Reports
GET    /reports
GET    /reports/:id/download            signed R2 URL
POST   /reports/generate                admin-only

# Billing
POST   /billing/checkout                Stripe session
GET    /billing/portal                  Customer Portal redirect
GET    /billing                         current plan

# Webhooks (no auth, signed)
POST   /api/webhooks/stripe
POST   /api/webhooks/clerk
```

**Conventions:** cursor pagination · Problem+JSON errors · `Idempotency-Key` on creates · FastAPI `require_org()` dep reads Clerk JWT.

## Provider Adapter Pattern

```python
class UsageAdapter(Protocol):
    provider: str
    def validate(self, key: bytes) -> bool: ...
    def fetch_costs(self, key: bytes, start: datetime, end: datetime) -> Iterator[NormalizedUsageEvent]: ...

@dataclass
class NormalizedUsageEvent:
    provider: Literal['openai','anthropic','gemini']
    model: str
    api_key_label: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: Decimal
    request_count: int
    bucket_hour: datetime
    raw_meta: dict
```

**OpenAI:** `GET /v1/organization/costs` + `/v1/organization/usage/completions`. Header `Authorization: Bearer sk-admin-...`. Two-pass cursor pagination: completions first (builds token lookup), costs second (yields events). `bucket_width=1d`, `limit=31` (OpenAI daily bucket max is 31; hourly is 168; minute is 1440). Refresh every 4h.

**Anthropic:** `GET /v1/organizations/usage_report/messages`. Headers: `x-api-key: sk-ant-admin-...`, `anthropic-version: 2023-06-01`, `anthropic-beta: usage-report-2024-07-01`. Cursor pagination via `next_page` token. Cost computed from `pricing.yaml` (per-Mtok rates for input, output, cache-read). `cache_read_input_tokens` mapped to `cached_tokens`; `cache_creation_input_tokens` preserved in `raw_meta`. Standard Admin API - not Enterprise-gated.

**Gemini:** Key validation only (M2). `validate()` hits `GET https://generativelanguage.googleapis.com/v1beta/models?key={api_key}` - 200 = valid. `fetch_costs()` is a no-op generator: AI Studio API keys have no usage-reporting endpoint; Cloud Billing API requires OAuth2/service account (different auth model from simple API keys). Cost collection deferred to V1. Integration status saves as `active` but zero events are inserted.

**Pricing:** prefer provider Cost API values. `pricing.yaml` is fallback + used for Anthropic cost calculation and forecasts. Monthly review.

## Tag-Rule Engine

Pure-function module at `api/services/tag_engine.py`. No DB access - fully unit-testable in isolation.

```python
@dataclass(frozen=True)
class CompiledRule:
    tag_type: str       # "feature" | "team" | "customer" | "env"
    tag_name: str       # value to store, e.g. "chat-v2"
    match_type: str     # "regex" | "substring" | "exact"
    match_pattern: str
    priority: int       # lower = higher priority

def compile_rules(db_rows: list[dict]) -> list[CompiledRule]:
    """Filter disabled, parse PostgREST embedded tag join, sort priority ASC."""

def apply_rules(label: str | None, rules: list[CompiledRule]) -> dict[str, str | None]:
    """Returns {feature_tag, team_tag, customer_tag, env_tag}. First match per type wins.
    Stops early when all 4 types assigned. None/empty label treated as empty string."""
```

**Matching semantics:**
- `exact` - full string equality, case-sensitive
- `substring` - `pattern in label` (Python `in` operator)
- `regex` - `re.search(pattern, label)`; invalid regex returns `False` (no exception propagation)

**Ingestion wire-up:** `_ingest_window()` in `ingestion.py` calls `compile_rules()` once per window (before the event loop), then `apply_rules(event.api_key_label, compiled)` per event. Result dict is spread directly into the `usage_events` row via `**apply_rules(...)`. Tag assignments are denormalized at write time - zero query overhead at read time.

**PostgREST join syntax:** `db.table("tag_rules").select("*, tags(type, name)")` returns `tags: {"type": ..., "name": ...}` embedded in each row. The `compile_rules()` function reads from this embedded key.

## Slack Client Service

Pure-function module at `api/services/slack_client.py`. No heavy SDK - uses `httpx` directly (avoids ~5MB Slack SDK transitive dep chain). All functions raise `ValueError` on API error so Celery can retry.

```python
def exchange_code(code, client_id, client_secret, redirect_uri) -> dict:
    """POST /api/oauth.v2.access → full Slack response dict. ValueError on ok=false."""

def revoke_token(bot_token) -> None:
    """POST /api/auth.revoke. Best-effort - logs warning, does not raise."""

def post_message(bot_token, channel_id, blocks, fallback_text) -> None:
    """POST /api/chat.postMessage. ValueError on ok=false (triggers Celery retry)."""
```

**Bot token storage:** AES-256-GCM encrypted → stored as BYTEA (`\x`-prefixed hex) in `slack_integrations.bot_token_enc`. Same `EncryptionService` used for Admin API keys. Strip `\x` prefix before `bytes.fromhex()` on all decrypt paths.

**Slack alert types:**
- Anomaly alert - Block Kit with severity emoji (🟡 low / 🟠 medium / 🔴 high), spike %, baseline, actual, model name, tag context; dispatched by `detect_org` for severity ≥ medium; `max_retries=3`
- Budget alert - Block Kit with `:warning:` (at threshold) or `:red_circle:` (100%+) header, scope label, limit, MTD spend, % used; best-effort after Resend email; failure does not retry
- Daily digest - Block Kit with date header, yesterday spend, 7d avg, MoM delta, top-3 cost drivers, open anomaly count; idempotency via `slack_digests` table; `max_retries=2`

## Core Flows

### Connect key (TTV critical)
```
User → Web: paste Admin key
Web → API: POST /integrations
API → Provider: validate key (live ping)
API: AES-256-GCM encrypt → store as BYTEA (\x-prefixed hex) → audit_events → enqueue backfill_integration
API → Web: 201 IntegrationRead
Worker (backfill_integration):
  paginate provider (30d) → delete-before-insert usage_events → enqueue aggregate_org
Worker (aggregate_org):
  usage_events → UPSERT daily_cost_summaries
Dashboard: fetches /usage/summary + /usage/timeseries → chart renders
```
Target: chart visible < 5 min for 30-day backfill on $20K/mo org.

**BYTEA storage convention:** Admin keys are stored as `"\\x" + ciphertext.hex()` so PostgREST/Supabase returns them in `\x<hex>` format. All decrypt paths must strip the `\x` prefix before calling `bytes.fromhex()`.

### Nightly pipeline (UTC, per org)
```
00:30  aggregate_usage_events   → upsert daily_cost_summaries              [M1 ✅]
01:00  detect_anomalies         → insert anomalies, enqueue notify          [M3 Group A ✅]
           send_anomaly_alert   → post Block Kit to Slack (severity ≥ med)  [M3 Group C ✅]
02:00  check_budgets            → compare MTD spend to limits, enqueue      [M3 Group B ✅]
           send_budget_alert    → Resend email + best-effort Slack post      [M3 Group B+C ✅]
02:30  generate_recommendations → rule-based recs engine                    [M3 Group D ✅]
09:00  send_daily_digests       → per-org Slack digest (idempotency guard)  [M3 Group C ✅]

Monthly (1st, 06:00 UTC):
       generate_monthly_reports → CFO PDF per org: build data → fpdf2 →     [Phase 1 ✅]
                                  R2 upload → reports row → Resend email
```

### Slack digest (09:00 UTC) ✅ [M3 Group C complete]
```
send_daily_digests()           → fan-out: one send_slack_digest.delay per org
send_slack_digest(org_id)      → idempotency check (slack_digests UNIQUE org_id+date)
_fetch_digest_data()           → 4 DB queries: yesterday+7d avg+top drivers | MTD | last-month | open anomalies
_digest_slack_blocks()         → Block Kit: header, spend fields, MoM delta, top-3 drivers, anomaly count
post_message()                 → chat.postMessage (httpx, no SDK)
INSERT slack_digests           → idempotency record (prevents duplicate on Celery retry)
```

### Stripe lifecycle
```
User → POST /billing/checkout → Stripe session URL → user pays → redirect /billing/success
(parallel) Stripe → webhook /api/webhooks/stripe → verify sig → upsert billing row
```

## Anomaly Algorithm

```python
def detect_anomalies(org_id, today):
    for group in iter_groups(org_id, today):    # (model, feature_tag, team_tag, customer_tag)
        history = daily_costs(org_id, group, days=14)
        if len(history) < 14: continue
        rolling = history[-8:-1]                 # last 7 excluding today
        mean = statistics.mean(rolling)
        stdev = statistics.pstdev(rolling) or 0.01
        actual = history[-1]
        if actual < 10.0: continue               # floor: ignore noise
        z = (actual - mean) / stdev
        if z >= 2.0:
            severity = 'high' if z>=4 else 'medium' if z>=3 else 'low'
            yield Anomaly(group, mean, actual, int((actual-mean)/mean*100), severity)
```

Statistics not ML because: explainable to CFO, runs in ms, sufficient at <50 customers, no warm-up.

## Budget Check Algorithm

```
For each budget in org:
  mtd_spend = SUM(daily_cost_summaries.total_cost_usd)
              WHERE org_id = org_id
                AND day BETWEEN first_of_month AND today
                AND <scope_filter>          ← eq(provider|model|*_tag) or none (global)

  spent_pct = int(mtd_spend / monthly_limit * 100)

  if spent_pct >= 100:
    if notified_100_at NOT in current calendar month:
      send_budget_alert(budget_id, 100, org_id)   ← Resend email
      write notified_100_at = now()
    continue                                       ← 100% supersedes warning; no double-alert

  if spent_pct >= alert_at_pct:
    if notified_80_at NOT in current calendar month:
      send_budget_alert(budget_id, alert_at_pct, org_id)
      write notified_80_at = now()
```

Idempotency: `notified_80_at` / `notified_100_at` timestamps are compared at `(year, month)` granularity - one alert per threshold per calendar month regardless of how many nightly runs execute.

## AI Layer

| Use | Model | Trigger | Cap |
|---|---|---|---|
| Recommendations | Haiku 4.5 | daily/org | $0.02 |
| Anomaly explainer | Haiku 4.5 | on creation, 24h cache | $0.01 |
| Monthly narrative | Sonnet 4.6 | 1×/month/org | $0.05 |

**Hard cap:** 3 AI calls/org/day enforced in Redis. Only aggregated summaries in prompts - never raw events, never PII. All outputs cached in DB.

## Engineering Reqs

- **`celery_app.py` import order:** must be imported in `api/main.py` before any router that calls `.delay()`. `@shared_task` tasks bind to whichever Celery app is constructed first - without this import they bind to a default app with `broker_url=None` (AMQP fallback) instead of Redis.
- **Lang:** TS strict in `/web`, no `any`. Python 3.11 with `ruff` + `mypy` + `black`.
- **CI:** lint + typecheck + tests on every PR. No direct push to `main`.
- **Tests:** unit-test pricing math, anomaly logic, tag-rule engine (target 80% on these). One e2e happy path per milestone. No frontend tests in MVP.
- **Envs:** `local` (Docker compose) · `staging` (auto-deploy from `main`) · `production` (manual deploy).
- **Logging:** structlog JSON. Every line: `request_id`, `org_id`, `actor_user_id`, `event`.
- **PostHog events:** signup, org_created, provider_connected, tag_created, budget_created, anomaly_viewed, recommendation_applied, pdf_downloaded, checkout_completed.

## Operational Notes

### Celery worker platforms

| Platform | Pool | Concurrency | Soft limit | Notes |
|---|---|---|---|---|
| Windows (local dev) | `solo` | 1 | disabled | No `fork`, no SIGUSR1. `solo` pool runs tasks in main process. |
| Linux (Railway prod) | `prefork` | default | 300s | SIGKILL hard limit at 600s. Max 100 tasks/child before restart. |

Set in `api/workers/celery_app.py` via `sys.platform == "win32"` check.

### ENCRYPTION_KEY bootstrap

Generate once per environment:
```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```
Set as `ENCRYPTION_KEY=<output>` in `.env` (local) or Railway env vars (production). An empty key raises `ValueError` before any DB operation.

## Security (non-negotiable)

- Admin keys: never touch frontend. Server-side only: validate → encrypt → store. Never returned to client. Never logged.
- AES-256-GCM via `EncryptionService` (32-byte key, 96-bit nonce prepended to ciphertext). Key in env var locally; Supabase Vault in production.
- BYTEA storage: `"\\x" + ciphertext.hex()` so Supabase returns `\x<hex>` format; strip prefix before `bytes.fromhex()` on all decrypt paths.
- RLS on every customer-data table. Two-tenant SQL probe before every deploy.
- `audit_events` row on every key/budget mutation.
- Upstash rate limiter: 60 req/min/user on public routes.
- CORS: strict allow-list (`app.<domain>` only).

## Pre-deploy smoke

1. RLS probe passes: run `infra/scripts/smoke-test.sql` - requires `SET LOCAL ROLE authenticated` before SELECT probes (the `postgres` superuser bypasses all RLS `USING` clauses).
2. Signup → org → connect → chart works on staging.
3. Stripe test checkout completes; webhook updates `billing`.
4. No new Sentry errors in last 1h.
5. `pricing.yaml` version committed.

## Known V1 debt (don't pay yet)

| Debt | Repay trigger |
|---|---|
| Postgres-only | `usage_events` > 50M rows OR Cost Explorer p95 > 1s → ClickHouse/Tinybird |
| Single-region (US-East) | First EU customer with residency ask |
| No SDK ingestion | First customer requiring per-request attribution at call site |
| Rule-based recs | 30 days of org data → Claude-generated structured recs |
| RLS-via-JWT only | Public customer API |
