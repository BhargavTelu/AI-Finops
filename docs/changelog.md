# Changelog

All notable changes to the AI FinOps Platform.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased] — M3 in progress

---

## [0.3.0] — M2 Multi-Provider + Attribution Wedge (2026-05-20)

117 tests passing, 2 skipped. 0 TypeScript errors.

### Added

**Anthropic Adapter** (`api/adapters/anthropic.py`)
- Implements `UsageAdapter` protocol: `validate()` + `fetch_costs()`
- `validate()`: pings `GET /v1/organizations/usage_report/messages` with a 1-day window; raises `ValueError` with human-readable message on 401/403/unexpected status; wraps `httpx.RequestError` into `ValueError("Network error: ...")`
- `fetch_costs()`: paginated `GET /v1/organizations/usage_report/messages` — cursor-based pagination via `_paginate()` helper with `next_page` token; yields `NormalizedUsageEvent` per model-hour bucket; computes cost from `pricing.yaml` via `_compute_cost()` (per-Mtok rates for input, output, cache-read); maps `cache_read_input_tokens` → `cached_tokens`, preserves `cache_creation_input_tokens` in `raw_meta`; skips rows where all tokens are zero and cost is zero
- Pricing support: `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-4-5` (and legacy variants) from `packages/pricing/pricing.yaml`; unknown models yield event with `cost_usd=Decimal("0")`
- Required headers: `x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-beta: usage-report-2024-07-01`
- 19 tests in `tests/test_anthropic_adapter.py`: validate 200/401/403/500/network error; cost math per token type; pagination; multi-model buckets; zero-cost skip; unknown model handling; `raw_meta` field preservation

**Gemini Adapter** (`api/adapters/gemini.py`)
- `validate()`: `GET https://generativelanguage.googleapis.com/v1beta/models?key={api_key}` — 200 → `True`; non-200 → `ValueError` with status code; `httpx.RequestError` → `ValueError("Could not reach Gemini API: ...")`
- `fetch_costs()`: empty generator (returns immediately); logs `gemini_billing_not_available` via structlog with reason; AI Studio API has no usage-reporting endpoint; Cloud Billing API requires OAuth2/service account — deferred to V1
- Users can connect and validate Gemini keys; integration saves as `active`; zero cost events are inserted
- 8 tests in `tests/test_gemini_adapter.py`: validate 200/400/401/403/network error; key sent as query param (not header); fetch_costs returns empty; fetch_costs makes zero HTTP calls

**Tag-Rule Engine** (`api/services/tag_engine.py`)
- Pure-function module, no DB access, fully unit-testable in isolation
- `CompiledRule` frozen dataclass: `tag_type`, `tag_name`, `match_type`, `match_pattern`, `priority`
- `compile_rules(db_rows)`: converts PostgREST rows (tag_rules joined with tags via `select("*, tags(type, name)")`), filters disabled rules, parses embedded `tags: {"type": ..., "name": ...}` dict, sorts by `priority` ASC (lower = higher priority)
- `_matches(rule, label)`: `exact` (case-sensitive equality), `substring` (`in` operator), `regex` (`re.search` with `try/except re.error` returning `False` on invalid pattern — no propagation)
- `apply_rules(label, rules)`: returns `dict[str, str | None]` with keys `feature_tag`, `team_tag`, `customer_tag`, `env_tag`; first matching rule per tag type wins; stops early when all 4 types assigned; `None`/empty label treated as empty string
- 28 tests in `tests/test_tag_engine.py`: compile_rules (7), exact matching (4), substring matching (4), regex matching (4), priority and multi-type (7), None/empty label safety (2)

