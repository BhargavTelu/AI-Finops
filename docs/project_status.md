# Project Status

## Current Milestone: M3 — Intelligence Layer

**Status:** M2 verified complete 2026-05-20. Starting M3.

---

## M3 Tasks

### Group A — Anomaly Detection

- [ ] `detect_anomalies(org_id, today)` Celery task — rolling 7-day mean + 2σ algorithm; >$10 floor; severity: low (z≥2), medium (z≥3), high (z≥4); groups by (model, feature_tag, team_tag, customer_tag)
- [ ] `detect_all_orgs` beat task — runs at 01:00 UTC nightly; dispatches `detect_anomalies` per org
- [ ] Wire `detect_all_orgs` into Celery beat schedule (stub already present in `celery_app.py`)
- [ ] `GET /anomalies?status=open|acknowledged|dismissed` — list anomalies for org ordered by `detected_at DESC`
- [ ] `PATCH /anomalies/:id` — acknowledge or dismiss; updates `status` field
- [ ] `AnomalyRead` Pydantic schema: `id`, `detected_at`, `scope_kind`, `scope_value`, `baseline_usd`, `actual_usd`, `spike_pct`, `severity`, `status`, `context`
- [ ] `/anomalies` frontend page — anomaly log table; severity badges (low=yellow, medium=orange, high=red); ack/dismiss buttons; empty state "No anomalies detected"
- [ ] Unit tests: anomaly algorithm math (z-score, floor, severity thresholds, < 14 days history skip)

### Group B — Budgets + Email Alerts

- [ ] `GET/POST/PATCH/DELETE /budgets` — CRUD; scope types: `global`, `provider`, `model`, `feature_tag`, `team_tag`, `customer_tag`, `env_tag`; `monthly_limit` in USD; `alert_at_pct` default 80
- [ ] `BudgetCreate` / `BudgetRead` Pydantic schemas
- [ ] `check_budgets(org_id)` Celery task — runs after nightly aggregation; compares MTD spend per scope to monthly limit; fires alert at 80% and 100% thresholds (once per threshold per month via `notified_at` guard in DB)
- [ ] Resend email: 80% warning template + 100% exceeded template — to org owner email; include scope name, limit, current spend, % used
- [ ] `/settings/budgets` frontend page — budget list with scope/limit/current spend/% bar; add/delete form; empty state with CTA
- [ ] Unit tests: budget check math, threshold guard (re-notify prevention)

### Group C — Slack Integration

- [ ] Slack OAuth flow: `GET /slack/oauth/callback` — exchanges code for bot token; stores encrypted in `slack_integrations` table; writes `installed_by`
- [ ] `POST /slack/disconnect` — deletes `slack_integrations` row; revokes token via Slack API
- [ ] `send_daily_digest(org_id)` Celery task — builds digest payload (yesterday spend, 7d avg, MoM delta, top 3 cost drivers, count of open anomalies, count of open budgets near threshold); `chat.postMessage` to org channel; records `sent_at` in `slack_digests` for idempotency
- [ ] `send_daily_digests` beat task — runs at 09:00 UTC; dispatches per org with connected Slack; wire into `celery_app.py` (stub already present)
- [ ] Real-time anomaly alert: when `detect_anomalies` creates a new anomaly with severity ≥ medium, post to Slack channel with spike %, baseline, actual, model/tag context
- [ ] Real-time budget alert: when `check_budgets` crosses 80% or 100%, post to Slack in addition to email
- [ ] `/settings/slack` frontend page — connect Slack button (OAuth redirect); connected state shows workspace + channel; disconnect button; empty state with CTA
- [ ] Unit tests: digest payload builder; Slack message format; alert trigger logic

### Group D — Recommendations Engine

- [ ] `generate_recommendations(org_id)` Celery task — runs nightly after aggregation; rule-based (no AI in M3)
- [ ] Rule 1 — **Model downgrade**: detect models with avg cost/request > $0.01 and request count > 100; recommend switching to a cheaper model in the same family; compute projected savings
- [ ] Rule 2 — **Prompt caching**: detect repeated calls (same model, same feature_tag, high request count); recommend enabling prompt caching; estimate savings based on cache-read price vs input price
- [ ] Rule 3 — **Batch API**: detect high request_count with small token counts (avg < 2K tokens); recommend Batch API for applicable models (OpenAI `gpt-4o`, `gpt-4o-mini`); 50% cost reduction estimate
- [ ] Deduplication: `UNIQUE(org_id, type, scope_value)` for `status=new` recs — don't re-insert if already open
- [ ] `GET /recommendations?status=new|applied|dismissed` — list recs ordered by `projected_savings_usd DESC`
- [ ] `PATCH /recommendations/:id` — mark `applied` or `dismissed`; sets `resolved_at`
- [ ] `RecommendationRead` Pydantic schema: `id`, `type`, `title`, `description`, `projected_savings_usd`, `confidence`, `status`, `generated_at`
- [ ] `/recommendations` frontend page — rec cards with title, savings badge, evidence summary, apply/dismiss buttons; filter by status; empty state "No recommendations yet — data needed"
- [ ] Unit tests: each recommendation rule logic; deduplication; savings calculation

