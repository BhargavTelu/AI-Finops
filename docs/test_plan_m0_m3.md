# SpendOps AI - Comprehensive Test Plan (M0–M3 Audit)
**Date:** 2026-05-21 | **Auditor:** QA / Senior Engineer | **Baseline:** 221 tests, 74% coverage

---

## Executive Summary

Full codebase read (70+ Python files, 25+ TypeScript files, 5 migrations, 1 pricing config).
Current state: 221 passing tests, 2 skipped, 74% aggregate coverage. Several critical gaps remain.

**Bugs found during audit (pre-test):**

| Bug ID | Severity | File | Description |
|--------|----------|------|-------------|
| BUG-01 | **Critical** | `adapters/anthropic.py:178` | `_headers()` missing `anthropic-beta: usage-report-2024-07-01` required by Anthropic API |
| BUG-02 | **High** | `routers/webhooks.py:217` | `_handle_membership_created` calls `.single()` - if PostgREST raises on 0 rows, the `if not user_resp.data` guard is unreachable |
| BUG-03 | **Medium** | `workers/notifications.py:82`, `routers/slack.py:173` | `lstrip("\\x")` strips any leading `\` or `x` chars instead of exactly a `\x` prefix; inconsistent with `ingestion.py`'s safer `[2:]` slice |
| BUG-04 | **Medium** | `routers/budgets.py:111` | No DB `UNIQUE` constraint on `(org_id, scope_type, scope_value)` - application-layer check is race-condition-prone under concurrent requests |
| BUG-05 | **Low** | `services/anomaly.py:35` | Docstring says "len >= 15" but function checks `len(history) < 15` - 14 points returns None; off-by-one is documented but confusing |

---

## Coverage Gaps by Module

| Module | Current | Target | Gap |
|--------|---------|--------|-----|
| `services/encryption.py` | 44% | 100% | Missing all encrypt/decrypt/validation tests |
| `routers/integrations.py` | 34% | 85% | Happy path, org isolation, key-never-returned |
| `routers/webhooks.py` | 26% | 80% | Svix verification, all 3 Clerk event handlers |
| `services/slack_client.py` | 24% | 80% | exchange_code, revoke_token, post_message |
| `services/recommendations.py` | 0% | 0% | Stub - no tests needed until M3-D implemented |
| `workers/ingestion.py` | 40% | 80% | backfill/refresh task end-to-end |
| `routers/anomalies.py` | 52% | 85% | List filter, patch status, org isolation |
| `routers/budgets.py` | 74% | 90% | Patch 404, delete 404, org isolation |
| `deps.py` | 31% | N/A | Auth middleware - untestable without real Clerk JWKS |

---

## Test Cases

### Layer 1 - Unit Tests: Core Services

#### 1.1 EncryptionService (`services/encryption.py`) - 0 tests currently

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-ENC-01 | Round-trip encrypt/decrypt | encrypt(b"sk-admin-test") then decrypt | Plaintext matches original | **Critical** |
| TC-ENC-02 | Wrong key length | init with 16-byte key (base64) | `ValueError` raised | **Critical** |
| TC-ENC-03 | Empty key string | init with `""` | `ValueError` raised (`binascii.Error` or `ValueError`) | **Critical** |
| TC-ENC-04 | Nonce uniqueness | encrypt same plaintext 100x | All ciphertexts are distinct | **High** |
| TC-ENC-05 | Tampered ciphertext | flip a bit in ciphertext then decrypt | `cryptography.InvalidTag` or `ValueError` raised | **Critical** |
| TC-ENC-06 | Nonce strip & length | blob[:12] = nonce, rest = ciphertext | First 12 bytes are always present in output | **High** |
| TC-ENC-07 | Binary plaintext round-trip | encrypt(b"\x00\xff\x00") | Decrypts to same bytes | **Medium** |

#### 1.2 Anomaly Service (`services/anomaly.py`) - 100% coverage (fill edge cases)

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-ANO-12 | Exactly 14 data points | `len(history) == 14` | Returns `None` | **Medium** |
| TC-ANO-13 | All-zero baseline, spike $50 | 14× $0, then $50 | High severity detected (z = 5000) | **Medium** |
| TC-ANO-14 | Negative value in history | `-5.0` in rolling window | No crash; `pstdev` handles it | **Low** |
| TC-ANO-15 | spike_pct when mean=0 | All zeros baseline + $50 spike | `spike_pct == 0` (special-cased) | **High** |

#### 1.3 Slack Client Service (`services/slack_client.py`) - 24% coverage

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-SLK-01 | `exchange_code` success | Mock HTTP 200 with `{"ok": true, "access_token": "xoxb-..."}` | Returns full response dict | **Critical** |
| TC-SLK-02 | `exchange_code` Slack API error | Mock 200 with `{"ok": false, "error": "invalid_code"}` | Raises `ValueError("Slack OAuth failed: invalid_code")` | **Critical** |
| TC-SLK-03 | `exchange_code` HTTP error | Mock HTTP 503 | Raises `ValueError` with status code | **Critical** |
| TC-SLK-04 | `exchange_code` network timeout | Raise `httpx.RequestError` | Raises `ValueError` | **High** |
| TC-SLK-05 | `revoke_token` API error | Mock 200 with `{"ok": false}` | Logs warning, does NOT raise | **High** |
| TC-SLK-06 | `revoke_token` network error | Raise `httpx.RequestError` | Logs warning, does NOT raise | **High** |
| TC-SLK-07 | `post_message` success | Mock 200 with `{"ok": true}` | Returns without raising | **Critical** |
| TC-SLK-08 | `post_message` Slack error | Mock 200 with `{"ok": false, "error": "channel_not_found"}` | Raises `ValueError("Slack postMessage failed: channel_not_found")` | **Critical** |
| TC-SLK-09 | `post_message` HTTP error | Mock HTTP 500 | Raises `ValueError` with status code | **Critical** |

#### 1.4 Anthropic Adapter - Missing Header Bug

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-ANT-11 | `_headers()` includes beta header | Call `_headers(b"key")` | Dict contains key `"anthropic-beta"` with value `"usage-report-2024-07-01"` | **Critical** |

#### 1.5 Notification Builders (`workers/notifications.py`)

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-NOT-01 | `_anomaly_slack_blocks` structure | Call with severity="high" | Returns list with 2+ blocks; first block text contains `:rotating_light:` | **High** |
| TC-NOT-02 | `_anomaly_slack_blocks` medium | severity="medium" | Contains `:large_orange_diamond:` | **High** |
| TC-NOT-03 | `_anomaly_slack_blocks` tag context | context with team_tag+feature_tag | Third block (context) present with "Team:" and "Feature:" | **Medium** |
| TC-NOT-04 | `_budget_slack_blocks` warning | is_exceeded=False | Header contains `:warning:` | **High** |
| TC-NOT-05 | `_budget_slack_blocks` exceeded | is_exceeded=True | Header contains `:red_circle:` | **High** |
| TC-NOT-06 | `_digest_slack_blocks` MoM None | `mom_pct=None` | "No prior month data" shown | **Medium** |
| TC-NOT-07 | `_digest_slack_blocks` MoM positive | `mom_pct=15` | `"+15% vs last month"` | **Medium** |
| TC-NOT-08 | `_digest_slack_blocks` MoM negative | `mom_pct=-5` | `"-5% vs last month"` | **Medium** |
| TC-NOT-09 | `_digest_slack_blocks` MoM flat | `mom_pct=0` | `"Flat vs last month"` | **Low** |
| TC-NOT-10 | `_scope_label` global | scope_type="global" | Returns "all providers (global)" | **Low** |
| TC-NOT-11 | `_scope_label` model | scope_type="model", scope_value="gpt-4o" | Returns "model: gpt-4o" | **Low** |
| TC-NOT-12 | `_warning_email_html` renders | Call with valid args | Returns non-empty HTML string containing pct | **Medium** |
| TC-NOT-13 | `_exceeded_email_html` renders | Call with valid args | Returns non-empty HTML string containing "exceeded" | **Medium** |

---

### Layer 2 - Route / API Integration Tests

All route tests use `TestClient` with mocked Supabase (`patch("_get_supabase")`), `OrgDep` overridden via `app.dependency_overrides`.

#### 2.1 Integration Routes (`routers/integrations.py`) - 34% coverage

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-INT-01 | Create integration happy path | POST /integrations with valid body | 201; response has `id`, `status="active"` | **Critical** |
| TC-INT-02 | **api_key never returned** | POST /integrations; inspect response | No `api_key` or `api_key_enc` field in response | **Critical** |
| TC-INT-03 | Backfill task enqueued | POST /integrations succeeds | `backfill_integration.delay` called with `(id, org_id)` | **Critical** |
| TC-INT-04 | Invalid provider returns 422 | POST with `provider="cohere"` | 422 | **High** |
| TC-INT-05 | Invalid key validation returns 422 | Adapter `validate()` raises ValueError | 422 with adapter error message | **High** |
| TC-INT-06 | List returns non-revoked only | Org has 2 active + 1 revoked | Only 2 returned | **High** |
| TC-INT-07 | Delete soft-revokes | DELETE /integrations/{id} | 204; DB updated `status="revoked"` | **Critical** |
| TC-INT-08 | Delete other org's integration | DELETE with different org's integration id | 404 | **Critical** |
| TC-INT-09 | Duplicate name returns 409 | DB raises unique violation | 409 with "already exists" | **High** |
| TC-INT-10 | Audit event written | POST succeeds | `audit_events.insert` called with `action="integration.create"` | **High** |

#### 2.2 Anomaly Routes (`routers/anomalies.py`) - 52% coverage

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-ANOM-01 | List all anomalies for org | 3 anomalies in DB | Returns 3 in desc order | **High** |
| TC-ANOM-02 | List filtered by status=open | 2 open, 1 acked | Returns 2 | **High** |
| TC-ANOM-03 | PATCH status to acked | PATCH /anomalies/{id} `{"status": "acked"}` | 200; `status` field = "acked" | **High** |
| TC-ANOM-04 | PATCH status to dismissed | PATCH /anomalies/{id} `{"status": "dismissed"}` | 200; `status` field = "dismissed" | **High** |
| TC-ANOM-05 | **Org isolation** | PATCH anomaly owned by different org | 404 | **Critical** |
| TC-ANOM-06 | Invalid status value | PATCH with `{"status": "deleted"}` | 422 | **Medium** |
| TC-ANOM-07 | Anomaly not found | PATCH non-existent id | 404 | **Medium** |

#### 2.3 Budget Routes (`routers/budgets.py`) - 74% coverage

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-BUD-01 | Create global budget | scope_type="global", no scope_value | 201; scope_value=null in response | **Critical** |
| TC-BUD-02 | Scope value required for model | scope_type="model", no scope_value | 422 | **Critical** |
| TC-BUD-03 | Duplicate budget 409 | Same org + scope already exists | 409 | **High** |
| TC-BUD-04 | Negative limit rejected | monthly_limit=-100 | 422 | **High** |
| TC-BUD-05 | List returns spend metrics | GET /budgets | `current_spend_mtd` and `spent_pct` in each row | **High** |
| TC-BUD-06 | Update limit | PATCH /budgets/{id} `{"monthly_limit": 2000}` | 200; new limit reflected | **High** |
| TC-BUD-07 | **Org isolation patch** | PATCH budget from other org | 404 | **Critical** |
| TC-BUD-08 | **Org isolation delete** | DELETE budget from other org | 404 | **Critical** |
| TC-BUD-09 | Delete non-existent | DELETE /budgets/bad-id | 404 | **Medium** |
| TC-BUD-10 | Empty patch body 422 | PATCH with `{}` | 422 | **Medium** |
| TC-BUD-11 | Zero limit budget shows 0% | monthly_limit=0; spend=$500 | `spent_pct=0` (no divide-by-zero) | **High** |
| TC-BUD-12 | spent_pct capped correctly | spend=$1500 vs limit=$1000 | `spent_pct=150` | **Medium** |

#### 2.4 Slack Routes (`routers/slack.py`) - 91% coverage

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-SLACK-01 | Status disconnected | No Slack row for org | `{"connected": false}` | **High** |
| TC-SLACK-02 | Status connected | Slack row exists | `connected=true` with workspace/channel info | **High** |
| TC-SLACK-03 | OAuth callback happy path | `exchange_code` returns valid dict with channel | 200; token encrypted in DB | **Critical** |
| TC-SLACK-04 | OAuth callback no channel | Slack response missing `incoming_webhook.channel_id` | 400 | **High** |
| TC-SLACK-05 | OAuth callback Slack error | `exchange_code` raises ValueError | 400 with error message | **High** |
| TC-SLACK-06 | Disconnect deletes row | Row exists in DB | 204; DB row deleted | **High** |
| TC-SLACK-07 | Disconnect when not connected | No row in DB | 404 | **High** |
| TC-SLACK-08 | Disconnect revoke failure non-fatal | `revoke_token` raises | 204; DB row still deleted | **High** |
| TC-SLACK-09 | Bot token encrypted at rest | POST /slack/oauth/callback | `bot_token_enc` in DB is not plaintext token | **Critical** |

---

### Layer 3 - Worker Tests

#### 3.1 Ingestion Worker (uncovered paths)

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-ING-06 | `backfill_integration` revoked | Integration status = "revoked" | Returns early, no fetch called | **High** |
| TC-ING-07 | `backfill_integration` stores error | Adapter raises exception | DB updated with `status="error"`, `last_error` set | **High** |
| TC-ING-08 | `refresh_integration` fallback window | `last_synced_at` is None | Uses 4h lookback window | **High** |
| TC-ING-09 | `_ingest_window` applies tag rules | Tag rules exist for org | `feature_tag` / `team_tag` fields populated in inserted rows | **Critical** |

#### 3.2 Anomaly Detection Worker (additional cases)

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-DET-10 | Low severity no Slack alert | Anomaly detected with severity="low" | `send_anomaly_alert.delay` NOT called | **Critical** |
| TC-DET-11 | Medium severity triggers Slack | Anomaly detected with severity="medium" | `send_anomaly_alert.delay` called | **Critical** |
| TC-DET-12 | High severity triggers Slack | Anomaly detected with severity="high" | `send_anomaly_alert.delay` called | **Critical** |

#### 3.3 Notification Workers (real task logic)

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-NOT-14 | `send_anomaly_alert` no Slack | No `slack_integrations` row | Silently returns; no post_message call | **High** |
| TC-NOT-15 | `send_anomaly_alert` posts blocks | Slack connected | `post_message` called with blocks containing severity | **High** |
| TC-NOT-16 | `send_anomaly_alert` anomaly not found | Anomaly ID doesn't exist | Returns without error | **Medium** |
| TC-NOT-17 | `send_budget_alert` sends email | Resend configured | `resend.Emails.send` called with budget details | **Critical** |
| TC-NOT-18 | `send_budget_alert` no admin email | No admin user for org | Returns early without sending | **High** |
| TC-NOT-19 | `send_slack_digest` idempotency | Row exists in `slack_digests` for today | Returns early, no `post_message` call | **Critical** |
| TC-NOT-20 | `send_slack_digest` inserts dedup record | Successful send | `slack_digests.insert` called | **High** |
| TC-NOT-21 | `send_slack_digest` retries on failure | `post_message` raises ValueError | `self.retry` called | **High** |

---

### Layer 4 - Webhook Security Tests (`routers/webhooks.py`) - 26% coverage

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-WH-01 | **Valid Svix signature passes** | Correct HMAC-SHA256 | 200 `{"received": true}` | **Critical** |
| TC-WH-02 | **Wrong signature rejected** | Modified body | 400 "Invalid webhook signature" | **Critical** |
| TC-WH-03 | **Stale timestamp rejected** | `svix_timestamp` > 5 min old | 400 "Webhook timestamp out of tolerance" | **Critical** |
| TC-WH-04 | Non-integer timestamp rejected | `svix_timestamp="abc"` | 400 "Invalid svix-timestamp" | **High** |
| TC-WH-05 | `user.created` upserts user row | Valid user.created payload | `users.upsert` called; 200 returned | **Critical** |
| TC-WH-06 | `user.created` no email returns 400 | Payload with no email_addresses | 400 | **High** |
| TC-WH-07 | `organization.created` upserts org | Valid org.created payload | `organizations.upsert` with plan="trial"; 200 | **Critical** |
| TC-WH-08 | `organization.created` 14-day trial | org.created event | `trial_ends_at` is ~14 days from now | **High** |
| TC-WH-09 | `organizationMembership.created` | Valid membership payload | `organization_members.upsert` called | **Critical** |
| TC-WH-10 | Clerk role mapping | `role="org:admin"` | Stored as `"admin"` | **High** |
| TC-WH-11 | Unhandled event type | `type="user.updated"` | 200; no DB write | **Medium** |

---

### Layer 5 - Security Boundary Tests

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-SEC-01 | **API key never in response** | POST /integrations; GET /integrations | No `api_key` or `api_key_enc` field anywhere | **Critical** |
| TC-SEC-02 | **Org isolation: integrations** | Org B requests Org A's integration id | 404, not 403 (no info leak) | **Critical** |
| TC-SEC-03 | **Org isolation: budgets** | Org B patches Org A's budget | 404 | **Critical** |
| TC-SEC-04 | **Org isolation: anomalies** | Org B dismisses Org A's anomaly | 404 | **Critical** |
| TC-SEC-05 | **Encryption key 31-byte rejects** | `EncryptionService` with 31-byte key | `ValueError` | **Critical** |
| TC-SEC-06 | **Tampered token unreadable** | Flip bytes in stored `bot_token_enc` | Decrypt raises; `_get_slack_channel` returns None | **Critical** |
| TC-SEC-07 | **Budget 80% alert once-per-month** | Run `check_org` twice in same month | `send_budget_alert.delay` called only once | **Critical** |
| TC-SEC-08 | **Budget 100% supersedes warning** | spend ≥ 100% | Only 100 alert fired, not 80 alert too | **Critical** |

---

### Layer 6 - Pricing Math Tests

| ID | Test | Scenario | Expected | Priority |
|----|------|----------|----------|----------|
| TC-PRI-01 | YAML parses correctly | Load pricing.yaml | No parse error; all 3 providers present | **High** |
| TC-PRI-02 | All models have 3 rate keys | Each model entry | Has `input_per_mtok`, `output_per_mtok`, `cached_per_mtok` | **High** |
| TC-PRI-03 | No zero rates | All rates > 0 | All values are positive floats | **High** |
| TC-PRI-04 | Claude Sonnet cost calc | 1M input + 1M output | $(3.00 + 15.00) = $18.00 | **High** |
| TC-PRI-05 | Cached tokens cheaper than input | claude-sonnet-4-5 | `cached_per_mtok < input_per_mtok` | **High** |

---

## Bug Fix Test Cases

These tests are written specifically to catch the known bugs and verify fixes:

| ID | Bug | Test | Pass Condition |
|----|-----|------|----------------|
| TC-BUG-01 | BUG-01: Missing Anthropic beta header | `assert "anthropic-beta" in adapter._headers(b"key")` | Header present with value `"usage-report-2024-07-01"` |
| TC-BUG-02 | BUG-02: `.single()` unsafe | `_handle_membership_created` with missing user | Returns 500 without unhandled exception |
| TC-BUG-03 | BUG-03: `lstrip` vs `[2:]` | Hex starting with `x` after prefix | Both approaches produce same result |

---

## Test Infrastructure Requirements

All tests use:
- `pytest-asyncio` for async tests
- `unittest.mock.patch` for Supabase client mocking
- `httpx.MockTransport` or `unittest.mock.patch` for external HTTP calls
- `app.dependency_overrides[OrgDep]` to inject test org context in route tests
- No real DB, no real network, no real Celery broker

### Mock Pattern (reference)
```python
def mock_org(org_id="00000000-0000-0000-0000-000000000001", user_id="user_test"):
    async def _dep():
        from api.deps import OrgContext
        return OrgContext(org_id=org_id, user_id=user_id)
    return _dep

# In test:
app.dependency_overrides[require_org] = mock_org()
```

---

## Priority Summary

| Priority | Count | Description |
|----------|-------|-------------|
| Critical | 42 | Must pass before M4; security, correctness, data integrity |
| High | 35 | Should pass; key functional coverage |
| Medium | 18 | Robustness; edge cases |
| Low | 8 | Nice-to-have; documentation tests |
| **Total** | **103** | New test cases to add |

Combined with existing 221 tests → target ~324 total tests.