**Tags API** (`api/routers/tags.py`) — all 8 endpoints implemented (previously all stubs)
- `GET /tags` — list all org tags ordered by type then name
- `POST /tags` — create tag; 409 on `UNIQUE(org_id, type, name)` violation; 422 for invalid `type` enum
- `PATCH /tags/:id` — update name + color; 404 if not found or wrong org
- `DELETE /tags/:id` — hard delete; cascades to `tag_rules` via `ON DELETE CASCADE`; 404 if not found
- `GET /tag-rules` — list rules ordered by priority, joined with `tags(type, name)` via PostgREST embedded resource syntax
- `POST /tag-rules` — validates `tag_id` belongs to org before insert; returns `TagRuleRead` with embedded tag info
- `PATCH /tag-rules/:id` — update match_type, match_pattern, priority, enabled
- `DELETE /tag-rules/:id` — 204 on success; 404 if not found
- `POST /tag-rules/preview` — dry-run a pattern against last 7 days of `usage_events`; builds a temporary `CompiledRule` to reuse `_matches()`; returns up to 20 deduplicated `{api_key_label, provider, model}` matches; no DB writes
- Pydantic schemas: `TagCreate`, `TagRead`, `TagRuleCreate`, `TagRuleRead` (with `tags: dict | None = None` for joined data), `TagRulePreview`, `PreviewMatch`
- 16 tests in `tests/test_tag_routes.py`: list/create/delete tags; list/create/delete rules; preview with match/no-match/deduplication

**Tag Engine — Ingestion Wire-up** (`api/workers/ingestion.py`)
- `compile_rules()` called once per `_ingest_window()` invocation (before the event loop) — loads enabled tag rules for the org joined with tag name/type
- `apply_rules(event.api_key_label, compiled)` called per event — result dict spread into `usage_events` row via `**apply_rules(...)`
- Tag assignments denormalized directly into `feature_tag`, `team_tag`, `customer_tag`, `env_tag` columns at write time — zero query overhead at read time
- `GeminiAdapter` added to `_ADAPTERS` dict

**Cost Explorer API** (`api/routers/usage.py`)
- `GET /usage/explore?range=<7d|30d|90d>&group_by=<provider|model|feature_tag|team_tag|customer_tag|env_tag>&provider=<optional>` — queries `daily_cost_summaries`, aggregates in Python, returns `list[ExploreRow]` with `group_value`, `total_cost_usd`, `total_requests`, `pct_of_total`
- `pct_of_total` computed server-side; always sums to 100% across returned rows
- Optional `provider` filter applied at DB level
- 21 tests in `tests/test_usage_routes.py` (extended from M1): explore grouping, pct_of_total math, provider filter, empty state, invalid group_by

**Cost Explorer UI** (`apps/web/src/app/(dashboard)/cost-explorer/`)
- Server component (`page.tsx`): validates `group_by` and `range` query params against allowlists; parallel fetch of explore data; renders empty state with link to integrations if no data
- `ExploreControls` client component: dropdown selects for Group By (provider/model/feature_tag/team_tag/customer_tag/env_tag) and Range (7d/30d/90d); optional provider filter; updates URL via `router.push` with new params; instant re-fetch on change
- `ExploreTable` component: TanStack Table with sortable columns; `% of total` column; totals row pinned at bottom; handles empty data; formatted USD and number columns
- TypeScript types: `ExploreRow` added to `lib/types.ts`

**Tags Settings UI** (`apps/web/src/app/(dashboard)/settings/tags/`)
- Server component (`page.tsx`): parallel fetch of tags + rules; passes `token` to client component for client-side API calls
- `TagsClient` client component (`tags-client.tsx`): manages tag list, rules list, form visibility, error messages, preview results with local state; calls `router.refresh()` after mutations to resync server state
- Tag CRUD: create form (type select, name input, hex color picker); inline error on 409 duplicate; delete with cascade info; empty state CTA
- Rule CRUD: create form (tag dropdown, match type select, monospace pattern input, priority number); delete
- Preview: `POST /tag-rules/preview` → shows matching api_key_labels with provider/model; empty state if no matches
- Tag type color badges: feature=blue, team=purple, customer=green, env=orange
- TypeScript types: `Tag`, `TagRule`, `TagType`, `MatchType`, `PreviewMatch` added to `lib/types.ts`

### Fixed

- **`integrations.py` `_ADAPTERS` only contained OpenAI**: Anthropic and Gemini keys were returning 422 "not yet supported". Fixed by adding `AnthropicAdapter` and `GeminiAdapter` to the `_ADAPTERS` dict in `integrations.py`

### Resolved (M2 open questions)

