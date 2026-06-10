# Project Status

## Current Milestone: M3 - Intelligence Layer

**Status:** M3 COMPLETE ✅. Group A (Anomaly Detection) complete 2026-05-21. Group B (Budgets + Email Alerts) complete 2026-05-21. Group C (Slack Integration) complete 2026-05-21. Group D (Recommendations Engine) complete 2026-06-10. Ready for M4.

---

## M3 Tasks

### Group A - Anomaly Detection ✅ (complete 2026-05-21)

**131 tests passing, 2 skipped. 0 TypeScript errors.**

- [x] `detect_anomalies(org_id, today)` Celery task - rolling 7-day mean + 2σ algorithm; >$10 floor; severity: low (z≥2), medium (z≥3), high (z≥4); groups by (model, feature_tag, team_tag, customer_tag)
- [x] `detect_all_orgs` beat task - runs at 01:00 UTC nightly; dispatches `detect_org` per org
- [x] Beat schedule already wired in `celery_app.py` - no change needed
- [x] `GET /anomalies?status=open|acked|dismissed` - list anomalies for org ordered by `detected_at DESC`
- [x] `PATCH /anomalies/:id` - acknowledge or dismiss; updates `status` field; ownership-checked (404 on wrong org)
- [x] `AnomalyRead` Pydantic schema: `id`, `detected_at`, `scope_kind`, `scope_value`, `baseline_usd`, `actual_usd`, `spike_pct`, `severity`, `status`, `context`
- [x] `/anomalies` frontend page - status tabs (open/acknowledged/dismissed); anomaly log table; severity badges (low=amber, medium=orange, high=red); ack/dismiss buttons with optimistic UI; loading skeleton; empty state; error state
- [x] `AnomalyRead` / `AnomalyStatus` / `AnomalySeverity` types added to `apps/web/src/lib/types.ts`
- [x] Unit tests: algorithm math (11 tests in `test_anomaly.py`) - z-score, floor, severity boundary thresholds, spike_pct edge cases, minimum data length
- [x] Worker unit tests (9 tests in `test_anomaly_detection.py`) - spike detection + insert, no-spike, $10 floor, dedup guard, no-data, scope fields, dispatcher

**Bug fixed:** `first_day` computed as `today - 14` (yielding 14-item history) instead of `today - 15`; `detect_anomalies()` always returned `None`. Caught by worker unit tests.

---

### Group B - Budgets + Email Alerts ✅ (complete 2026-05-21)

**171 tests passing, 2 skipped. 0 TypeScript errors.**

- [x] `GET/POST/PATCH/DELETE /budgets` - CRUD; scope types: `global`, `provider`, `model`, `feature_tag`, `team_tag`, `customer_tag`, `env_tag`; `monthly_limit` in USD; `alert_at_pct` default 80; 409 on duplicate scope
- [x] `BudgetCreate` / `BudgetRead` / `BudgetUpdate` Pydantic schemas - corrected `scope_type` enum from stub; `BudgetRead` includes computed `current_spend_mtd` and `spent_pct`
- [x] `check_org(org_id)` / `check_all_orgs()` Celery tasks in `workers/budget_checks.py` - runs at 02:00 UTC (after aggregation + anomaly detection); compares MTD spend per scope; fires at `alert_at_pct` and 100% thresholds; 100% supersedes warning (no double-alert)
- [x] `notified_80_at` / `notified_100_at` idempotency guard - once per threshold per calendar month; DB migration `20260521000000_fix_budgets_schema.sql` adds columns + fixes constraint
- [x] `send_budget_alert` Celery task in `notifications.py` - Resend email; 80% warning template + 100% exceeded template; scope label, limit, MTD spend, % used; retries on failure
- [x] `/budgets` frontend page - server component + `BudgetsClient`; budget list with progress bars (green/amber/red); Add Budget dialog (scope selector, scope value input, limit, alert%); inline delete with confirmation; empty state with CTA; loading skeleton
- [x] `BudgetRead` / `BudgetScopeType` types added to `apps/web/src/lib/types.ts`
- [x] Beat schedule wired: `check-budgets` at 02:00 UTC in `celery_app.py`
- [x] 40 new tests: 24 in `test_budget_checks.py` (threshold math, idempotency guard, scope filtering, zero-limit, custom threshold) + 16 in `test_budget_routes.py` (CRUD, org isolation, 409, 404, validation)

