# Test Results — M0–M3 Batch 1
**Date:** 2026-05-21 | **Engineer:** QA / Claude Code | **Branch:** main

---

## Executive Summary

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 221 | 311 |
| Passing | 221 | 311 |
| Failing | 0 | 0 |
| Skipped | 2 | 2 |
| Coverage | 74% | 86% |
| New test cases added | — | 90 |

All 103 planned test cases from `docs/test-plan.md` were accounted for:
- **90 new tests** written across 15 new test files
- **13 test cases** already covered by the pre-existing suite (TC-BUD-01–10, TC-SLACK-01–07, TC-NOT-14–16, TC-NOT-19–21)
- **2 production bugs fixed** as a result of failing tests
- **1 test defect fixed** (TC-SLACK-09 missing `state` field)

Final run command:
```
pytest tests/ --no-header --tb=line -q
```
Result: **311 passed, 2 skipped, 0 failed** in 2.35 s

---

## Bugs Found and Fixed

### BUG-01 (Critical) — Missing Anthropic beta header — FIXED
**File:** `apps/api/src/api/adapters/anthropic.py:178`
**Symptom:** All calls to `GET /v1/organizations/usage_report/messages` would return 400 from Anthropic because the required `anthropic-beta: usage-report-2024-07-01` header was absent.
**Fix:** Added `"anthropic-beta": "usage-report-2024-07-01"` to `AnthropicAdapter._headers()`.
**Test:** TC-ANT-11 (`test_anthropic_header.py`) — PASS

### BUG-SLK (High) — `exchange_code()` did not wrap network errors — FIXED
**File:** `apps/api/src/api/services/slack_client.py`
**Symptom:** The docstring for `exchange_code()` states it raises `ValueError` on network errors, but `httpx.RequestError` was not caught and propagated raw to callers. TC-SLK-04 caught this.
**Fix:** Wrapped the `httpx.Client.post()` call in a `try/except httpx.RequestError` that re-raises as `ValueError`.
**Test:** TC-SLK-04 (`test_slack_client_service.py`) — PASS after fix

### BUG-TFIX (Low) — TC-SLACK-09 missing `state` field in test request — FIXED
**File:** `apps/api/tests/test_slack_routes_extended.py`
**Symptom:** Test sent `{"code": "..."}` to `/api/v1/slack/oauth/callback` which requires both `code` and `state` per `SlackOAuthCallbackBody`. Got 422 instead of 200.
**Fix:** Updated test payload to `{"code": "valid_code", "state": ORG_ID}`.
**Test:** TC-SLACK-09 — PASS after fix

---

## Open Bugs (not fixed — scope deferred)

| Bug ID | Severity | File | Description |
|--------|----------|------|-------------|
| BUG-02 | High | `routers/webhooks.py:217` | `_handle_membership_created` uses `.single()` — if PostgREST raises on 0 rows, the `if not user_resp.data` guard is unreachable |
| BUG-03 | Medium | `workers/notifications.py:82`, `routers/slack.py:173` | `lstrip("\\x")` strips any leading `\` or `x` chars; safer alternative is `[2:]` slice |
| BUG-04 | Medium | `routers/budgets.py:111` | No DB UNIQUE constraint on `(org_id, scope_type, scope_value)` — application-layer check is race-condition-prone |
| BUG-05 | Low | `services/anomaly.py:35` | Docstring says "len >= 15" but code checks `< 15` — 14 points returns None; off-by-one is documented but confusing |

---

## Layer 1 — Unit Tests: Core Services
**35 tests · 35 passed · 0 failed**

### EncryptionService (`test_encryption.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-ENC-01 | Round-trip encrypt/decrypt | PASS | |
| TC-ENC-02 | Wrong key length raises ValueError | PASS | |
| TC-ENC-03 | Empty key string raises ValueError | PASS | |
| TC-ENC-04 | Nonce uniqueness (100 encrypts) | PASS | |
| TC-ENC-05 | Tampered ciphertext raises | PASS | |
| TC-ENC-06 | Nonce is first 12 bytes of blob | PASS | |
| TC-ENC-07 | Binary plaintext round-trip | PASS | |

### Anomaly Service Edge Cases (`test_anomaly_edge_cases.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-ANO-12 | Exactly 14 data points → None | PASS | |
| TC-ANO-13 | All-zero baseline + $50 spike → high | PASS | z=5000 (stdev clipped to 0.01) |
| TC-ANO-14 | Negative value in history → no crash | PASS | |
| TC-ANO-15 | spike_pct=0 when mean=0 | PASS | |

### Slack Client Service (`test_slack_client_service.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-SLK-01 | `exchange_code` success | PASS | |
| TC-SLK-02 | `exchange_code` Slack API error | PASS | |
| TC-SLK-03 | `exchange_code` HTTP 503 | PASS | |
| TC-SLK-04 | `exchange_code` network timeout | PASS | **Required code fix** |
| TC-SLK-05 | `revoke_token` API error non-fatal | PASS | |
| TC-SLK-06 | `revoke_token` network error non-fatal | PASS | |
| TC-SLK-07 | `post_message` success | PASS | |
| TC-SLK-08 | `post_message` Slack error | PASS | |
| TC-SLK-09 | `post_message` HTTP 500 | PASS | |