- **Anthropic Enterprise Analytics API**: uses standard Admin API (`x-api-key`), not Enterprise-gated — implemented in M2
- **Gemini billing granularity**: AI Studio API keys have no usage-reporting endpoint; Cloud Billing API requires OAuth2/service account (different auth model from simple API keys) — cost collection deferred to V1; key validation ships in M2

---

## [0.2.0] — M1 First Integration + First Chart (2026-05-19)

### Added

**Integrations API**
- `POST /integrations` — validates OpenAI Admin key via live API ping, AES-256-GCM encrypts with `EncryptionService`, stores as BYTEA with PostgreSQL `\x`-prefixed hex, writes audit event, enqueues `backfill_integration`
- `GET /integrations` — lists active integrations for the org (key never returned)
- `DELETE /integrations/:id` — soft-revokes (sets `status=revoked`), writes audit event
- `IntegrationCreate` / `IntegrationRead` Pydantic schemas in `api/schemas/integrations.py`

**OpenAI Adapter** (`api/adapters/openai.py`)
- Implements `UsageAdapter` protocol: `validate()` + `fetch_costs()`
- `validate()`: pings `GET /v1/organization/costs` with a 1-day window; raises `ValueError` with human-readable message on 401/403
- `fetch_costs()`: two-pass — Pass 1 builds token lookup from `GET /v1/organization/usage/completions`; Pass 2 yields `NormalizedUsageEvent` from `GET /v1/organization/costs`
- Cursor-based pagination via `_paginate()` helper; `bucket_width=1d`, `_PAGE_LIMIT=31` (OpenAI daily bucket max)

**Celery Workers** (`api/workers/`)
- `backfill_integration` — pulls 30d historical data on key connect; delete-before-insert idempotency in `usage_events`; triggers `aggregate_org` immediately after so charts appear without waiting for the nightly run; retries up to 3× with 60s delay; marks integration `error` on failure
- `refresh_integration` — incremental fetch since `last_synced_at`; falls back to 4h lookback if no prior sync
- `refresh_all_integrations` — beat task dispatching `refresh_integration` for all active integrations every 4h
- `aggregate_org` — pages through `usage_events`, groups in Python by (day, provider, model, *_tag), UPSERTs `daily_cost_summaries`; processes up to yesterday UTC only; 31-day window
- `aggregate_all_orgs` — beat task dispatching `aggregate_org` for all orgs with active integrations at 00:30 UTC

**Celery beat schedule** (`api/workers/celery_app.py`)
- `nightly-aggregation`: `aggregate_all_orgs` at 00:30 UTC
- `refresh-integrations`: `refresh_all_integrations` every 4h
- `slack-digest`: `send_daily_digests` at 09:00 UTC (stub — M3)
- `detect-anomalies`: `detect_all_orgs` at 01:00 UTC (stub — M3)
- Windows dev support: `worker_pool="solo"` on `win32`, `prefork` on Linux (Railway); `task_soft_time_limit` and `worker_max_tasks_per_child` disabled on Windows (no SIGUSR1)

**Usage API** (`api/routers/usage.py`)
- `GET /usage/summary?range=<Nd>` — aggregate totals (cost, requests, tokens) from `daily_cost_summaries`; `period_end` is always yesterday UTC
- `GET /usage/timeseries?range=<Nd>&group_by=model` — daily cost points grouped by model; aggregates tag-split rows in Python; returns sorted `list[DailyPoint]`; raises HTTP 400 for unsupported `group_by` values
- `_parse_range()` helper: `period_end = yesterday`, `period_start = period_end - (days-1)` (N-day inclusive window)
- `UsageSummary` / `DailyPoint` Pydantic schemas in `api/schemas/usage.py`
- `/explore`, `/forecast`, `/export.csv` stubbed for M2/M4

**Frontend** (`apps/web/`)
- Settings/Integrations page — server component fetches initial list; `IntegrationsPage` client component handles connect form, success/error banners, integration table (provider/name/status/last-synced/revoke), empty state
- Dashboard page — server component fetches `summary` + `timeseries` in parallel, pivots data server-side, renders 3 stat cards (30d cost/requests/tokens) + `DashboardCharts` client component
- `DashboardCharts` — Tremor `AreaChart` (30d cost trend by model) + `BarChart` (cost by model, top 10)
- Empty state: shows link to integrations when no data
- Shared TypeScript types (`lib/types.ts`): `IntegrationRead`, `UsageSummary`, `DailyPoint`