**Bug found and fixed:** `check_org` fell through to 80% alert check when 100% was already notified same month (only `continue`d when sending, not when guard blocked). Fixed: always `continue` when `spent_pct >= 100`. Caught by `test_100pct_guard_prevents_resend_same_month`.

### Gap Analysis & Test Hardening ✅ (complete 2026-05-22)

**324 tests passing, 2 skipped. 103 new gap tests all green.**

A systematic gap analysis identified 29 untested code paths across 11 categories. All 29 gaps now have regression tests (103 test functions total). Four production bugs were fixed in the process.

**Production bugs fixed:**
- [x] `routers/webhooks.py` - `_handle_membership_created` used `.single().execute()` which raises `PGRST116` unhandled (5xx from wrong place). Replaced with `try/except` around each `.single()` call and added `isinstance(data, dict) and "id" in data` guard to also catch PostgREST error-dict responses. (Gap-16)
- [x] `routers/slack.py` - `slack_resp["team"]["id"]` raised `KeyError` when Slack omits the `team` key (misconfigured scopes). Changed to `.get("team") or {}` + `.get("id", "")` with explicit `HTTPException(400)`. (Gap-25)
- [x] `services/encryption.py` - `base64.b64decode()` raised `binascii.Error("Incorrect padding")` for malformed keys; error message didn't match the descriptive pattern tests expected. Wrapped decode in `try/except`; re-raises as `ValueError`. (Gap-28)
- [x] `packages/pricing/pricing.yaml` - `claude-3-5-sonnet-20241022` and `claude-3-5-haiku-20241022` missing from pricing table; `_compute_cost()` silently returned `Decimal("0")`. Added both models at current pricing ($3/$15/$0.30 and $0.80/$4/$0.08 per MTok). (Gap-20)

**Test infrastructure fixes (test-side bugs, not production):**
- [x] `test_aggregation_worker.py` (Gap-02) - Concurrent test raced to `patch()` the same module-level function from two threads; one thread's mock overwrote the other's. Fixed by patching once with `side_effect=make_db` outside threads.
- [x] `test_ingestion_gaps.py` (Gap-06) - `patch("api.workers.ingestion.aggregate_org")` failed because `aggregate_org` is a local import inside `backfill_integration`. Changed to `patch("api.workers.aggregation.aggregate_org")`.
- [x] `test_route_gaps.py` (Gap-25/26) - `patch("api.routers.slack._require_org")` failed because `_require_org` lives in `api.deps`. Switched to `app.dependency_overrides[_require_org]`; also fixed wrong URL prefix and missing `state` field in request body.
- [x] `test_notification_gaps.py` (Gap-24) - `_compute_scope_spend` is locally imported in `notifications.py`; changed patch target to `api.workers.budget_checks._compute_scope_spend`.
- [x] `test_notification_gaps.py` - `with (...) as (a, *b):` syntax (tuple unpacking after parenthesized `with`) is not valid Python; moved each `as` clause onto its individual `patch()`.

**Gap coverage by priority:**

| Priority | Gaps | Tests | Notes |
|----------|------|-------|-------|
| Critical | Gap-01, 02, 05, 06, 08, 10, 18 | 7 groups | Aggregation pipeline, concurrency races, ingestion failures, adapter two-pass |
| High | Gap-03, 07, 11–14, 16, 19–21, 22–23, 25, 27 | 15 groups | JWT security, JWKS races, Anthropic adapter, regex ReDoS, Slack KeyError, Svix multi-sig |
| Medium | Gap-04, 09, 15, 17, 24, 26, 28–29 | 7 groups | Tag coalescing, anomaly dedup, CORS/encryption config, lstrip semantics, cascade cleanup |

---

### Group C - Slack Integration ✅ (complete 2026-05-21)

**221 tests passing, 2 skipped. 0 TypeScript errors in new files.**

