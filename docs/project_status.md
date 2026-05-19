# Project Status

## Current Milestone: M2 — Multi-Provider + Attribution Wedge

**Status:** Starting M2. M1 verified complete 2026-05-19.

---

## M2 Tasks

- [ ] Anthropic adapter (`adapters/anthropic.py`) — `/v1/organizations/usage_report/messages` + `/cost_report`, verify granularity
- [ ] Anthropic ingestion wired into `backfill_integration` + `refresh_integration`
- [ ] Gemini adapter — verify billing API granularity in week 1; defer to V1 if insufficient
- [ ] Tag CRUD (`GET/POST/PATCH/DELETE /tags`)
- [ ] Tag-rules CRUD (`GET/POST/PATCH/DELETE /tag-rules`) + `POST /tag-rules/preview` dry-run
- [ ] Tag-rule engine: runs at ingestion, denormalizes tags into `usage_events` columns
- [ ] `GET /usage/explore` — pivot data for Cost Explorer (group by provider/model/tag/date)
- [ ] Cost Explorer page — TanStack Table with drag dimensions, sort, filter, totals, % of total
- [ ] Multi-provider unified dashboard view (USD-normalized across providers)
- [ ] `timeseries` endpoint extended to support `group_by=feature_tag|team_tag|customer_tag`

**M2 done-condition:** Design partner with 2+ providers sees Cost Explorer and says "I had no idea X was that expensive."

**Out of scope for M2:** Anomalies, budgets, Slack, billing, recommendations, forecasting.

---

## Completed Milestones

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
- [x] Settings/integrations page — server component + `IntegrationsPage` client component: connect form (validate → encrypt → store), integration list with status badges, revoke button
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
| M3 | Anomaly detection + budgets + Slack | 11 |
| M4 | Billing + CFO PDF + polish + landing page | 9 |

---

## Open Questions (M2)

1. Anthropic Enterprise Analytics API — is it Enterprise-gated? → affects M2 timeline
2. Gemini billing granularity — verify in M2 week 1; defer to V1 if weak
3. Stripe trial: 14 days vs none?
4. Entry price: $299 vs $99 for top-of-funnel experiment?

---

## Known Debt

See `architecture.md` § Known V1 debt.
