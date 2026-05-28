# Test Plan - SpendOps AI (M0–M3 Pre-M4 Audit)

**Prepared:** 2026-05-24
**Scope:** Full audit of M0 through M3. This document covers the complete test surface:
existing coverage is summarised, and every **missing/gap test case is identified and specified**.
Only gap tests (marked `NEW`) need to be written. Do not re-write existing tests.

**Existing suite baseline:** 559 test functions across 47 test files in `apps/api/tests/`.

---

## How to read this document

| Column | Meaning |
|--------|---------|
| `TC-ID` | Unique test case identifier. New IDs continue the series used in the existing suite. |
| `Layer` | UNIT = pure-function / no-HTTP, INTG = mocked HTTP routes, E2E = live staging |
| `Status` | **NEW** = gap test to write · **EXISTS** = already in the suite |
| `Priority` | **CRITICAL** = blocks production · **HIGH** = correctness risk · **MEDIUM** = important but not blocking |
| `File` | Target file for new tests |

---

## Part 1 - Existing Coverage Summary

The following areas have solid test coverage. These are **not** re-specified below.

| Area | Primary test files | Approx. count |
|------|--------------------|---------------|
| Encryption service (AES-256-GCM) | `test_encryption.py`, `test_security_boundaries.py`, `test_config_gaps.py` | 15 |
| Tag engine (compile, apply, match, security) | `test_tag_engine.py`, `test_tag_engine_security.py` | 30 |
| Anomaly detection algorithm (2σ, floors, severity) | `test_anomaly.py`, `test_anomaly_detection.py`, `test_anomaly_edge_cases.py` | 25 |
| Anomaly worker (detect_org, detect_all_orgs, dedup) | `test_anomaly_detection.py`, `test_detection_severity_alerts.py` | 20 |
| Budget CRUD routes | `test_budget_routes.py`, `test_budget_routes_extended.py` | 25 |
| Budget check worker (check_org, thresholds, guards) | `test_budget_checks.py` | 20 |
| Slack routes (OAuth, status, disconnect) | `test_slack_routes.py`, `test_slack_routes_extended.py` | 20 |
| Slack client service (exchange_code, revoke, post) | `test_slack_client_service.py` | 12 |
| Slack mute + anomaly explainer | `test_slack_mute_and_explainer.py` | 15 |
| Notification builders (Slack Block Kit) | `test_notifications_builders.py` | 15 |
| Notification digest worker | `test_notifications_digest.py` | 20 |
| Budget alert notifications | `test_notifications_budget_alert.py` | 15 |
| Recommendations engine (model_swap, caching, batch) | `test_recommendations.py` | 35 |
| Pricing YAML (structure, math) | `test_pricing_new.py` | 5 |
| OpenAI adapter (fetch_costs, pagination, costs) | `test_openai_adapter.py` | 25 |
| Anthropic adapter (fetch_costs, pagination, costs) | `test_anthropic_adapter.py`, `test_anthropic_header.py` | 20 |
| Gemini adapter (fetch_costs, pagination) | `test_gemini_adapter.py` | 15 |
| Ingestion worker (backfill, refresh, override) | `test_ingestion_workers.py`, `test_workers.py` | 30 |
| Ingestion gaps (race condition, partial batch) | `test_ingestion_gaps.py` | 8 |
| Aggregation worker | `test_aggregation_worker.py` | 10 |
| Dashboard endpoint | `test_dashboard_endpoint.py` | 15 |
| Usage routes (summary, timeseries, explore, events) | `test_usage_routes.py` | 30 |
| Usage tag override (admin endpoint) | `test_usage_override.py` | 15 |
| Integration routes (create, list, delete) | `test_integration_routes.py`, `test_security_boundaries.py` | 15 |
| Tag CRUD routes + preview | `test_tag_routes.py` | 12 |
| Anomaly routes (list, patch) | `test_anomaly_routes.py` | 8 |
| Clerk webhook (signature verify, user/org/member) | `test_webhooks_clerk.py` | 15 |
| JWT / deps auth | `test_deps_jwt.py` | 12 |
| Security boundaries (cross-org, unauthenticated) | `test_security_boundaries.py` | 10 |
| Worker race conditions (concurrent tasks) | `test_worker_race_conditions.py` | 8 |
| Open bugs (BUG-02, BUG-03) | `test_open_bugs.py` | 6 |
| Route gaps (Gap-25, Gap-26) | `test_route_gaps.py` | 7 |
| Config gaps (Gap-28, Gap-29) | `test_config_gaps.py` | 6 |
| Webhook gaps (Svix signature edge cases) | `test_webhook_gaps.py` | 6 |
| E2E M1 happy path | `test_e2e_m1.py` | 8 |

---

## Part 2 - Gap Test Cases (NEW - need to be written)

### Section A · Stub / NotImplementedError Routes

These routes currently raise `NotImplementedError`, which FastAPI converts to an unhandled 500.
Before M4 ships, each stub must be covered with a regression test that documents the current
behavior **and** the expected post-implementation behavior. When the route is implemented,
the test assertion is updated from `!= 200` / `500` to the correct success code.

---

#### TC-STUB-01
| Field | Value |
|-------|-------|
| **TC-ID** | TC-STUB-01 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_stub_routes.py` (new file) |
| **Component** | `POST /integrations/:id/test` |
| **Scenario** | Call the endpoint with a valid auth token. The route body is `raise NotImplementedError`. |
| **Expected Result** | Response is `500`. When implemented: `200` with a `{"status": "ok"}` or similar confirmation. |
| **Notes** | This is a critical M4 pre-condition. If it silently 500s it may confuse users trying to retest a connection. |

---

#### TC-STUB-02
| Field | Value |
|-------|-------|
| **TC-ID** | TC-STUB-02 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_stub_routes.py` |
| **Component** | `GET /usage/forecast` |
| **Scenario** | Call the endpoint with valid auth. Route raises `NotImplementedError`. |
| **Expected Result** | Response is `500`. When implemented (M4 FR-24): `200` with `ForecastResult` schema including `projected_eom_usd`, `confidence_interval`, and insufficient-data flag. |