### M3 Done-condition

Test org with synthetic spike fires anomaly → Slack alert lands in < 10 min → recommendations list shows 3+ items with savings estimates.

### M3 Out of scope

- Stripe billing, CFO PDF, landing page, onboarding wizard (M4)
- AI-generated recommendation narratives (V1 — Claude Haiku)
- Per-user Slack DMs (V1)

---

## Completed Milestones

### M2 — Multi-Provider + Attribution Wedge ✅ (verified 2026-05-20)

**117 tests passing, 2 skipped. 0 TypeScript errors.**

**Group A — Anthropic Adapter**
- [x] `AnthropicAdapter` (`api/adapters/anthropic.py`) — `validate()` + `fetch_costs()`
- [x] `validate()`: pings `/v1/organizations/usage_report/messages`; raises `ValueError` on 401/403/unexpected/network error
- [x] `fetch_costs()`: paginated via `_paginate()` with `next_page` cursor; yields `NormalizedUsageEvent` per model-hour bucket; `_compute_cost()` uses pricing.yaml rates for input/output/cache-read tokens; maps `cache_read_input_tokens` → `cached_tokens`; preserves `cache_creation_input_tokens` in `raw_meta`; skips zero-cost zero-token rows
- [x] 19 tests in `tests/test_anthropic_adapter.py`

**Group B — Cost Explorer**
- [x] `GET /usage/explore` — queries `daily_cost_summaries`; groups by provider/model/feature_tag/team_tag/customer_tag/env_tag; optional provider filter; returns `list[ExploreRow]` with `pct_of_total`
- [x] `ExploreRow` schema: `group_value`, `total_cost_usd`, `total_requests`, `pct_of_total`
- [x] Cost Explorer page at `/cost-explorer` — server component with validated query params
- [x] `ExploreControls` client component — Group By + Range + Provider dropdowns; updates URL params
- [x] `ExploreTable` component — TanStack Table; sortable columns; `% of total` column; totals row
- [x] 21 tests in `tests/test_usage_routes.py`

**Group C — Tag System**
- [x] `tag_engine.py` — `CompiledRule` dataclass; `compile_rules()` (filters disabled, parses PostgREST join, sorts by priority); `_matches()` (exact/substring/regex with invalid-regex safety); `apply_rules()` (first match per type, early exit at 4 assigned)
- [x] Tags CRUD: `GET/POST/PATCH/DELETE /tags` — 409 on duplicate, 404 on missing, cascade delete propagates to rules
- [x] Tag Rules CRUD: `GET/POST/PATCH/DELETE /tag-rules` — tag_id ownership check on create; list includes embedded tag info via PostgREST join
- [x] `POST /tag-rules/preview` — dry-run against last 7 days of `usage_events`; reuses `_matches()`; returns up to 20 deduplicated `{api_key_label, provider, model}` tuples
- [x] Tag engine wired into `_ingest_window()` — rules compiled once per window, applied per event, results spread into row dict via `**apply_rules(...)`
- [x] `/settings/tags` page — `TagsClient` with tag CRUD + rule CRUD + preview; color badges per tag type; empty states
- [x] 28 tests in `tests/test_tag_engine.py` + 16 tests in `tests/test_tag_routes.py` = 44 tag tests

**Group D — Gemini Adapter**
- [x] `GeminiAdapter` (`api/adapters/gemini.py`) — `validate()` hits AI Studio models endpoint; `fetch_costs()` is no-op generator (billing deferred to V1 — no usage-reporting endpoint on AI Studio API)
- [x] 8 tests in `tests/test_gemini_adapter.py`

**Bug fixed during M2**
- [x] `integrations.py` `_ADAPTERS` dict only contained `OpenAIAdapter` — Anthropic and Gemini keys returned 422 "not yet supported"; fixed by adding `AnthropicAdapter` and `GeminiAdapter`

**Resolved open questions**
- Anthropic Admin API is not Enterprise-gated — implemented using standard `x-api-key` header
- Gemini AI Studio API has no usage-reporting endpoint; Cloud Billing API requires OAuth2 (different auth model) — key validation ships in M2, cost collection deferred to V1

---

### M1 — First Integration + First Chart ✅ (verified 2026-05-19)