- [x] `GET /slack/status` - returns `SlackStatusResponse`; `{connected: false}` when no row exists
- [x] `POST /slack/oauth/callback` - exchanges code for bot token; AES-256-GCM encrypts; upserts `slack_integrations` (upsert allows channel switching); resolves `installed_by` UUID from Clerk user_id; HTTP 400 if `incoming_webhook.channel_id` absent
- [x] `POST /slack/disconnect` - revokes token (best-effort); always deletes `slack_integrations` row; 404 if not connected
- [x] `slack_client.py` service - `exchange_code()`, `revoke_token()`, `post_message()`; pure `httpx` (no Slack SDK); 10s timeout; `ValueError` on `ok=false` for Celery retry handling
- [x] `SlackOAuthCallbackBody` / `SlackStatusResponse` Pydantic schemas in `api/schemas/slack.py`
- [x] `send_daily_digests()` - fan-out task; queries orgs with `slack_integrations`; dispatches `send_slack_digest.delay(org_id)` per org
- [x] `send_slack_digest(org_id)` - per-org digest with `max_retries=2`; idempotency guard via `slack_digests` UNIQUE(`org_id, digest_date`) - skips if already sent today; records row in `slack_digests` on success
- [x] `_fetch_digest_data()` - 4 queries: yesterday total + 7d avg + top-3 drivers, this-month MTD, last-month same period (MoM %), open anomaly count
- [x] `_digest_slack_blocks()` - Block Kit payload: header with date, spend + MoM + 7d avg fields, top-driver bullets, anomaly count; mobile fallback text
- [x] `send_anomaly_alert(anomaly_id)` - `max_retries=3`; severity emoji (🟡/🟠/🔴); spike %, baseline, actual, tag context; skips if anomaly or Slack not found
- [x] Wire-up in `detect_org` - dispatches `send_anomaly_alert.delay()` when `severity in ("medium", "high")` after anomaly insert
- [x] Budget Slack alert in `send_budget_alert` - best-effort Slack post after Resend email; `:warning:` at threshold, `:red_circle:` at 100%; Slack failure does not retry
- [x] `_budget_slack_blocks()` + `_scope_label()` helpers
- [x] `apps/web/src/app/(dashboard)/settings/layout.tsx` - settings layout with `SettingsTabs` client component
- [x] `apps/web/src/app/(dashboard)/settings/settings-tabs.tsx` - Integrations / Tag Rules / Slack tabs; `usePathname()` active state; `Route<string>` cast
- [x] `/settings/slack/page.tsx` - server component; fetches status; builds OAuth URL server-side from `SLACK_CLIENT_ID`; passes flash messages from `searchParams`
- [x] `/settings/slack/slack-client.tsx` - connected state (workspace, channel, installed date, Reconnect + Disconnect); disconnected empty state with CTA; "What you'll receive" feature list; `PageMotion` wrapper
- [x] `/settings/slack/loading.tsx` - `animate-pulse` Skeleton
- [x] `/settings/slack/callback/page.tsx` - server component OAuth callback; redirects to `?connected=true` or `?error=<message>`
- [x] `SlackStatus` TypeScript interface in `apps/web/src/lib/types.ts`
- [x] `SLACK_CLIENT_ID` + `SLACK_REDIRECT_URI` added to `.env.local.example`
- [x] 50 new tests: 9 in `test_slack_routes.py` (routes CRUD + error cases) + 19 in `test_notifications_slack.py` (block builders, alert dispatch) + 22 in `test_notifications_digest.py` (digest data, blocks, idempotency, retry)

### Group D - Recommendations Engine ✅ (complete 2026-06-10)

**603 tests passing, 2 skipped. 0 TypeScript errors.**