---

#### TC-STUB-03
| Field | Value |
|-------|-------|
| **TC-ID** | TC-STUB-03 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_stub_routes.py` |
| **Component** | `GET /usage/export.csv` |
| **Scenario** | Call the endpoint with valid auth. Route raises `NotImplementedError`. |
| **Expected Result** | Response is `500`. When implemented (M4 FR-23): `200` with `Content-Type: text/csv` and a dated filename in `Content-Disposition`. |

---

#### TC-STUB-04
| Field | Value |
|-------|-------|
| **TC-ID** | TC-STUB-04 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | CRITICAL |
| **File** | `tests/test_stub_routes.py` |
| **Component** | `GET /billing`, `POST /billing/checkout`, `GET /billing/portal` |
| **Scenario** | Call each billing endpoint with valid auth. All three raise `NotImplementedError`. |
| **Expected Result** | Each returns `500`. When implemented (M4 FR-21): `GET /billing` → 200 with plan/status; `POST /billing/checkout` → 200 with Stripe redirect URL; `GET /billing/portal` → 200 with portal URL. |
| **Notes** | Billing is the M4 monetization gate. All three stubs must pass before M4 ships. |

---

#### TC-STUB-05
| Field | Value |
|-------|-------|
| **TC-ID** | TC-STUB-05 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | CRITICAL |
| **File** | `tests/test_stub_routes.py` |
| **Component** | `POST /webhooks/stripe` |
| **Scenario** | POST to the endpoint with a mock Stripe-Signature header. Route raises `NotImplementedError`. |
| **Expected Result** | Response is `500`. When implemented (M4): `200 {"received": true}` after verifying the signature and upserting the `billing` row. |
| **Notes** | Stripe webhooks must be verified before processing. A missing or invalid `stripe-signature` must return `400`. This gap is **critical** - M4 launch depends on it. |

---

#### TC-STUB-06
| Field | Value |
|-------|-------|
| **TC-ID** | TC-STUB-06 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_stub_routes.py` |
| **Component** | `GET /reports`, `GET /reports/:id/download`, `POST /reports/generate` |
| **Scenario** | Call each report endpoint with valid auth. All three raise `NotImplementedError`. |
| **Expected Result** | Each returns `500`. When implemented (M4 FR-22): `GET /reports` → 200 list; `GET /reports/:id/download` → 302 or 200 with signed R2 URL; `POST /reports/generate` → 202 accepted. |

---

### Section B · Worker Fan-Out Tasks (not individually tested)

These are the "dispatch to all orgs" entry-point tasks. Only per-org workers are tested;
the fan-out layer is missing.

---

#### TC-FAN-01
| Field | Value |
|-------|-------|
| **TC-ID** | TC-FAN-01 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_aggregation_worker.py` (add to existing) |
| **Component** | `workers/aggregation.aggregate_all_orgs` |
| **Scenario** | Mock Supabase to return 3 active integrations across 2 unique orgs. Call `aggregate_all_orgs()`. |
| **Expected Result** | `aggregate_org.delay()` is called exactly twice - once per unique org_id. |

---

#### TC-FAN-02
| Field | Value |
|-------|-------|
| **TC-ID** | TC-FAN-02 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_aggregation_worker.py` |
| **Component** | `workers/aggregation.aggregate_all_orgs` |
| **Scenario** | No active integrations. Call `aggregate_all_orgs()`. |
| **Expected Result** | `aggregate_org.delay()` is never called. No exception raised. |

---

#### TC-FAN-03
| Field | Value |
|-------|-------|
| **TC-ID** | TC-FAN-03 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_budget_checks.py` (add to existing) |
| **Component** | `workers/budget_checks.check_all_orgs` |
| **Scenario** | Mock Supabase to return `budgets` rows for 3 distinct org_ids. Call `check_all_orgs()`. |
| **Expected Result** | `check_org.delay()` is called exactly 3 times, once per unique org_id. |

---

#### TC-FAN-04
| Field | Value |
|-------|-------|
| **TC-ID** | TC-FAN-04 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_budget_checks.py` |
| **Component** | `workers/budget_checks.check_all_orgs` |
| **Scenario** | No budgets in DB. Call `check_all_orgs()`. |
| **Expected Result** | `check_org.delay()` is never called. No exception raised. |

---

#### TC-FAN-05
| Field | Value |
|-------|-------|
| **TC-ID** | TC-FAN-05 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_notifications_digest.py` (add to existing) |
| **Component** | `workers/notifications.send_daily_digests` |
| **Scenario** | Mock DB to return 2 Slack-connected orgs. Call `send_daily_digests()`. |
| **Expected Result** | `send_digest.delay()` (or equivalent inner task) is called exactly twice - once per org. |
| **Notes** | The per-org path is tested; this test covers the fan-out layer. |

---

### Section C · Tag Routes - Missing PATCH Endpoints

`PATCH /tags/:id` and `PATCH /tag-rules/:id` are implemented but have zero tests.

---

#### TC-TAG-10
| Field | Value |
|-------|-------|
| **TC-ID** | TC-TAG-10 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_tag_routes.py` (add to existing) |
| **Component** | `PATCH /tags/:id` |
| **Scenario** | PATCH a tag that belongs to the org with `{"name": "new-name", "color": "#ff0000"}`. DB returns updated row. |
| **Expected Result** | `200` with updated `name` and `color`. |

---