### Anthropic Adapter Header (`test_anthropic_header.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-ANT-11 / BUG-01 | `_headers()` contains `anthropic-beta` | PASS | Bug fixed before test written |

### Notification Builders (`test_notifications_builders.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-NOT-01 | `_anomaly_slack_blocks` high → `:rotating_light:` | PASS | |
| TC-NOT-02 | `_anomaly_slack_blocks` medium → `:large_orange_diamond:` | PASS | |
| TC-NOT-03 | `_anomaly_slack_blocks` tag context block | PASS | |
| TC-NOT-04 | `_budget_slack_blocks` warning → `:warning:` | PASS | |
| TC-NOT-05 | `_budget_slack_blocks` exceeded → `:red_circle:` | PASS | |
| TC-NOT-06 | `_digest_slack_blocks` MoM None | PASS | |
| TC-NOT-07 | `_digest_slack_blocks` MoM positive | PASS | |
| TC-NOT-08 | `_digest_slack_blocks` MoM negative | PASS | |
| TC-NOT-09 | `_digest_slack_blocks` MoM flat | PASS | |
| TC-NOT-10 | `_scope_label` global scope | PASS | |
| TC-NOT-11 | `_scope_label` model scope | PASS | |
| TC-NOT-12 | `_warning_email_html` renders with pct | PASS | |
| TC-NOT-13 | `_exceeded_email_html` renders | PASS | |

---

## Layer 2 — Route / API Integration Tests
**21 tests · 21 passed · 0 failed**

### Integration Routes (`test_integration_routes.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-INT-01 | Create integration → 201 | PASS | |
| TC-INT-02 | API key never in response | PASS | |
| TC-INT-03 | Backfill task enqueued | PASS | |
| TC-INT-04 | Invalid provider → 422 | PASS | |
| TC-INT-05 | Adapter validate() raises → 422 | PASS | |
| TC-INT-06 | List returns non-revoked only | PASS | |
| TC-INT-07 | Delete soft-revokes → 204 | PASS | |
| TC-INT-08 | Delete other org's integration → 404 | PASS | |
| TC-INT-09 | Duplicate name → 409 | PASS | |
| TC-INT-10 | Audit event written on create | PASS | |

### Anomaly Routes (`test_anomaly_routes.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-ANOM-01 | List all anomalies → 3 results | PASS | |
| TC-ANOM-02 | List filtered by status=open → 2 | PASS | |
| TC-ANOM-03 | PATCH status → acked | PASS | |
| TC-ANOM-04 | PATCH status → dismissed | PASS | |
| TC-ANOM-05 | Org isolation → 404 | PASS | |
| TC-ANOM-06 | Invalid status value → 422 | PASS | |
| TC-ANOM-07 | Anomaly not found → 404 | PASS | |

### Budget Routes Extended (`test_budget_routes_extended.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-BUD-11 | Zero limit → spent_pct=0 (no divide-by-zero) | PASS | |
| TC-BUD-12 | spent_pct=150 when over limit | PASS | |

### Slack Routes Extended (`test_slack_routes_extended.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-SLACK-08 | Revoke failure non-fatal → 204 | PASS | |
| TC-SLACK-09 | Bot token encrypted at rest | PASS | **Test defect fixed** (missing `state` field) |

**Previously covered in existing suite (not re-implemented):**
TC-BUD-01–10 (test_budget_routes.py), TC-SLACK-01–07 (test_slack_routes.py)

---

## Layer 3 — Worker Tests
**9 tests · 9 passed · 0 failed**

### Anomaly Detection Severity + Alerts (`test_detection_severity_alerts.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-DET-10 | Low severity → no `send_anomaly_alert.delay` | PASS | |
| TC-DET-11 | Medium severity → `send_anomaly_alert.delay` called | PASS | |
| TC-DET-12 | High severity → `send_anomaly_alert.delay` called | PASS | |

### Ingestion Worker (`test_ingestion_workers.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-ING-06 | `backfill_integration` revoked → returns early | PASS | |
| TC-ING-07 | `backfill_integration` adapter error → stores error | PASS | |
| TC-ING-08 | `refresh_integration` no last_synced → 4h window | PASS | |
| TC-ING-09 | `_ingest_window` applies tag rules to events | PASS | |

### Budget Alert Email (`test_notifications_budget_alert.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-NOT-17 | `send_budget_alert` sends email via Resend | PASS | |
| TC-NOT-18 | `send_budget_alert` no admin email → returns early | PASS | |

**Previously covered in existing suite:**
TC-NOT-14–16 (test_notifications_slack.py), TC-NOT-19–21 (test_notifications_digest.py)

---

## Layer 4 — Webhook Security Tests
**11 tests · 11 passed · 0 failed**