- [x] `generate_all_org_recommendations()` / `generate_org_recommendations(org_id)` Celery tasks - runs nightly at 02:30 UTC after budget checks; dispatches per-org; pulls 30d `daily_cost_summaries`, groups by (provider, model, feature_tag), runs rule engine
- [x] Rule 1 - **Model downgrade** (`_check_model_swap`): avg cost/request > $0.01 AND ≥100 requests; downgrade map (gpt-4o→mini, claude-opus-4-5→sonnet-4-5, etc.); savings via input price ratio; confidence 0.85 (>500 req) or 0.60
- [x] Rule 2 - **Prompt caching** (`_check_caching_opportunity`): model supports caching AND ≥200 requests; 30% cache-hit rate on 70% input tokens estimate; confidence 0.60; scope `{model}:{feature_tag or 'all'}`
- [x] Rule 3 - **Batch API** (`_check_batch_opportunity`): model in {gpt-4o, gpt-4o-mini} AND ≥500 requests AND avg tokens < 2000; 50% cost reduction; confidence 0.80
- [x] Deduplication: partial unique index `UNIQUE(org_id, type, scope_value) WHERE status='new'` + explicit query before insert in worker; migration `20260524000000_recommendations_scope_and_dedup.sql`
- [x] `GET /recommendations?status=new|applied|dismissed` - list recs ordered by `projected_savings_usd DESC`; `PATCH /recommendations/:id` - mark `applied` or `dismissed`; sets `resolved_at`; ownership check
- [x] `RecommendationRead` / `RecommendationUpdate` Pydantic schemas with type enum (model_swap, caching, batch, other), evidence dict, scope_value, confidence
- [x] `/recommendations` frontend page - rec cards with savings badge (`$Xk/mo`), type badge (Model swap / Prompt caching / Batch API), effort badge (Easy/Medium/Hard), confidence bar, description, apply/dismiss buttons; status tabs (New/Applied/Dismissed); effort filter pills; total savings summary; empty state with CTA; loading skeleton; error state; Framer Motion stagger animation
- [x] `RecommendationRead` / `RecommendationType` / `RecommendationStatus` types in `apps/web/src/lib/types.ts`
- [x] Beat schedule wired: `generate-recommendations` at 02:30 UTC in `celery_app.py`
- [x] 40+ unit tests in `test_recommendations.py` covering all three rules, edge cases, savings math, confidence thresholds

### M3 Done-condition

Test org with synthetic spike fires anomaly → Slack alert lands in < 10 min → recommendations list shows 3+ items with savings estimates.

### M3 Out of scope

- Stripe billing, CFO PDF, landing page, onboarding wizard (M4)
- AI-generated recommendation narratives (V1 - Claude Haiku)
- Per-user Slack DMs (V1)

---

## Completed Milestones

### M2 - Multi-Provider + Attribution Wedge ✅ (verified 2026-05-20)

**117 tests passing, 2 skipped. 0 TypeScript errors.**

**Group A - Anthropic Adapter**
- [x] `AnthropicAdapter` (`api/adapters/anthropic.py`) - `validate()` + `fetch_costs()`
- [x] `validate()`: pings `/v1/organizations/usage_report/messages`; raises `ValueError` on 401/403/unexpected/network error
- [x] `fetch_costs()`: paginated via `_paginate()` with `next_page` cursor; yields `NormalizedUsageEvent` per model-hour bucket; `_compute_cost()` uses pricing.yaml rates for input/output/cache-read tokens; maps `cache_read_input_tokens` → `cached_tokens`; preserves `cache_creation_input_tokens` in `raw_meta`; skips zero-cost zero-token rows
- [x] 19 tests in `tests/test_anthropic_adapter.py`

**Group B - Cost Explorer**
- [x] `GET /usage/explore` - queries `daily_cost_summaries`; groups by provider/model/feature_tag/team_tag/customer_tag/env_tag; optional provider filter; returns `list[ExploreRow]` with `pct_of_total`
- [x] `ExploreRow` schema: `group_value`, `total_cost_usd`, `total_requests`, `pct_of_total`
- [x] Cost Explorer page at `/cost-explorer` - server component with validated query params
- [x] `ExploreControls` client component - Group By + Range + Provider dropdowns; updates URL params
- [x] `ExploreTable` component - TanStack Table; sortable columns; `% of total` column; totals row
- [x] 21 tests in `tests/test_usage_routes.py`

