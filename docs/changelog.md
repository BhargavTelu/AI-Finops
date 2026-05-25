# Changelog

All notable changes to SpendOps AI.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased] — M3 Group D in progress

---

## [0.5.1] — Gap Analysis & Test Hardening (2026-05-22)

324 tests passing, 2 skipped. 103 new gap-coverage tests across 11 new test files.

### Added

**Gap test suite** — 29 documented gaps covered by 103 test functions across 11 new files:

- `tests/test_aggregation_worker.py` — Gap-01 (happy path), Gap-02 (concurrent race), Gap-03 (pagination termination), Gap-04 (NULL/empty tag coalescing)
- `tests/test_ingestion_gaps.py` — Gap-05 (concurrent refresh race), Gap-06 (partial batch failure guard), Gap-07 (`refresh_all_integrations` dispatch)
- `tests/test_worker_race_conditions.py` — Gap-08 (anomaly detection concurrent race), Gap-09 (dedup guard blocks double-insert), Gap-10 (budget check concurrent race)
- `tests/test_deps_jwt.py` — Gap-11 (`alg:none` and HS256 algorithm confusion), Gap-12 (JWKS concurrent refresh race), Gap-13 (unknown `kid` forced-refresh), Gap-14 (JWKS fetch timeout), Gap-15 (malformed `o` claim → 403 not 500)
- `tests/test_open_bugs.py` — Gap-16 (BUG-02: `.single()` raises on missing row), Gap-17 (BUG-03: `lstrip` vs `removeprefix` semantics)
- `tests/test_adapter_gaps.py` — Gap-18 (OpenAI two-pass failure), Gap-19 (provider 429 raises `ValueError`), Gap-20 (Anthropic adapter basic coverage), Gap-21 (pagination stops on `has_more=False`)
- `tests/test_tag_engine_security.py` — Gap-22 (ReDoS completes < 5s, invalid regex → `False`)
- `tests/test_notification_gaps.py` — Gap-23 (digest idempotency TOCTOU race documented), Gap-24 (Resend failure blocks Slack; no admin email returns early)
- `tests/test_route_gaps.py` — Gap-25 (Slack OAuth missing `team` key), Gap-26 (cascade delete failure → still 204)
- `tests/test_webhook_gaps.py` — Gap-27 (Svix multiple signatures: first-valid-wins, all-invalid → 400)
- `tests/test_config_gaps.py` — Gap-28 (encryption key validated at `EncryptionService.__init__`), Gap-29 (CORS plain string raises `JSONDecodeError`)

### Fixed

**Production code**

- **`routers/webhooks.py` — `_handle_membership_created` unhandled exception (Gap-16/BUG-02)**
  - `.single().execute()` raised `PGRST116` when no row existed; exception propagated as 500 from the wrong place (a downstream `KeyError` on `data["id"]` rather than the intended `HTTPException`)
  - Wrapped both `.single().execute()` calls in `try/except`; raises `HTTPException(500)` immediately on any exception so Svix retries delivery
  - Added `isinstance(data, dict) and "id" in data` guard: catches the PostgREST error-dict case (non-empty dict that is truthy but has no `"id"` key)

- **`routers/slack.py` — `slack_resp["team"]["id"]` `KeyError` (Gap-25)**
  - Direct key access raised `KeyError → 500` when Slack omitted the `team` field (e.g., misconfigured OAuth scopes)
  - Changed to `slack_resp.get("team") or {}` + `.get("id", "")` with an explicit `HTTPException(400, "Slack response missing workspace info.")` when `workspace_id` is empty
  - Now returns 400 instead of 500, matching the behavior for the already-handled missing `channel_id` case

- **`services/encryption.py` — `binascii.Error` not caught (Gap-28)**
  - `base64.b64decode()` raised `binascii.Error("Incorrect padding")` for malformed keys; error message did not match the descriptive error pattern expected by callers
  - Wrapped decode in `try/except Exception`; re-raises as `ValueError(f"Encryption key must be valid base64: {exc}")` so all key-validation errors are consistently `ValueError` with a descriptive message