#### TC-TAG-11
| Field | Value |
|-------|-------|
| **TC-ID** | TC-TAG-11 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_tag_routes.py` |
| **Component** | `PATCH /tags/:id` |
| **Scenario** | PATCH a tag that doesn't exist (DB returns empty list). |
| **Expected Result** | `404 Tag not found`. |

---

#### TC-TAG-12
| Field | Value |
|-------|-------|
| **TC-ID** | TC-TAG-12 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_tag_routes.py` |
| **Component** | `PATCH /tag-rules/:id` |
| **Scenario** | PATCH a rule that belongs to the org with updated `match_pattern` and `priority`. DB returns updated row. |
| **Expected Result** | `200` with updated fields. |

---

#### TC-TAG-13
| Field | Value |
|-------|-------|
| **TC-ID** | TC-TAG-13 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_tag_routes.py` |
| **Component** | `PATCH /tag-rules/:id` |
| **Scenario** | PATCH a tag rule that doesn't exist (DB returns empty). |
| **Expected Result** | `404 Tag rule not found`. |

---

#### TC-TAG-14
| Field | Value |
|-------|-------|
| **TC-ID** | TC-TAG-14 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_tag_routes.py` |
| **Component** | `PATCH /tag-rules/:id` - org isolation |
| **Scenario** | Org B attempts to PATCH a tag rule that belongs to Org A. DB `eq("org_id", ...)` filter returns no rows. |
| **Expected Result** | `404` (not `403` - no info leak about the rule's existence). |

---

### Section D · Budget Routes - Untested Edge Cases

---

#### TC-BUD-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-BUD-20 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_budget_routes.py` (add to existing) |
| **Component** | `PATCH /budgets/:id` - `hard_cap` not patchable |
| **Scenario** | PATCH a budget with only `{"hard_cap": true}` (no `monthly_limit`, no `alert_at_pct`). |
| **Expected Result** | `422` with detail `"No fields to update"` - `hard_cap` is not in the patchable field set. |
| **Notes** | The current `BudgetUpdate` schema only allows `monthly_limit` and `alert_at_pct`. This tests that `hard_cap` is silently ignored and the empty-patch guard fires. |

---

#### TC-BUD-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-BUD-21 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_budget_routes.py` |
| **Component** | `_compute_mtd_spend` - `env_tag` scope |
| **Scenario** | Call `_compute_mtd_spend` with `scope_type="env_tag"` and `scope_value="production"`. Verify the query has `.eq("env_tag", "production")`. |
| **Expected Result** | Query filters by `env_tag = "production"`. Returns the sum of matching rows. |
| **Notes** | `customer_tag` and `env_tag` scopes are not individually unit-tested; the other tag scopes are. |

---

#### TC-BUD-22
| Field | Value |
|-------|-------|
| **TC-ID** | TC-BUD-22 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_budget_routes.py` |
| **Component** | `_to_budget_read` - zero `monthly_limit` guard |
| **Scenario** | Call `_to_budget_read` with a row where `monthly_limit="0.00"` and `mtd_spend=Decimal("0")`. |
| **Expected Result** | `spent_pct` = 0 (division by zero guard: `if limit else 0`). No `ZeroDivisionError` raised. |

---

### Section E · Anomaly Detection - Context Field

---

#### TC-ANO-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-ANO-20 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_anomaly_detection.py` (add to existing) |
| **Component** | `workers/anomaly_detection.detect_org` - `context` field population |
| **Scenario** | Insert mock daily summaries with `feature_tag="chat"`, `team_tag="ml"`, `model="gpt-4o"`. A spike is triggered. Check the anomaly row inserted into the DB. |
| **Expected Result** | The inserted row has a `context` dict containing at minimum `{"model": "gpt-4o", "feature_tag": "chat", "team_tag": "ml"}`. |
| **Notes** | The anomaly explainer prompt uses `context` tags for specificity. If `context` is empty, the explanation is generic and unhelpful. |

---

#### TC-ANO-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-ANO-21 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_anomaly_detection.py` |
| **Component** | `workers/anomaly_detection.detect_org` - `scope_value` field |
| **Scenario** | A spike is detected for `scope_kind="model"` with `scope_value="gpt-4o"`. |
| **Expected Result** | The inserted anomaly row has `scope_kind="model"` and `scope_value="gpt-4o"`. These are the fields used by `GET /anomalies` filters. |

---

### Section F · Usage Routes - Edge Cases

---

#### TC-USG-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-USG-20 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_usage_routes.py` (add to existing) |
| **Component** | `_parse_range` - zero-day window |
| **Scenario** | Call `_parse_range("0d")`. `days=0`, so `period_start = period_end - timedelta(days=-1) = period_end + 1 day`. |
| **Expected Result** | `period_start > period_end` (inverted range). The summary endpoint returns zeros because no days are in range. No crash. |
| **Notes** | The regex `^\d+d$` accepts "0d". The dashboard should return empty data gracefully. |

---

#### TC-USG-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-USG-21 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_dashboard_endpoint.py` (add to existing) |
| **Component** | `GET /usage/dashboard` - first day of month edge case |
| **Scenario** | Mock `datetime.now()` to return the first day of the current month. `yesterday` will be the last day of the previous month. |
| **Expected Result** | `mtd_end = yesterday < mtd_start = first of current month`. `mtd` period returns `total_cost_usd=0` and `total_requests=0`. No `ZeroDivisionError` or `ValueError`. |
| **Notes** | The `sum_range(start, end)` helper has a `if start > end: return zeros` guard. This test verifies it is exercised. |

---

#### TC-USG-22
| Field | Value |
|-------|-------|
| **TC-ID** | TC-USG-22 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_usage_routes.py` |
| **Component** | `GET /usage/explore` - `pct_of_total` when all costs are zero AND `grand_total = 0` |
| **Scenario** | DB returns rows but all have `total_cost_usd = 0`. |
| **Expected Result** | `pct_of_total = 0.0` for all rows (denominator guard: `if grand_total else 0.0`). No `ZeroDivisionError`. |
| **Notes** | The guard exists in the code but is not independently tested. `test_pct_of_total_zero_when_all_costs_zero` tests empty DB; this tests zero-cost rows. |

---

### Section G · Health Endpoint

---

#### TC-HLTH-01
| Field | Value |
|-------|-------|
| **TC-ID** | TC-HLTH-01 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | CRITICAL |
| **File** | `tests/test_health.py` (new file) |
| **Component** | `GET /health` |
| **Scenario** | GET `/health` with no auth token. |
| **Expected Result** | `200 {"status": "ok"}`. No auth required (health checks are public). |
| **Notes** | Railway and any load balancer health probes hit this endpoint. If it requires auth, the app will be removed from rotation. |

---

#### TC-HLTH-02
| Field | Value |
|-------|-------|
| **TC-ID** | TC-HLTH-02 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_health.py` |
| **Component** | `GET /health` - route prefix |
| **Scenario** | GET `/health` (no `/api/v1` prefix). Verify it is NOT behind the `/api/v1` router group. |
| **Expected Result** | `200`. The health endpoint must remain accessible at the root path even if the API prefix changes. |

---

### Section H · Webhook - Stripe Stub & Clerk Edge Cases

---

#### TC-WH-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-WH-20 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | CRITICAL |
| **File** | `tests/test_webhooks_clerk.py` (add) or `tests/test_stub_routes.py` |
| **Component** | `POST /webhooks/stripe` - stub behavior |
| **Scenario** | POST with a mock `stripe-signature` header. Route currently raises `NotImplementedError`. |
| **Expected Result** | `500`. Documents that this MUST NOT reach production in this state. When M4 implements the handler: `200 {"received": true}` after valid signature; `400` for invalid signature. |

---

#### TC-WH-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-WH-21 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_webhooks_clerk.py` (add to existing) |
| **Component** | `POST /webhooks/clerk` - unhandled event types |
| **Scenario** | Send a valid Svix-signed payload with `type = "user.updated"` (not a handled event type). |
| **Expected Result** | `200 {"received": true}`. The handler logs `clerk_webhook_unhandled_event` at DEBUG and does not raise. |

---

#### TC-WH-22
| Field | Value |
|-------|-------|
| **TC-ID** | TC-WH-22 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_webhooks_clerk.py` |
| **Component** | `_write_clerk_metadata` - httpx network failure |
| **Scenario** | `_write_clerk_metadata` is called but `httpx.AsyncClient.patch` raises `httpx.ConnectError`. |
| **Expected Result** | Warning is logged (`clerk_metadata_write_error`). The webhook handler returns `200 {"received": true}` - the DB row is already committed and metadata write is non-fatal. |

---

#### TC-WH-23
| Field | Value |
|-------|-------|
| **TC-ID** | TC-WH-23 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_webhooks_clerk.py` |
| **Component** | `_handle_org_created` - trial window set |
| **Scenario** | Process a `organization.created` event. Capture the `trial_ends_at` value in the upserted row. |
| **Expected Result** | `trial_ends_at` is approximately 14 days from now (within 60 seconds of expected). |
| **Notes** | The 14-day trial requirement is in FR-21. No test currently verifies the trial_ends_at computation. |

---

### Section I · Recommendations Engine - Spec Completeness

---

#### TC-REC-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-REC-20 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_recommendations.py` (add to existing) |
| **Component** | `services/recommendations` - `input_compression` type |
| **Scenario** | FR-19 specifies four recommendation types: `model_swap`, `caching`, `batching`, and `input_compression`. Call `generate_recommendations` with stats that should trigger all applicable rules. |
| **Expected Result** | Document current behavior: `input_compression` type is **NOT** returned (not yet implemented). This test acts as a spec-gap tracker. When `input_compression` is implemented, this test should be updated to assert its presence. |
| **Notes** | This is a known scope item from FR-19. The test documents the gap and prevents silent regression. |

---

#### TC-REC-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-REC-21 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_recommendations.py` |
| **Component** | `PATCH /recommendations/:id` - `resolved_at` timestamp |
| **Scenario** | PATCH a recommendation to `status=applied`. Capture the DB update payload. |
| **Expected Result** | The update payload contains `resolved_at` set to a recent ISO timestamp (within 5 seconds of now). The router currently sets `resolved_at` on every PATCH - this test verifies that. |

---

#### TC-REC-22
| Field | Value |
|-------|-------|
| **TC-ID** | TC-REC-22 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_recommendations.py` |
| **Component** | `services/recommendations._check_model_swap` - `o1-mini` has no downgrade |
| **Scenario** | Pass `ModelStats` for `model="o1-mini"` (not in `_MODEL_DOWNGRADE` as a key). |
| **Expected Result** | Returns `[]`. No recommendation for models that have no cheaper alternative in the map. |

---

### Section J · Integration Route - Audit Logging

---

#### TC-INT-10
| Field | Value |
|-------|-------|
| **TC-ID** | TC-INT-10 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_integration_routes.py` (add to existing) |
| **Component** | `POST /integrations` - audit_events row |
| **Scenario** | Create an integration successfully. Capture all `db.table(...)` calls. |
| **Expected Result** | `audit_events.insert(...)` is called once with `action="integration.create"`, the correct `org_id`, `actor_user_id`, and `target_kind="integration"`. |
| **Notes** | The existing test only checks `any("audit_events" in s for s in table_calls)` - it doesn't verify the payload content. |

---

#### TC-INT-11
| Field | Value |
|-------|-------|
| **TC-ID** | TC-INT-11 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_integration_routes.py` |
| **Component** | `DELETE /integrations/:id` - audit_events row |
| **Scenario** | Delete an integration. Verify `audit_events.insert(...)` is called with `action="integration.delete"`. |
| **Expected Result** | Audit event is logged with correct action, org_id, and target_id. |

---

#### TC-INT-12
| Field | Value |
|-------|-------|
| **TC-ID** | TC-INT-12 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_integration_routes.py` |
| **Component** | `POST /integrations` - audit event failure is non-fatal |
| **Scenario** | `audit_events.insert().execute()` raises an exception. The integration creation completes. |
| **Expected Result** | `201` response with the new integration. The failed audit write is logged (`audit_log_failed`) but does not cause a 500. |

---

#### TC-INT-13
| Field | Value |
|-------|-------|
| **TC-ID** | TC-INT-13 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_integration_routes.py` |
| **Component** | `POST /integrations` - duplicate display_name returns 409 |
| **Scenario** | DB `insert` raises with `"unique"` in the error message (simulating a unique constraint violation on `org_id + provider + display_name`). |
| **Expected Result** | `409` with `"An integration with this name already exists"`. |

---

### Section K · Slack Disconnect - Edge Cases

---

#### TC-SLK-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-SLK-20 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_slack_routes.py` (add to existing) |
| **Component** | `POST /slack/disconnect` - DB delete always runs even when revoke fails |
| **Scenario** | `revoke_token()` raises an exception (token expired). |
| **Expected Result** | `204`. The exception is caught, logged as a warning, and `slack_integrations.delete()` is still called. The Slack row is removed from the DB regardless of revoke outcome. |

---

#### TC-SLK-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-SLK-21 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_slack_routes.py` |
| **Component** | `POST /slack/disconnect` - already disconnected |
| **Scenario** | Call `POST /slack/disconnect` when no Slack integration exists for the org (DB returns empty). |
| **Expected Result** | `404 "No Slack integration found"`. |

---

### Section L · Ingestion / Aggregation - Pagination Loop

---

#### TC-AGG-10
| Field | Value |
|-------|-------|
| **TC-ID** | TC-AGG-10 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_aggregation_worker.py` (add to existing) |
| **Component** | `workers/aggregation.aggregate_org` - pagination through `_PAGE_SIZE=1000` |
| **Scenario** | Mock DB to return 1000 rows on first page and 500 on second (triggering the `while True` loop to exit). |
| **Expected Result** | All 1500 rows are aggregated. Loop exits when `len(result.data) < _PAGE_SIZE`. No data is dropped. |
| **Notes** | The pagination loop guard is `if len(result.data) < _PAGE_SIZE: break`. Only one iteration is tested in existing tests. |

---

#### TC-AGG-11
| Field | Value |
|-------|-------|
| **TC-ID** | TC-AGG-11 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_aggregation_worker.py` |
| **Component** | `workers/aggregation.aggregate_org` - revoked integration events excluded |
| **Scenario** | Two integrations exist: one `active`, one `revoked`. Both have `usage_events`. Call `aggregate_org`. |
| **Expected Result** | Only events belonging to the `active` integration are in the `IN_` filter passed to the usage_events query. The revoked integration's data does not appear in `daily_cost_summaries`. |

---

### Section M · Notification System - `send_budget_alert` Email Templates

---

#### TC-NOT-20
| Field | Value |
|-------|-------|
| **TC-ID** | TC-NOT-20 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_notifications_budget_alert.py` (add to existing) |
| **Component** | `workers/notifications._warning_email_html` |
| **Scenario** | Call `_warning_email_html` with a budget, spend amount, and org name. |
| **Expected Result** | Returned HTML contains: the org name, the `monthly_limit` amount, the current spend, and the word "80%" or "warning" (or similar). Does not contain the word "exceeded". |

---

#### TC-NOT-21
| Field | Value |
|-------|-------|
| **TC-ID** | TC-NOT-21 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_notifications_budget_alert.py` |
| **Component** | `workers/notifications._exceeded_email_html` |
| **Scenario** | Call `_exceeded_email_html` with a budget, spend amount, and org name. |
| **Expected Result** | Returned HTML contains: the org name, the `monthly_limit`, the current spend, and the word "100%" or "exceeded". Different from the warning template. |

---

#### TC-NOT-22
| Field | Value |
|-------|-------|
| **TC-ID** | TC-NOT-22 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_notifications_budget_alert.py` |
| **Component** | `workers/notifications.send_budget_alert` - Slack failure does not block email |
| **Scenario** | Slack `post_message` raises an exception. Email (`resend`) is mocked to succeed. |
| **Expected Result** | The exception from `post_message` is caught and logged. Email is still sent. The task does not raise. |
| **Notes** | Existing test `test_slack_failure_does_not_retry_email` in `test_notification_gaps.py` covers this path; verify it tests the exception-catch branch explicitly (not just a no-op mock). |

---

### Section N · Security - Additional Boundaries

---

#### TC-SEC-09
| Field | Value |
|-------|-------|
| **TC-ID** | TC-SEC-09 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | CRITICAL |
| **File** | `tests/test_security_boundaries.py` (add to existing) |
| **Component** | `GET /anomalies` - org isolation (list, not just patch) |
| **Scenario** | Org A has 3 open anomalies. Org B makes a `GET /anomalies` request. The DB mock filters by `org_id = Org B` and returns empty. |
| **Expected Result** | `200 []`. Org B's response is empty - Org A's anomaly IDs are not revealed. |

---

#### TC-SEC-10
| Field | Value |
|-------|-------|
| **TC-ID** | TC-SEC-10 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | CRITICAL |
| **File** | `tests/test_security_boundaries.py` |
| **Component** | `GET /recommendations` - org isolation (list) |
| **Scenario** | Org A has 5 open recommendations. Org B makes a `GET /recommendations` request. DB mock filters by `org_id = Org B` → empty. |
| **Expected Result** | `200 []`. No data leakage. |

---

#### TC-SEC-11
| Field | Value |
|-------|-------|
| **TC-ID** | TC-SEC-11 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_security_boundaries.py` |
| **Component** | `GET /usage/summary` - org isolation |
| **Scenario** | Org A has spend data. Org B makes a `GET /usage/summary` request. DB mock returns empty for Org B's `org_id`. |
| **Expected Result** | `200` with `total_cost_usd = 0`. Org B does not see Org A's data. |

---

#### TC-SEC-12
| Field | Value |
|-------|-------|
| **TC-ID** | TC-SEC-12 |
| **Layer** | INTG |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_security_boundaries.py` |
| **Component** | `GET /slack/status` - org isolation |
| **Scenario** | Org A has a connected Slack workspace. Org B calls `GET /slack/status`. DB mock returns empty for Org B's `org_id`. |
| **Expected Result** | `200 {"connected": false}`. Org B cannot see Org A's Slack workspace_id. |

---

### Section O · E2E Milestones - Missing M2 and M3 Tests

---

#### TC-E2E-02
| Field | Value |
|-------|-------|
| **TC-ID** | TC-E2E-02 |
| **Layer** | E2E |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_e2e_m2.py` (new file) |
| **Component** | M2 milestone - multi-provider + Cost Explorer |
| **Scenario** | Against a staging environment: (1) Connect two integrations (OpenAI + Anthropic). (2) Seed usage_events via `_ingest_window`. (3) Create tags + rules. (4) Verify `GET /usage/explore?group_by=feature_tag` returns at least one row tagged by the rules. (5) Verify `GET /usage/explore?group_by=provider` returns both providers. |
| **Expected Result** | Explorer returns multi-provider data correctly attributed to feature tags. |
| **Notes** | Uses the same mocked-provider pattern as `test_e2e_m1.py`. Uses `pytest.mark.e2e` to skip in unit runs. |

---

#### TC-E2E-03
| Field | Value |
|-------|-------|
| **TC-ID** | TC-E2E-03 |
| **Layer** | E2E |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_e2e_m3.py` (new file) |
| **Component** | M3 milestone - anomaly + budget + alert |
| **Scenario** | Against a staging/mocked environment: (1) Seed `daily_cost_summaries` with 15 days of baseline data followed by a 5× spike. (2) Run `detect_org`. (3) Verify anomaly row inserted with `severity="high"`. (4) Create a budget at $100. Seed MTD spend at $85. Run `check_org`. (5) Verify `send_budget_alert.delay(budget_id, 80)` is called. |
| **Expected Result** | Anomaly is detected and at 80% budget threshold a budget alert is triggered within the same run. |
| **Notes** | Tests the three M3 subsystems (anomaly, budget, alert) end-to-end without a real Slack or email service. |

---

### Section P · Config / Infrastructure Gaps

---

#### TC-CFG-05
| Field | Value |
|-------|-------|
| **TC-ID** | TC-CFG-05 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_config_gaps.py` (add to existing) |
| **Component** | `api/config.Settings` - `ai_calls_per_org_per_day` default |
| **Scenario** | Instantiate Settings without setting `AI_CALLS_PER_ORG_PER_DAY`. |
| **Expected Result** | `settings.ai_calls_per_org_per_day == 3`. This is the cost cap default from CLAUDE.md. |
| **Notes** | If the default changes, the anomaly explainer rate limiter behavior changes silently. |

---

#### TC-CFG-06
| Field | Value |
|-------|-------|
| **TC-ID** | TC-CFG-06 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | MEDIUM |
| **File** | `tests/test_config_gaps.py` |
| **Component** | `api/config.Settings` - CORS wildcard rejected |
| **Scenario** | Attempt to set `CORS_ORIGINS = '["*"]'`. |
| **Expected Result** | Either the setting is accepted (and this is documented as a known insecure config) or a `ValidationError` is raised at startup. Document the actual behavior. |
| **Notes** | A wildcard CORS policy in production would allow any origin to call the API. |

---

### Section Q · Pricing YAML - Sync with Recommendations

---

#### TC-PRI-10
| Field | Value |
|-------|-------|
| **TC-ID** | TC-PRI-10 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_pricing_new.py` (add to existing) |
| **Component** | `pricing.yaml` ↔ `services/recommendations._INPUT_PRICE_PER_MTOK` sync |
| **Scenario** | Load `pricing.yaml`. For every model in `_INPUT_PRICE_PER_MTOK`, verify the `input_per_mtok` in the YAML matches the hardcoded value in the recommendations service. |
| **Expected Result** | No discrepancy. If a price update is applied to `pricing.yaml` but not to `_INPUT_PRICE_PER_MTOK` (or vice versa), this test fails. |
| **Notes** | The recommendations module has a comment: *"Kept in sync with packages/pricing/pricing.yaml; update both when prices change."* No test enforces this sync. |

---

#### TC-PRI-11
| Field | Value |
|-------|-------|
| **TC-ID** | TC-PRI-11 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_pricing_new.py` |
| **Component** | `pricing.yaml` ↔ `services/recommendations._CACHE_SAVINGS_PER_MTOK` sync |
| **Scenario** | For every model in `_CACHE_SAVINGS_PER_MTOK`, verify: `input_per_mtok - cached_per_mtok` from YAML equals the value in `_CACHE_SAVINGS_PER_MTOK`. |
| **Expected Result** | All cache savings values match the YAML computation. |

---

### Section R · Clerk Webhook - Membership Race Condition (BUG-02 Follow-up)

---

#### TC-WH-24
| Field | Value |
|-------|-------|
| **TC-ID** | TC-WH-24 |
| **Layer** | UNIT |
| **Status** | **NEW** |
| **Priority** | HIGH |
| **File** | `tests/test_webhooks_clerk.py` (add to existing) |
| **Component** | `_handle_membership_created` - data dict error (BUG-02 additional case) |
| **Scenario** | Supabase returns `MagicMock(data={"id": "user-uuid"})` (a dict, not a list). The existing guard `isinstance(user_resp.data, dict) and "id" not in user_resp.data` passes because `"id"` IS in the dict - but this is a success. Test the genuine error case: `data={"code": "PGRST116"}`. |
| **Expected Result** | `500` is returned (triggering Svix retry). The `isinstance(user_resp.data, dict) or "id" not in user_resp.data` guard correctly classifies a PostgREST error dict as missing. |
| **Notes** | `test_open_bugs.py::test_data_dict_with_error_code_not_caught_by_falsy_check` documents this bug. This companion test verifies the POST-FIX behavior once `_handle_membership_created` is updated to use `.limit(1)`. |

---

## Part 3 - Bugs Surfaced During Audit

The following issues were identified during the code review. They are separate from the test gaps
above - they require code fixes, not just new tests.

### BUG-04 (HIGH): `_check_model_swap` uses hardcoded `_INPUT_PRICE_PER_MTOK` map not synced to `pricing.yaml`

**Location:** [src/api/services/recommendations.py](../apps/api/src/api/services/recommendations.py#L32-L43)
**Risk:** If prices are updated in `pricing.yaml` for billing accuracy, the recommendation savings
math stays stale. Customers may see inflated or deflated savings estimates.
**Test to add:** TC-PRI-10, TC-PRI-11 (above).
**Fix:** Either load prices from `pricing.yaml` in `recommendations.py`, or add a startup assertion
that the two maps agree.

---

### BUG-05 (MEDIUM): `PATCH /budgets/:id` silently ignores `hard_cap` changes

**Location:** [src/api/routers/budgets.py](../apps/api/src/api/routers/budgets.py#L166-L176)
**Risk:** Admin updates `hard_cap` via the API; the patch returns 422 "No fields to update" (if only `hard_cap` is sent) or silently ignores it (if sent alongside `monthly_limit`). The UI may show a confirmation that no action was taken.
**Test to add:** TC-BUD-20 (above).
**Fix:** Either add `hard_cap` to the `BudgetUpdate` schema and the patch dict, or document and surface a clear error when only non-patchable fields are sent.

---

### BUG-06 (HIGH): `GET /usage/forecast` and `GET /usage/export.csv` raise `NotImplementedError` → 500 in production

**Location:** [src/api/routers/usage.py](../apps/api/src/api/routers/usage.py#L336-L342)
**Risk:** If the frontend calls these routes (e.g., the onboarding wizard links to export), it receives a generic 500 with no message. Users see a broken experience.
**Fix:** Replace `raise NotImplementedError` with `raise HTTPException(status_code=501, detail="Not yet implemented")` until the feature is built. This gives a clear 501 status code that the frontend can handle gracefully.

---

### BUG-07 (HIGH): All billing routes and Stripe webhook raise `NotImplementedError` → unhandled 500

**Location:** [src/api/routers/billing.py](../apps/api/src/api/routers/billing.py), [src/api/routers/webhooks.py](../apps/api/src/api/routers/webhooks.py#L281)
**Risk:** If Stripe sends a webhook before M4 is deployed (e.g., a test event), the 500 response causes Stripe to retry indefinitely.
**Fix:** Return `501` instead of raising `NotImplementedError` for all stub routes. For the Stripe webhook specifically, return `200` (not 500) for unknown/unhandled events so Stripe does not retry.

---

### BUG-08 (MEDIUM): `input_compression` recommendation type from FR-19 is not implemented

**Location:** [src/api/services/recommendations.py](../apps/api/src/api/services/recommendations.py)
**Risk:** The spec (FR-19) documents four optimization strategies. Only three are shipped (model_swap, caching, batch). Design partners who are prompt-heavy may miss a meaningful saving.
**Test to add:** TC-REC-20 (documents the gap as a tracked test).
**Fix:** Implement `_check_input_compression` rule: triggers when avg_tokens > 2000 and model is in a compression-eligible set. Estimated savings = 30% of cost (based on average compression ratio). Confidence: 0.50 (medium).

---

### BUG-09 (LOW): `aggregate_all_orgs` is not covered by any test

**Location:** [src/api/workers/aggregation.py](../apps/api/src/api/workers/aggregation.py#L29-L38)
**Risk:** If the fan-out logic breaks (wrong filter, duplicate org_ids), every org will fail to aggregate silently. No test catches this.
**Test to add:** TC-FAN-01, TC-FAN-02 (above).

---

### BUG-10 (LOW): `check_all_orgs` fan-out is not tested

**Location:** [src/api/workers/budget_checks.py](../apps/api/src/api/workers/budget_checks.py#L71)
**Risk:** Same as BUG-09 for budget checks. If the SELECT query returns duplicate org_ids, `check_org` is called multiple times per org.
**Test to add:** TC-FAN-03, TC-FAN-04 (above).

---

## Part 4 - Summary Table of New Tests

| TC-ID | Layer | Priority | Component | Status |
|-------|-------|----------|-----------|--------|
| TC-STUB-01 | INTG | HIGH | `POST /integrations/:id/test` (stub) | NEW |
| TC-STUB-02 | INTG | HIGH | `GET /usage/forecast` (stub) | NEW |
| TC-STUB-03 | INTG | HIGH | `GET /usage/export.csv` (stub) | NEW |
| TC-STUB-04 | INTG | CRITICAL | Billing routes ×3 (stubs) | NEW |
| TC-STUB-05 | INTG | CRITICAL | `POST /webhooks/stripe` (stub) | NEW |
| TC-STUB-06 | INTG | HIGH | Reports routes ×3 (stubs) | NEW |
| TC-FAN-01 | UNIT | HIGH | `aggregate_all_orgs` fan-out | NEW |
| TC-FAN-02 | UNIT | HIGH | `aggregate_all_orgs` - empty DB | NEW |
| TC-FAN-03 | UNIT | HIGH | `check_all_orgs` fan-out | NEW |
| TC-FAN-04 | UNIT | HIGH | `check_all_orgs` - empty DB | NEW |
| TC-FAN-05 | UNIT | MEDIUM | `send_daily_digests` fan-out | NEW |
| TC-TAG-10 | INTG | HIGH | `PATCH /tags/:id` - success | NEW |
| TC-TAG-11 | INTG | HIGH | `PATCH /tags/:id` - 404 | NEW |
| TC-TAG-12 | INTG | HIGH | `PATCH /tag-rules/:id` - success | NEW |
| TC-TAG-13 | INTG | HIGH | `PATCH /tag-rules/:id` - 404 | NEW |
| TC-TAG-14 | INTG | MEDIUM | `PATCH /tag-rules/:id` - cross-org 404 | NEW |
| TC-BUD-20 | INTG | MEDIUM | Budget PATCH with `hard_cap` only → 422 | NEW |
| TC-BUD-21 | UNIT | MEDIUM | `_compute_mtd_spend` - `env_tag` scope | NEW |
| TC-BUD-22 | UNIT | MEDIUM | `_to_budget_read` - zero monthly_limit | NEW |
| TC-ANO-20 | UNIT | HIGH | `detect_org` - `context` field content | NEW |
| TC-ANO-21 | UNIT | MEDIUM | `detect_org` - `scope_value` field | NEW |
| TC-USG-20 | UNIT | MEDIUM | `_parse_range("0d")` edge case | NEW |
| TC-USG-21 | INTG | MEDIUM | Dashboard - first day of month MTD | NEW |
| TC-USG-22 | INTG | MEDIUM | Explorer - `pct_of_total` when all zero | NEW |
| TC-HLTH-01 | INTG | CRITICAL | `GET /health` - 200, no auth | NEW |
| TC-HLTH-02 | INTG | HIGH | `GET /health` - not under `/api/v1` | NEW |
| TC-WH-20 | INTG | CRITICAL | `POST /webhooks/stripe` - stub 500 | NEW |
| TC-WH-21 | UNIT | HIGH | Clerk webhook - unhandled event type | NEW |
| TC-WH-22 | UNIT | HIGH | `_write_clerk_metadata` - httpx failure | NEW |
| TC-WH-23 | UNIT | MEDIUM | `_handle_org_created` - trial_ends_at | NEW |
| TC-REC-20 | UNIT | HIGH | `input_compression` not yet implemented | NEW |
| TC-REC-21 | INTG | MEDIUM | Recommendation PATCH - `resolved_at` set | NEW |
| TC-REC-22 | UNIT | MEDIUM | `_check_model_swap` - no-downgrade model | NEW |
| TC-INT-10 | INTG | MEDIUM | Audit event payload on integration create | NEW |
| TC-INT-11 | INTG | MEDIUM | Audit event payload on integration delete | NEW |
| TC-INT-12 | INTG | MEDIUM | Audit event failure is non-fatal | NEW |
| TC-INT-13 | INTG | HIGH | Integration create - duplicate 409 | NEW |
| TC-SLK-20 | INTG | MEDIUM | Disconnect - revoke failure → DB still deleted | NEW |
| TC-SLK-21 | INTG | MEDIUM | Disconnect - not connected → 404 | NEW |
| TC-AGG-10 | UNIT | HIGH | `aggregate_org` - pagination (2 pages) | NEW |
| TC-AGG-11 | UNIT | HIGH | `aggregate_org` - revoked integration excluded | NEW |
| TC-NOT-20 | UNIT | MEDIUM | `_warning_email_html` structure | NEW |
| TC-NOT-21 | UNIT | MEDIUM | `_exceeded_email_html` structure | NEW |
| TC-NOT-22 | UNIT | HIGH | Budget alert - Slack fail does not block email | NEW |
| TC-SEC-09 | INTG | CRITICAL | `GET /anomalies` - org isolation | NEW |
| TC-SEC-10 | INTG | CRITICAL | `GET /recommendations` - org isolation | NEW |
| TC-SEC-11 | INTG | HIGH | `GET /usage/summary` - org isolation | NEW |
| TC-SEC-12 | INTG | HIGH | `GET /slack/status` - org isolation | NEW |
| TC-E2E-02 | E2E | HIGH | M2 e2e - multi-provider + Cost Explorer | NEW |
| TC-E2E-03 | E2E | HIGH | M3 e2e - anomaly + budget + alert | NEW |
| TC-CFG-05 | UNIT | MEDIUM | `ai_calls_per_org_per_day` default = 3 | NEW |
| TC-CFG-06 | UNIT | MEDIUM | CORS wildcard behavior documented | NEW |
| TC-PRI-10 | UNIT | HIGH | `pricing.yaml` ↔ `_INPUT_PRICE_PER_MTOK` sync | NEW |
| TC-PRI-11 | UNIT | HIGH | `pricing.yaml` ↔ `_CACHE_SAVINGS_PER_MTOK` sync | NEW |
| TC-WH-24 | UNIT | HIGH | Membership race - error dict guard post-fix | NEW |

**Total new test cases: 53**
**Total existing tests: 559**
**Grand total after implementation: 612+**

---

## Part 5 - Pre-M4 Gate Checklist

Before opening any M4 work, the following must be true:

- [ ] All CRITICAL new tests above pass (TC-STUB-04, TC-STUB-05, TC-HLTH-01, TC-WH-20, TC-SEC-09, TC-SEC-10)
- [ ] Stub routes return `501` (not `500`) - BUG-06 and BUG-07 fixed
- [ ] `GET /health` is confirmed public and returns `200`
- [ ] `PATCH /tags/:id` and `PATCH /tag-rules/:id` have tests (TC-TAG-10 through TC-TAG-14)
- [ ] Fan-out workers tested (TC-FAN-01 through TC-FAN-05)
- [ ] `pricing.yaml` ↔ recommendations price sync verified (TC-PRI-10, TC-PRI-11)
- [ ] Stripe webhook stub acknowledged and scheduled for M4 implementation
- [ ] All HIGH new tests pass
- [ ] `pytest apps/api/tests/` passes with `--tb=short` - no new failures introduced

---

*End of TEST_PLAN.md*
