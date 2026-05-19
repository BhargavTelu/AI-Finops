# Changelog

All notable changes to the AI FinOps Platform.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased] — M2 in progress

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