- **`packages/pricing/pricing.yaml` — missing Claude 3.5 models (Gap-20)**
  - `claude-3-5-sonnet-20241022` and `claude-3-5-haiku-20241022` absent from the Anthropic section; `_compute_cost()` silently returned `Decimal("0")` for these widely-used models
  - Added both at current public pricing: Sonnet at $3.00/$15.00/$0.30 per MTok, Haiku at $0.80/$4.00/$0.08 per MTok

---

## [0.5.0] — M3 Group C: Slack Integration (2026-05-21)

221 tests passing, 2 skipped. 0 TypeScript errors in new files.

### Added

**Slack OAuth + Status + Disconnect API** (`api/routers/slack.py` — new file)
- `GET /slack/status` — returns `SlackStatusResponse` (`connected`, `workspace_id`, `channel_name`, `channel_id`, `installed_at`); returns `{connected: false}` when no row exists
- `POST /slack/oauth/callback` — receives `{code, state}` from frontend; calls `slack_client.exchange_code()` to swap for bot token; validates that `incoming_webhook.channel_id` is present (HTTP 400 if missing); AES-256-GCM encrypts the bot token; upserts `slack_integrations` row with `on_conflict="org_id"` so reconnecting to a different channel replaces the existing row; resolves `installed_by` UUID from Clerk user_id before insert
- `POST /slack/disconnect` — revokes bot token via `slack_client.revoke_token()` (best-effort; DB row always deleted even if Slack revocation fails); deletes `slack_integrations` row; 404 if not connected

**Slack Client Service** (`api/services/slack_client.py` — new file)
- `exchange_code(code, client_id, client_secret, redirect_uri)` — `POST https://slack.com/api/oauth.v2.access`; raises `ValueError` on `ok=false`
- `revoke_token(bot_token)` — `POST https://slack.com/api/auth.revoke`; best-effort (logs warning, does not raise)
- `post_message(bot_token, channel_id, blocks, fallback_text)` — `POST https://slack.com/api/chat.postMessage`; raises `ValueError` on `ok=false` for Celery retry; 10s timeout via `httpx` (no Slack SDK — avoids large dependency)

**Pydantic Schemas** (`api/schemas/slack.py` — new file)
- `SlackOAuthCallbackBody` — `code: str`, `state: str` (CSRF token = Clerk org_id)
- `SlackStatusResponse` — `connected: bool`; optional `workspace_id`, `channel_name`, `channel_id`, `installed_at`

**Daily Digest Worker** (`api/workers/notifications.py` — implemented from stub)
- `send_daily_digests()` — fan-out `@shared_task`; queries all orgs with a `slack_integrations` row; dispatches `send_slack_digest.delay(org_id)` per org; logs dispatch count
- `send_slack_digest(org_id)` — per-org task with `max_retries=2`; idempotency guard via `slack_digests` table (UNIQUE on `org_id, digest_date`) — skips if already sent today; retrieves and decrypts bot token; calls `_fetch_digest_data()` then `_digest_slack_blocks()`; records row in `slack_digests` on success; retries on Slack `ValueError`
- `_fetch_digest_data(db, org_id, yesterday)` — 4 queries: (1) 7-day window with model breakdown → yesterday total + 7d avg + top-3 cost drivers; (2) this-month MTD; (3) last-month same day range (MoM %); (4) open anomaly count; MoM returns `None` if no prior-month data
- `_digest_slack_blocks(digest_date, yesterday_usd, avg_7d_usd, mom_pct, top_drivers, open_anomaly_count)` — Slack Block Kit payload: header with date, fields for spend + MoM + 7d avg, top-driver bullets, anomaly count, fallback text for mobile