**Group C - Tag System**
- [x] `tag_engine.py` - `CompiledRule` dataclass; `compile_rules()` (filters disabled, parses PostgREST join, sorts by priority); `_matches()` (exact/substring/regex with invalid-regex safety); `apply_rules()` (first match per type, early exit at 4 assigned)
- [x] Tags CRUD: `GET/POST/PATCH/DELETE /tags` - 409 on duplicate, 404 on missing, cascade delete propagates to rules
- [x] Tag Rules CRUD: `GET/POST/PATCH/DELETE /tag-rules` - tag_id ownership check on create; list includes embedded tag info via PostgREST join
- [x] `POST /tag-rules/preview` - dry-run against last 7 days of `usage_events`; reuses `_matches()`; returns up to 20 deduplicated `{api_key_label, provider, model}` tuples
- [x] Tag engine wired into `_ingest_window()` - rules compiled once per window, applied per event, results spread into row dict via `**apply_rules(...)`
- [x] `/settings/tags` page - `TagsClient` with tag CRUD + rule CRUD + preview; color badges per tag type; empty states
- [x] 28 tests in `tests/test_tag_engine.py` + 16 tests in `tests/test_tag_routes.py` = 44 tag tests

**Group D - Gemini Adapter**
- [x] `GeminiAdapter` (`api/adapters/gemini.py`) - `validate()` hits AI Studio models endpoint; `fetch_costs()` is no-op generator (billing deferred to V1 - no usage-reporting endpoint on AI Studio API)
- [x] 8 tests in `tests/test_gemini_adapter.py`

**Bug fixed during M2**
- [x] `integrations.py` `_ADAPTERS` dict only contained `OpenAIAdapter` - Anthropic and Gemini keys returned 422 "not yet supported"; fixed by adding `AnthropicAdapter` and `GeminiAdapter`

**Resolved open questions**
- Anthropic Admin API is not Enterprise-gated - implemented using standard `x-api-key` header
- Gemini AI Studio API has no usage-reporting endpoint; Cloud Billing API requires OAuth2 (different auth model) - key validation ships in M2, cost collection deferred to V1

---

### M1 - First Integration + First Chart ✅ (verified 2026-05-19)

- [x] `POST /integrations` - validate OpenAI Admin key, AES-256-GCM encrypt (BYTEA `\x`-prefixed hex), insert, audit log, enqueue backfill
- [x] `GET /integrations` - list active integrations (key redacted, never returned)
- [x] `DELETE /integrations/:id` - soft-revoke (status=revoked), audit log
- [x] OpenAI adapter (`adapters/openai.py`) - `GET /v1/organization/costs` + `GET /v1/organization/usage/completions`, cursor pagination with `bucket_width=1d`, `_PAGE_LIMIT=31`
- [x] Celery `backfill_integration` task - pull 30d history on key connect; triggers `aggregate_org` immediately so charts appear without waiting for nightly run
- [x] Celery `refresh_integration` task - incremental fetch since `last_synced_at`; falls back to 4h lookback if no prior sync
- [x] Celery `refresh_all_integrations` beat task - enqueues `refresh_integration` for all active integrations every 4h
- [x] Celery `aggregate_org` task - GROUP BY (day, provider, model, *_tag) → UPSERT `daily_cost_summaries`; delete-before-insert idempotency in `usage_events`
- [x] Celery `aggregate_all_orgs` beat task - enqueues `aggregate_org` for all orgs with active integrations at 00:30 UTC
- [x] `GET /usage/summary` - aggregate totals (cost, requests, tokens) for a date range from `daily_cost_summaries`
- [x] `GET /usage/timeseries` - daily cost points grouped by model; aggregates tag-split rows in Python
- [x] Pydantic schemas: `IntegrationCreate`, `IntegrationRead`, `UsageSummary`, `DailyPoint`
- [x] Settings/integrations page - server component + `IntegrationsPage` client component: connect form, integration list with status badges, revoke button
- [x] Dashboard page - server component fetches + pivots data; stat cards (30d cost/requests/tokens); `DashboardCharts` client component with Tremor `AreaChart` (30d trend) + `BarChart` (cost by model)
- [x] Windows-compatible Celery worker: `worker_pool="solo"` on `win32`, `prefork` on Linux (Railway)
- [x] 37 tests passing (37 pass, 2 skipped)