**Tests** — 37 passing, 2 skipped
- `tests/test_integration_routes.py` — CRUD routes, key validation, duplicate detection, org isolation
- `tests/test_ingestion.py` — ingest window, backfill, refresh workers
- `tests/test_aggregation.py` — aggregate math, upsert idempotency
- `tests/test_usage_routes.py` — summary totals, period dates, timeseries grouping, unsupported group_by

### Fixed

- **Missing `ENCRYPTION_KEY`**: `.env` had empty value; all `POST /integrations` calls returned 500. Generated and set a valid AES-256-GCM key in `.env`
- **Wrong Celery broker on startup**: `celery_app.py` not in FastAPI import path caused `@shared_task` to bind to a default app with `broker_url=None` (AMQP). Added `import api.workers.celery_app` to `api/main.py`
- **BYTEA `\x` prefix crash**: Supabase returns BYTEA with `\x` prefix; `bytes.fromhex("\\x...")` raises `ValueError`. Fixed storage to use `"\\x" + hex` and decrypt to strip prefix before `fromhex()`
- **Celery worker crash on Windows** (`ValueError: not enough values to unpack`): billiard spawn model races with task dispatch. Fixed with `worker_pool="solo"` on Windows
- **OpenAI 400 "Limit exceeds maximum"**: `_PAGE_LIMIT` reduced from 180 → 168 → 31 to match the `1d` bucket limit

---

## [0.1.0] — M0 Foundation (2026-05-19)

### Added

**Infrastructure & scaffold**
- Initial monorepo structure: `apps/web`, `apps/api`, `packages/types`, `packages/pricing`, `infra/`
- `apps/web` — Next.js 14 App Router skeleton with Clerk, Tailwind, shadcn/ui, Tremor, TanStack Table
- `apps/api` — FastAPI + Celery skeleton; all routers, schemas, services, and workers stubbed
- `packages/types` — shared TypeScript types (API responses + DB rows)
- `packages/pricing` — `pricing.yaml` fallback table (Jan 2025 prices for OpenAI, Anthropic, Gemini)
- `infra/migrations/20240101000000_initial_schema.sql` — full schema with RLS on all org-scoped tables
- `infra/migrations/20260518000000_add_slack_digests.sql` — `slack_digests` idempotency table
- `infra/migrations/20260518000001_add_updated_at_to_users_and_orgs.sql` — `updated_at` on identity tables
- `infra/migrations/20260519000000_add_clerk_id_to_identity_tables.sql` — `clerk_id TEXT UNIQUE` on `users` and `organizations` for webhook upsert idempotency
- `infra/scripts/smoke-test.sql` — two-tenant RLS isolation probe
- `infra/scripts/seed.sql` and `bootstrap.sh`
- `docker-compose.yml` for local Redis + api + worker
- Python venv at `apps/api/.venv`

**Auth**
- `apps/web/src/middleware.ts` — `clerkMiddleware` protecting all non-public routes
- `apps/web/src/app/(auth)/sign-in/` and `sign-up/` — Clerk-hosted auth UI
- `apps/web/src/app/create-org/page.tsx` — org creation page using `<CreateOrganization />`
- `apps/web/src/app/(dashboard)/layout.tsx` — auth + org guard, sidebar with `<OrganizationSwitcher />`, header with `<UserButton />`
- `apps/web/src/components/nav-links.tsx` — active-link nav client component
- `apps/web/src/lib/supabase/server.ts` — injects Clerk HS256 "supabase" template JWT so Supabase RLS reads `org_id` claim
- `apps/api/src/api/deps.py` — `_require_org()`: RS256 JWKS verification, `OrgDep` dependency
- `apps/api/src/api/routers/webhooks.py` — Clerk webhook handler: Svix signature verification, user/org/membership upsert, `db_id` write-back to Clerk `public_metadata`

### Fixed
- `infra/scripts/smoke-test.sql` — added `SET LOCAL ROLE authenticated` before SELECT probes; the `postgres` superuser bypasses all RLS `USING` clauses, making the probe always pass regardless of policy correctness

---