**Real-time Anomaly Alert** (`api/workers/notifications.py` + `api/workers/anomaly_detection.py`)
- `send_anomaly_alert(anomaly_id)` — `@shared_task` with `max_retries=3`; fetches anomaly row + org Slack channel; skips silently if anomaly or Slack not found; posts Block Kit message with severity emoji (🟡/🟠/🔴), spike %, baseline, actual, model name, and tag context when set
- `_anomaly_slack_blocks()` — severity-keyed header; fields: Spike%, Baseline/day, Actual, Severity; context block appended when any tag is non-null
- Wire-up in `detect_org` (`anomaly_detection.py`): calls `send_anomaly_alert.delay(anomaly_id)` when `severity in ("medium", "high")` after inserting anomaly row

**Real-time Budget Slack Alert** (`api/workers/notifications.py`)
- `send_budget_alert` updated — after Resend email, makes a best-effort Slack post; Slack failure does not trigger retry (email is authoritative)
- `_budget_slack_blocks()` — `:warning:` or `:red_circle:` header; fields: scope label, limit, MTD spend, % used
- `_scope_label()` — human-readable scope text ("Global", "Provider: openai", "Feature tag: chat", etc.)

**Settings layout + tab nav** (`apps/web/src/app/(dashboard)/settings/`)
- `layout.tsx` — server layout wrapping all settings sub-pages with `SettingsTabs`
- `settings-tabs.tsx` — "use client" tab nav: Integrations / Tag Rules / Slack; `usePathname()` drives active border; typed with `as Route<string>` cast (same pattern as `nav-links.tsx`)

**Frontend `/settings/slack` page** (`apps/web/src/app/(dashboard)/settings/slack/`)
- `page.tsx` — server component; fetches `GET /slack/status`; builds full Slack OAuth URL server-side from `SLACK_CLIENT_ID` + `SLACK_REDIRECT_URI` env vars (avoids `NEXT_PUBLIC_` exposure); passes `successMsg`/`errorMsg` from `searchParams` as props
- `slack-client.tsx` — connected state: workspace ID, channel name, installed date; Reconnect link + Disconnect button (`POST /slack/disconnect`); disconnected state: empty state with `#` icon + "Connect Slack" CTA or unconfigured warning; "What you'll receive" feature list; `PageMotion` Framer Motion wrapper
- `loading.tsx` — `animate-pulse` Skeleton matching connected-state layout
- `callback/page.tsx` — server component OAuth callback; reads `code`/`state`/`error` from `searchParams`; calls `POST /slack/oauth/callback`; redirects to `/settings/slack?connected=true` on success or `/settings/slack?error=<message>` on failure

**TypeScript types** (`apps/web/src/lib/types.ts`)
- `SlackStatus` interface: `connected: boolean`; optional `workspace_id`, `channel_name`, `channel_id`, `installed_at`

**Environment variables** (`apps/web/.env.local.example`)
- `SLACK_CLIENT_ID` — OAuth app client ID (server-side only)
- `SLACK_REDIRECT_URI` — defaults to `http://localhost:3000/settings/slack/callback`

**Unit tests — 50 new tests across 3 files**
- `tests/test_slack_routes.py` (9 tests): `TestSlackStatus` — not connected, connected with full fields; `TestSlackOAuthCallback` — successful connect, exchange error → 400, no channel → 400, unconfigured server → 503; `TestSlackDisconnect` — deletes row, not-connected → 404
- `tests/test_notifications_slack.py` (19 tests): `TestAnomalySlackBlocks` (6) — severity emojis, spike/value fields, tag context block present/absent, medium/high/low variants; `TestBudgetSlackBlocks` (3) — warning/exceeded headers, scope + amounts; `TestGetSlackChannel` (3) — None when not connected, returns decrypted token+channel, None on decrypt error; `TestSendAnomalyAlert` (4) — posts when connected, skips on missing anomaly, skips on missing Slack, uses correct channel; `TestSendBudgetAlertSlack` (3) — posts to Slack when connected, skips gracefully when not connected, Slack failure does not raise
- `tests/test_notifications_digest.py` (22 tests): `TestDigestSlackBlocks` (6) — date in header, spend in fields, MoM positive/negative/absent, top-driver bullets; `TestFetchDigestData` (8) — yesterday total, 7d avg, top-3 driver sort, MoM math, open anomaly count; `TestSendDailyDigests` (2) — dispatches per connected org, no dispatch if none; `TestSendSlackDigest` (6) — posts digest, skips missing Slack, idempotency guard, records in `slack_digests`, Slack failure retries

