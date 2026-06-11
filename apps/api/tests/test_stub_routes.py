"""
Stub route regression tests - Section A and TC-WH-20.

These routes are not yet implemented (M4) and return 501 Not Implemented.
BUG-06 / BUG-07 fixed: NotImplementedError → HTTPException(501) so the
frontend can handle the status code gracefully instead of receiving a generic 500.

When a route is implemented, update the assertion from 501 → the correct code.

TC-STUB-01  POST /integrations/:id/test
TC-STUB-02  GET  /usage/forecast
TC-STUB-03  GET  /usage/export.csv - route REMOVED (FR-23 ships client-side)
TC-STUB-04  GET/POST/GET /billing, /billing/checkout, /billing/portal
TC-STUB-05  POST /webhooks/stripe
TC-STUB-06  /reports routes - IMPLEMENTED (Phase 1); see test_report_routes.py
TC-WH-20    POST /webhooks/stripe - duplicate stub behavior check
"""

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000099"

_AUTH_OVERRIDE = lambda: OrgContext(user_id="user_stub", org_id=ORG_ID)  # noqa: E731
app.dependency_overrides[_require_org] = _AUTH_OVERRIDE


@pytest.fixture(autouse=True)
def _apply_module_auth_override():
    """Re-apply this module's auth override before each test.

    Import-time assignment alone is unreliable: every test module is imported
    at collection, so whichever module imports LAST owns the override for the
    whole run unless each module re-applies its own before its tests.
    """
    app.dependency_overrides[_require_org] = _AUTH_OVERRIDE
    yield


client = TestClient(app, raise_server_exceptions=False)


# ── TC-STUB-01: POST /integrations/:id/test ────────────────────────────────────

class TestIntegrationTestStub:
    """TC-STUB-01 - POST /integrations/:id/test returns 501 Not Implemented."""

    def test_stub_returns_500(self) -> None:
        resp = client.post("/api/v1/integrations/some-id/test")
        assert resp.status_code == 501, (
            f"Expected 501 (Not Implemented) stub, got {resp.status_code}. "
            "When M4 implements this route: assert 200 with {\"status\": \"ok\"}."
        )


# ── TC-STUB-02: GET /usage/forecast ───────────────────────────────────────────

class TestUsageForecastStub:
    """TC-STUB-02 - GET /usage/forecast returns 501 Not Implemented."""

    def test_stub_returns_500(self) -> None:
        resp = client.get("/api/v1/usage/forecast")
        assert resp.status_code == 501, (
            f"Expected 501 (Not Implemented) stub, got {resp.status_code}. "
            "When M4 implements (FR-24): assert 200 with ForecastResult schema."
        )


# ── TC-STUB-03: GET /usage/export.csv (removed) ───────────────────────────────

class TestUsageExportCsvRemoved:
    """TC-STUB-03 - /usage/export.csv was removed, not implemented.

    FR-23 (CSV export from Cost Explorer) ships client-side via
    apps/web/src/app/(dashboard)/cost-explorer/export-button.tsx, so the
    server endpoint is intentionally gone. Guard against it silently
    reappearing without a deliberate decision.
    """

    def test_route_is_gone(self) -> None:
        resp = client.get("/api/v1/usage/export.csv")
        assert resp.status_code == 404, (
            f"Expected 404 (route removed - FR-23 is client-side), got "
            f"{resp.status_code}. If this endpoint is being reintroduced, "
            "it needs a real implementation and a deliberate plan change."
        )


# ── TC-STUB-04: Billing routes × 3 ───────────────────────────────────────────

class TestBillingStubs:
    """
    TC-STUB-04 - GET /billing, POST /billing/checkout, GET /billing/portal.
    All raise NotImplementedError → 500. Critical M4 monetization gate.
    """

    def test_get_billing_returns_500(self) -> None:
        resp = client.get("/api/v1/billing")
        assert resp.status_code == 501, (
            f"Expected 501, got {resp.status_code}. "
            "When M4 implements (FR-21): assert 200 with plan/status."
        )

    def test_post_billing_checkout_returns_500(self) -> None:
        resp = client.post("/api/v1/billing/checkout")
        assert resp.status_code == 501, (
            f"Expected 501, got {resp.status_code}. "
            "When M4 implements: assert 200 with Stripe redirect URL."
        )

    def test_get_billing_portal_returns_500(self) -> None:
        resp = client.get("/api/v1/billing/portal")
        assert resp.status_code == 501, (
            f"Expected 501, got {resp.status_code}. "
            "When M4 implements: assert 200 with portal URL."
        )


# ── TC-STUB-05 + TC-WH-20: POST /webhooks/stripe ─────────────────────────────

class TestStripeWebhookStub:
    """
    TC-STUB-05 / TC-WH-20 - POST /webhooks/stripe returns 501 Not Implemented.
    CRITICAL: Stripe retries on non-2xx. A 500 causes indefinite retries.
    When M4 implements: return 200 {"received": true} after valid signature.
    An invalid stripe-signature must return 400.
    """

    def test_stripe_webhook_stub_returns_500(self) -> None:
        resp = client.post(
            "/api/webhooks/stripe",
            headers={"stripe-signature": "t=123,v1=fakesig"},
            content=b'{"type": "checkout.session.completed"}',
        )
        assert resp.status_code == 501, (
            f"Expected 501 (Not Implemented) stub, got {resp.status_code}. "
            "CRITICAL: This stub must not reach production. "
            "When M4 implements: assert 200 {\"received\": true} for valid sig."
        )


# ── TC-STUB-06: Reports routes - IMPLEMENTED in Phase 1 ───────────────────────
# Real coverage lives in tests/test_report_routes.py (list, download ownership,
# presign, generate 202, rate limit). No stub assertions remain.
