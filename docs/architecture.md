# Architecture — AI FinOps Platform

Companion to `project_spec.md`. How we build it.

## Stack

| Layer | Choice | Note |
|---|---|---|
| Frontend | Next.js 14 (App Router) + TS + Tailwind + shadcn/ui | Server components for dashboard |
| Charts | Tremor (blocks) + Recharts (custom) | |
| Tables | TanStack Table | Required for Cost Explorer pivot |
| Backend | FastAPI (Python 3.11) | Separate from Next.js — ingestion needs persistent workers |
| Jobs | Celery + Upstash Redis | Python parity with API |
| DB | Supabase Postgres + RLS | ClickHouse only if `usage_events` > 50M rows |
| Auth | Clerk | Multi-tenant orgs built-in |
| Billing | Stripe Checkout + Customer Portal | No custom billing UI |
| Email | Resend | |
| Storage | Cloudflare R2 | PDFs |
| AI | Claude Haiku 4.5 | Recs, narratives — capped $0.05/org/day |
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
budgets (id, org_id, scope_type, scope_value, monthly_limit numeric(12,2), alert_at_pct int default 80, hard_cap bool, created_by)
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
GET    /usage/export.csv

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
POST   /slack/oauth/callback
POST   /slack/disconnect

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

**Anthropic:** `GET /v1/organizations/usage_report/messages` + `/cost_report`. Headers: `x-api-key: sk-ant-admin-...`, `anthropic-version: 2023-06-01`.

**Gemini:** Cloud Billing API on the Gemini project. Validate granularity in M2 week 1; defer to V1 if weak.

**Pricing:** prefer provider Cost API values. `pricing.yaml` is fallback + used for forecasts. Monthly review.

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

### Nightly (00:30 UTC, per org)
```
aggregate_usage_events   → upsert daily_cost_summaries
detect_anomalies         → insert anomalies, enqueue notify
check_budgets            → enqueue budget alerts on threshold cross
generate_recommendations → rule-based (V1: Claude Haiku)
```

### Slack digest (09:00 org-local)
```
build_digest_payload     → yesterday spend, 7d avg, MoM, top 3 drivers, open anomalies
chat.postMessage         → Slack
record sent_at           → slack_digests (idempotency)
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

## AI Layer

| Use | Model | Trigger | Cap |
|---|---|---|---|
| Recommendations | Haiku 4.5 | daily/org | $0.02 |
| Anomaly explainer | Haiku 4.5 | on creation, 24h cache | $0.01 |
| Monthly narrative | Sonnet 4.6 | 1×/month/org | $0.05 |

**Hard cap:** 3 AI calls/org/day enforced in Redis. Only aggregated summaries in prompts — never raw events, never PII. All outputs cached in DB.

## Engineering Reqs

- **`celery_app.py` import order:** must be imported in `api/main.py` before any router that calls `.delay()`. `@shared_task` tasks bind to whichever Celery app is constructed first — without this import they bind to a default app with `broker_url=None` (AMQP fallback) instead of Redis.
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

1. RLS probe passes: run `infra/scripts/smoke-test.sql` — requires `SET LOCAL ROLE authenticated` before SELECT probes (the `postgres` superuser bypasses all RLS `USING` clauses).
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