### Fixed

- **`send_anomaly_alert` never wrote `anomalies.notified_at`**: the `notified_at` column exists in the `anomalies` schema to record when the Slack alert was sent, but the task exited after `post_message` without writing it. Fixed: after a successful `post_message`, the task now updates `anomalies.notified_at = now()` (best-effort; a failed DB write logs a warning but does not re-raise). Two tests updated to account for the additional `execute()` call.
- **`TypeError: unsupported operand type(s) for +=: 'list_iterator' and 'list'`** in `test_slack_failure_retries`: once `MagicMock.side_effect` is assigned a list, Python converts it to a `list_iterator`; appending with `+=` raises `TypeError`. Fixed by building the complete side-effect list upfront (`one_attempt * 3`) before assigning to the mock.

---

## [0.4.1] — M3 Group B: Budgets + Email Alerts (2026-05-21)

171 tests passing, 2 skipped. 0 TypeScript errors.

### Added

**Database migration** (`infra/migrations/20260521000000_fix_budgets_schema.sql`)
- Fixed `budgets.scope_type` CHECK constraint — original migration only allowed `('global', 'tag', 'model')`; corrected to the full spec enum: `('global', 'provider', 'model', 'feature_tag', 'team_tag', 'customer_tag', 'env_tag')`
- Added `notified_80_at TIMESTAMPTZ` and `notified_100_at TIMESTAMPTZ` columns on `budgets` — tracks when each threshold alert was last sent; `NULL` = never notified; guard checks `date_trunc('month')` equality to allow one alert per threshold per calendar month

**Budget Pydantic schemas** (`api/schemas/budgets.py`)
- `BudgetScopeType` — `Literal` with all 7 scope values
- `BudgetCreate` — `scope_type`, `scope_value` (required for all non-global types, 422 if missing), `monthly_limit` (`Decimal`, `gt=0`), `alert_at_pct` (default 80, 1–100), `hard_cap` (bool, default False)
- `BudgetUpdate` — partial: `monthly_limit` and/or `alert_at_pct` only; 422 if both absent
- `BudgetRead` — all stored fields plus `current_spend_mtd: Decimal` and `spent_pct: int` computed at read time by the route handler

**Budget CRUD routes** (`api/routers/budgets.py`)
- `GET /budgets` — lists all org budgets ordered by `created_at DESC`; computes MTD spend per budget scope by summing `daily_cost_summaries` for the current calendar month
- `POST /budgets` — application-level uniqueness check (409 on duplicate `(org_id, scope_type, scope_value)`); `scope_value` forced `NULL` for global type
- `PATCH /budgets/:id` — ownership check (404 on wrong org); updates `monthly_limit` and/or `alert_at_pct`; 422 if no fields provided
- `DELETE /budgets/:id` — ownership check (404 on wrong org); 204 on success
- MTD spend computed by `_compute_scope_spend()` helper — selects from `daily_cost_summaries` for the current calendar month with scope-type-specific column filter

**Budget check worker** (`api/workers/budget_checks.py` — new file)
- `check_all_orgs()` — `@shared_task`; queries all orgs with at least one budget; dispatches `check_org.delay(org_id)` per unique org; logs dispatch count
- `check_org(org_id)` — for each budget: computes MTD scope spend; at 100%+ fires `send_budget_alert.delay(budget_id, 100, org_id)` + writes `notified_100_at`; always `continue`s (never falls through to warning check); at `alert_at_pct`+ fires `send_budget_alert.delay(budget_id, pct, org_id)` + writes `notified_80_at`; both guarded by `_same_calendar_month()` to prevent re-alerts within the same month
- `_same_calendar_month(ts_str)` — pure helper; `None`, empty string, and malformed dates return `False`; compares `(year, month)` against current UTC time; handles `Z` suffix in ISO strings
- `_compute_scope_spend(db, org_id, scope_type, scope_value)` — sums `total_cost_usd` from `daily_cost_summaries` for current calendar month with scope-appropriate `eq()` filter; `global` scope applies no additional filter