- [x] `POST /integrations` — validate OpenAI Admin key, AES-256-GCM encrypt (BYTEA `\x`-prefixed hex), insert, audit log, enqueue backfill
- [x] `GET /integrations` — list active integrations (key redacted, never returned)
- [x] `DELETE /integrations/:id` — soft-revoke (status=revoked), audit log
- [x] OpenAI adapter (`adapters/openai.py`) — `GET /v1/organization/costs` + `GET /v1/organization/usage/completions`, cursor pagination with `bucket_width=1d`, `_PAGE_LIMIT=31`
- [x] Celery `backfill_integration` task — pull 30d history on key connect; triggers `aggregate_org` immediately so charts appear without waiting for nightly run
- [x] Celery `refresh_integration` task — incremental fetch since `last_synced_at`; falls back to 4h lookback if no prior sync
- [x] Celery `refresh_all_integrations` beat task — enqueues `refresh_integration` for all active integrations every 4h
- [x] Celery `aggregate_org` task — GROUP BY (day, provider, model, *_tag) → UPSERT `daily_cost_summaries`; delete-before-insert idempotency in `usage_events`
- [x] Celery `aggregate_all_orgs` beat task — enqueues `aggregate_org` for all orgs with active integrations at 00:30 UTC
- [x] `GET /usage/summary` — aggregate totals (cost, requests, tokens) for a date range from `daily_cost_summaries`
- [x] `GET /usage/timeseries` — daily cost points grouped by model; aggregates tag-split rows in Python
- [x] Pydantic schemas: `IntegrationCreate`, `IntegrationRead`, `UsageSummary`, `DailyPoint`
- [x] Settings/integrations page — server component + `IntegrationsPage` client component: connect form, integration list with status badges, revoke button
- [x] Dashboard page — server component fetches + pivots data; stat cards (30d cost/requests/tokens); `DashboardCharts` client component with Tremor `AreaChart` (30d trend) + `BarChart` (cost by model)
- [x] Windows-compatible Celery worker: `worker_pool="solo"` on `win32`, `prefork` on Linux (Railway)
- [x] 37 tests passing (37 pass, 2 skipped)

**Bugs found and fixed during M1 validation:**
- `ENCRYPTION_KEY` missing from `.env` — caused 500 on all `POST /integrations` calls
- `celery_app.py` not imported in FastAPI startup — `@shared_task` tasks bound to wrong broker (AMQP instead of Redis)
- BYTEA hex encoding: storage without `\x` prefix caused decrypt crash on read (Supabase returns `\x<hex>`)
- Celery worker crash on Windows (`ValueError: not enough values to unpack`) — billiard spawn model; fixed with `solo` pool
- `_PAGE_LIMIT = 180` exceeded OpenAI hourly bucket max of 168 — then corrected to 31 when `bucket_width` changed to `1d`

---

### M0 — Foundation ✅ (verified 2026-05-19)

- [x] Full monorepo scaffold (Next.js 14 + FastAPI + packages + infra)
- [x] All config files, dependency manifests, folder structure
- [x] Python venv + Node.js dependencies installed
- [x] Initial DB migration — all tables, indexes, RLS policies
- [x] `pricing.yaml` with current model prices
- [x] Clerk JWT verification in `deps.py` (`_require_org`) — RS256 JWKS, extracts user_id + org_id
- [x] Clerk webhook handler (`/api/webhooks/clerk`) — user, org, membership sync + `db_id` write-back to Clerk metadata
- [x] `clerk_id` columns migration applied to Supabase (`infra/migrations/20260519000000_add_clerk_id_to_identity_tables.sql`)
- [x] Clerk middleware at `apps/web/src/middleware.ts` — route protection active
- [x] `/sign-in` and `/sign-up` pages (Clerk components)
- [x] `/create-org` page — org creation flow (`<CreateOrganization />`)
- [x] `/dashboard` gated by auth + org — redirects to `/create-org` if no active org
- [x] Dashboard sidebar (nav links + `<OrganizationSwitcher />`) and header (`<UserButton />`)
- [x] Supabase server client injects Clerk HS256 JWT for RLS
- [x] Two-tenant SQL probe passes (`infra/scripts/smoke-test.sql` — requires `SET LOCAL ROLE authenticated`)
- [x] End-to-end verified: two real users, two real orgs, RLS isolation confirmed

---

## Upcoming Milestones

| Milestone | Focus | Days |
|---|---|---|
| M3 | Anomaly detection + budgets + Slack + recommendations | 11 |
| M4 | Billing + CFO PDF + polish + landing page | 9 |

---

## Open Questions (M3)

1. Slack app credentials — create Slack app in dev before starting Group C; requires redirect URI for OAuth callback
2. Resend sender domain — confirm verified sender domain before Group B email alerts
3. Budget reset cycle — confirm monthly (calendar month) vs rolling 30 days; calendar month simpler for CFO reporting
4. Recommendation confidence scoring — `high/medium/low` or numeric 0–1? Keep categorical for M3 (simpler UI)

---

## Known Debt

See `architecture.md` § Known V1 debt.