### Svix Signature Verification + Clerk Event Handlers (`test_webhooks_clerk.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-WH-01 | Valid Svix signature passes | PASS | Real HMAC computed from .env secret |
| TC-WH-02 | Wrong signature rejected → 400 | PASS | |
| TC-WH-03 | Stale timestamp rejected → 400 | PASS | |
| TC-WH-04 | Non-integer timestamp rejected → 400 | PASS | |
| TC-WH-05 | `user.created` upserts user row | PASS | |
| TC-WH-06 | `user.created` no email → 400 | PASS | |
| TC-WH-07 | `organization.created` upserts org | PASS | |
| TC-WH-08 | `organization.created` 14-day trial | PASS | |
| TC-WH-09 | `organizationMembership.created` upserts member | PASS | |
| TC-WH-10 | Clerk role `org:admin` mapped to `"admin"` | PASS | |
| TC-WH-11 | Unhandled event type → 200, no DB write | PASS | |

---

## Layer 5 — Security Boundary Tests
**9 tests · 9 passed · 0 failed**

(`test_security_boundaries.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-SEC-01 | API key never in POST/GET response | PASS | 2 sub-tests |
| TC-SEC-02 | Org isolation: integrations (404 not 403) | PASS | |
| TC-SEC-03 | Org isolation: budgets | PASS | |
| TC-SEC-04 | Org isolation: anomalies | PASS | |
| TC-SEC-05 | 31-byte key → ValueError | PASS | |
| TC-SEC-06 | Tampered token unreadable | PASS | |
| TC-SEC-07 | Budget 80% alert fires once per month | PASS | |
| TC-SEC-08 | Budget 100% alert supersedes 80% | PASS | |

---

## Layer 6 — Pricing Math Tests
**5 tests · 5 passed · 0 failed**

(`test_pricing_new.py`)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-PRI-01 | `pricing.yaml` parses; all 3 providers present | PASS | |
| TC-PRI-02 | All models have 3 rate keys | PASS | |
| TC-PRI-03 | No zero rates | PASS | |
| TC-PRI-04 | Claude Sonnet: 1M input + 1M output = $18.00 | PASS | $3 + $15 = $18 |
| TC-PRI-05 | Cached tokens cheaper than input tokens | PASS | $0.30 < $3.00/mtok |

---

## New Test Files Created

| File | Layer | TCs Covered | Tests |
|------|-------|-------------|-------|
| `test_encryption.py` | 1 | TC-ENC-01–07 | 7 |
| `test_anomaly_edge_cases.py` | 1 | TC-ANO-12–15 | 4 |
| `test_slack_client_service.py` | 1 | TC-SLK-01–09 | 9 |
| `test_anthropic_header.py` | 1 | TC-ANT-11 | 2 |
| `test_notifications_builders.py` | 1 | TC-NOT-01–13 | 13 |
| `test_integration_routes.py` | 2 | TC-INT-01–10 | 10 |
| `test_anomaly_routes.py` | 2 | TC-ANOM-01–07 | 7 |
| `test_budget_routes_extended.py` | 2 | TC-BUD-11–12 | 2 |
| `test_slack_routes_extended.py` | 2 | TC-SLACK-08–09 | 2 |
| `test_detection_severity_alerts.py` | 3 | TC-DET-10–12 | 3 |
| `test_ingestion_workers.py` | 3 | TC-ING-06–09 | 4 |
| `test_notifications_budget_alert.py` | 3 | TC-NOT-17–18 | 2 |
| `test_webhooks_clerk.py` | 4 | TC-WH-01–11 | 11 |
| `test_security_boundaries.py` | 5 | TC-SEC-01–08 | 9 |
| `test_pricing_new.py` | 6 | TC-PRI-01–05 | 5 |
| **Total** | | **90 new TCs** | **90** |

---

## Coverage Change by Module

| Module | Before | After |
|--------|--------|-------|
| `services/encryption.py` | 44% | **100%** |
| `services/slack_client.py` | 24% | **100%** |
| `services/anomaly.py` | ~93% | **100%** |
| `routers/integrations.py` | 34% | **85%** |
| `routers/anomalies.py` | 52% | **92%** |
| `routers/budgets.py` | 74% | **84%** |
| `routers/slack.py` | 27% | **94%** |
| `routers/webhooks.py` | 26% | **87%** |
| `workers/anomaly_detection.py` | 0% | **99%** |
| `workers/budget_checks.py` | 0% | **88%** |
| `workers/ingestion.py` | 40% | **78%** |
| `workers/notifications.py` | 33% | **94%** |
| `adapters/anthropic.py` | 30% | **34%** (validate/fetch not yet unit tested) |
| **TOTAL** | **74%** | **86%** |

---

## Final Command Output

```
pytest tests/ --no-header --tb=line -q
311 passed, 2 skipped, 2 warnings in 2.35s
```

The 2 skipped tests are pre-existing (unrelated to this batch); the 2 warnings are `PytestUnraisableExceptionWarning` from httpx async context in existing tests.