**send_budget_alert task** (`api/workers/notifications.py` — stub implemented)
- Fetches budget row and org admin email (via `organization_members` role='admin' → `users.email`, oldest member = org owner)
- Calls Resend API with HTML email; subject and template differ by threshold:
  - 80% warning: amber-accented table with scope, limit, MTD spend, % used
  - 100% exceeded: red-accented table with same fields; subject prefixed "Budget exceeded"
- Retries up to 3× on Resend failure via `self.retry(exc=exc)`
- Logs `budget_alert_sent` / `budget_alert_send_failed` / `budget_alert_no_admin_email` / `budget_alert_budget_not_found`

**Celery beat schedule** (`api/workers/celery_app.py`)
- `check-budgets`: `check_all_orgs` at 02:00 UTC (after aggregation at 00:30 and anomaly detection at 01:00)
- `api.workers.budget_checks` added to `include` list

**Frontend `/budgets` page** (`apps/web/src/app/(dashboard)/budgets/`)
- `page.tsx` — server component; fetches `GET /budgets` with Clerk token; passes `initialBudgets` to client; catch-all on error returns empty list
- `budgets-client.tsx` — `BudgetsClient` component with:
  - Budget table: Scope, Monthly limit, MTD spend, Usage (progress bar), Alert at, Actions columns
  - Progress bar (`SpendBar`): green < alert threshold, amber at warning, red at 100%+
  - MTD spend cell coloured red (exceeded) or amber (warning) using the same thresholds
  - Exceeded counter banner ("N budgets exceeded this month") shown when `spent_pct >= 100`
  - Add Budget dialog with: scope type selector, conditional scope value input (hidden for global), monthly limit input, alert threshold input with explanatory hint text; 409 and validation errors shown inline
  - Inline delete with two-step confirmation (Yes / No) per row; optimistic removal on success
  - Empty state with CTA button that opens the Add Budget dialog
  - Framer Motion `AnimatePresence` + `motion.tr` for row enter/exit animations
- `loading.tsx` — shadcn Skeleton matching 4-row × 6-column table structure

**TypeScript types** (`apps/web/src/lib/types.ts`)
- `BudgetScopeType` union type
- `BudgetRead` interface with all fields including computed `current_spend_mtd` and `spent_pct`

**Unit tests**
- `tests/test_budget_checks.py` (24 tests):
  - `TestSameCalendarMonth` (6): None, empty string, current month, previous month, Z-suffix, malformed string
  - `TestComputeScopeSpend` (6): global sums all rows, empty returns zero, provider eq call, model eq call, feature_tag scope, multiple rows summed
  - `TestCheckOrg` (12): below threshold no alert, at 80% fires, over 80% fires, at 100% fires exceeded not warning, over 100% fires exceeded, 80% guard same month, 100% guard same month, new month allows re-alert, no budgets early return, `notified_80_at` written after alert, zero-limit skipped, custom alert threshold
- `tests/test_budget_routes.py` (16 tests):
  - `TestListBudgets` (3): empty list, returns budget with computed spend, 100% spend reported correctly
  - `TestCreateBudget` (7): global budget, model without scope_value → 422, model with scope_value, duplicate → 409, negative limit → 422, zero limit → 422, all 7 scope types accepted
  - `TestUpdateBudget` (3): update limit, wrong org → 404, empty body → 422
  - `TestDeleteBudget` (2): delete own → 204, wrong org → 404

### Fixed

- **`check_org` double-alert bug**: when `notified_100_at` was already set for the current month, the `continue` statement was inside the inner `if not _same_calendar_month(...)` block — so a guarded 100% budget still fell through to the 80% threshold check and fired a spurious warning alert. Fixed by moving `continue` unconditionally outside the guard: whenever `spent_pct >= 100`, skip the warning check regardless of whether the 100% alert was sent. Caught by `test_100pct_guard_prevents_resend_same_month`.