**Bugs found and fixed during M1 validation:**
- `ENCRYPTION_KEY` missing from `.env` - caused 500 on all `POST /integrations` calls
- `celery_app.py` not imported in FastAPI startup - `@shared_task` tasks bound to wrong broker (AMQP instead of Redis)
- BYTEA hex encoding: storage without `\x` prefix caused decrypt crash on read (Supabase returns `\x<hex>`)
- Celery worker crash on Windows (`ValueError: not enough values to unpack`) - billiard spawn model; fixed with `solo` pool
- `_PAGE_LIMIT = 180` exceeded OpenAI hourly bucket max of 168 - then corrected to 31 when `bucket_width` changed to `1d`

---

### M0 - Foundation ✅ (verified 2026-05-19)

- [x] Full monorepo scaffold (Next.js 14 + FastAPI + packages + infra)
- [x] All config files, dependency manifests, folder structure
- [x] Python venv + Node.js dependencies installed
- [x] Initial DB migration - all tables, indexes, RLS policies
- [x] `pricing.yaml` with current model prices
- [x] Clerk JWT verification in `deps.py` (`_require_org`) - RS256 JWKS, extracts user_id + org_id
- [x] Clerk webhook handler (`/api/webhooks/clerk`) - user, org, membership sync + `db_id` write-back to Clerk metadata
- [x] `clerk_id` columns migration applied to Supabase (`infra/migrations/20260519000000_add_clerk_id_to_identity_tables.sql`)
- [x] Clerk middleware at `apps/web/src/middleware.ts` - route protection active
- [x] `/sign-in` and `/sign-up` pages (Clerk components)
- [x] `/create-org` page - org creation flow (`<CreateOrganization />`)
- [x] `/dashboard` gated by auth + org - redirects to `/create-org` if no active org
- [x] Dashboard sidebar (nav links + `<OrganizationSwitcher />`) and header (`<UserButton />`)
- [x] Supabase server client injects Clerk HS256 JWT for RLS
- [x] Two-tenant SQL probe passes (`infra/scripts/smoke-test.sql` - requires `SET LOCAL ROLE authenticated`)
- [x] End-to-end verified: two real users, two real orgs, RLS isolation confirmed

---

## Upcoming Milestones

| Milestone | Focus | Days |
|---|---|---|
| M3 | Anomaly detection + budgets + Slack + recommendations | 11 |
| M4 | Billing + CFO PDF + polish + landing page | 9 |

---

## Open Questions (M3)

1. **Slack app credentials** - create Slack app in dev workspace before starting Group C; requires redirect URI for OAuth callback (**blocking for Group C**)
2. ~~Resend sender domain - confirm verified sender domain before Group B email alerts~~ - **resolved**: `resend_api_key` + `from_email` already in `config.py`; Group B email alerts ship with existing config
3. ~~Budget reset cycle - calendar month vs rolling 30 days~~ - **resolved**: calendar month; implemented as `date_trunc('month')` comparison
4. ~~Recommendation confidence scoring - categorical vs numeric~~ - **resolved**: `high/medium/low` categorical for M3

---

## Known Debt

See `architecture.md` § Known V1 debt.

**Remaining known gaps (documented, not yet fixed in production):**
- Gap-02/05/08/10 - No distributed Redis lock on concurrent `aggregate_org`, `refresh_integration`, `detect_org`, or `check_org` tasks. Tests document the race; fix requires a Redis `SET NX EX` lock wrapper in each worker.
- Gap-11/12/13/14 - JWT `alg:none` is rejected but JWKS concurrent refresh race and unknown-kid forced-refresh path have edge cases. Tests document current behavior; full fix requires a thread-safe JWKS cache.
- Gap-23 - `send_slack_digest` has a TOCTOU race: Slack post can succeed but `slack_digests` INSERT can fail, leaving no idempotency record. Test documents the window; fix requires wrapping both operations in a DB transaction.