---

## [0.4.0] — M3 Group A: Anomaly Detection (2026-05-21)

131 tests passing, 2 skipped. 0 TypeScript errors.

### Added

**Anomaly Detection Worker** (`api/workers/anomaly_detection.py`)
- `detect_all_orgs` Celery task — queries all orgs with active integrations; dispatches `detect_org.delay(org_id)` per unique org; logs dispatch count
- `detect_org` Celery task — for each distinct (model, feature_tag, team_tag, customer_tag) group in `daily_cost_summaries`: fetches 15 days of history in one query; sums costs per day across providers; fills date gaps with $0; calls `services.anomaly.detect_anomalies(history)`; inserts anomaly row to DB on detection; deduplicates by checking open anomalies already detected today for the same scope; enqueues `send_anomaly_alert.delay(anomaly_id)` for severity ≥ medium (Group C implements the alert body)
- `scope_kind = "model"`, `scope_value = model_name`; tag context (feature_tag, team_tag, customer_tag) stored in `context` jsonb alongside spike details
- Beat schedule was already wired at 01:00 UTC in `celery_app.py` — no change required

**Anomaly API Routes** (`api/routers/anomalies.py`)
- `GET /anomalies?status=open|acked|dismissed` — queries `anomalies` table filtered by org + status; ordered by `detected_at DESC`; returns `list[AnomalyRead]`; status validated as `Literal` type (not raw string)
- `PATCH /anomalies/:id` — ownership check (404 if anomaly not in org); updates `status` to `acked` or `dismissed`; returns updated `AnomalyRead`

**Frontend `/anomalies` page** (`apps/web/src/app/(dashboard)/anomalies/`)
- `page.tsx` — server component; validates `?status` URL param against allowlist; fetches `/anomalies?status=<status>` with Clerk token; passes to client
- `anomalies-client.tsx` — status tabs (Open / Acknowledged / Dismissed) updating URL via `router.push`; anomaly table with columns: Time, Scope, Spike%, Baseline/day, Actual, Severity, Actions; Ack + Dismiss buttons calling `PATCH /anomalies/:id`; optimistic removal from current tab on update; error banner with dismiss; empty state per tab
- Severity badges: low = amber, medium = orange, high = red (dark-mode aware)
- `loading.tsx` — shadcn Skeleton skeleton matching table structure (5 rows, 7 columns)

**TypeScript types** (`apps/web/src/lib/types.ts`)
- `AnomalyRead`, `AnomalySeverity`, `AnomalyStatus` added

**Unit tests** (`tests/test_anomaly.py` — extended to 11 tests)
- `test_low_severity_at_two_sigma_boundary` — z in [2, 3) → severity `"low"`
- `test_medium_severity_at_three_sigma_boundary` — z in [3, 4) → severity `"medium"`
- `test_spike_pct_zero_when_mean_is_zero` — mean=0 edge case; no divide-by-zero
- `test_returns_correct_baseline_and_actual_usd` — Decimal values preserved correctly
- `test_exactly_fifteen_data_points_is_sufficient` — minimum data length boundary

**Worker tests** (`tests/test_anomaly_detection.py` — 9 tests, new file)
- `TestDetectOrg`: spike detected → insert called; flat baseline → no insert; actual below $10 floor → no insert; insufficient history → no insert; open anomaly today → dedup skip; no data → early exit; scope fields on insert
- `TestDetectAllOrgs`: dispatches per unique org (deduplicates repeated org_id); no dispatch on empty integrations

### Fixed

- **`first_day` off-by-one**: computed as `today - 14` (producing a 14-item history list); `detect_anomalies()` requires ≥15 items and always returned `None`. Fixed to `today - _HISTORY_DAYS` (`today - 15`). Bug caught by worker unit tests before any data hit the DB.

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
