"""
Security boundary tests.
TC-SEC-01 to TC-SEC-08.
"""

import base64
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app
from api.services.encryption import EncryptionService

ORG_A = "00000000-0000-0000-0000-000000000001"
ORG_B = "00000000-0000-0000-0000-000000000002"
INT_ID_A = "aaaaaaaa-0000-0000-0000-000000000001"
BUDGET_ID_A = "bbbbbbbb-0000-0000-0000-000000000001"
ANOMALY_ID_A = "cccccccc-0000-0000-0000-000000000001"
NOW_ISO = datetime.now(timezone.utc).isoformat()

# Default auth = Org A - set at import time and re-applied by the autouse fixture below.
_ORG_A_OVERRIDE = lambda: OrgContext(user_id="user_a", org_id=ORG_A)  # noqa: E731
app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE


@pytest.fixture(autouse=True)
def _apply_module_auth_override():
    """Re-apply this module's auth override before each test.

    Import-time assignment alone is unreliable: every test module is imported
    at collection, so whichever module imports LAST owns the override for the
    whole run unless each module re-applies its own before its tests.
    """
    app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE
    yield


client = TestClient(app)


@pytest.fixture(autouse=True)
def _restore_auth_override():
    """Re-apply the Org A override before each test and restore after.

    test_route_gaps.py pops the override in its finally blocks, which would
    leave subsequent tests in this module without any auth override (→ 401).
    This fixture makes every test in this file independent of execution order.
    """
    saved = app.dependency_overrides.get(_require_org)
    app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE
    yield
    if saved is not None:
        app.dependency_overrides[_require_org] = saved
    else:
        app.dependency_overrides.pop(_require_org, None)


def _mock_db(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.upsert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.is_.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


# ── TC-SEC-01: API key never in response ──────────────────────────────────────

class TestApiKeyNeverInResponse:
    def test_create_integration_no_api_key_in_response(self) -> None:  # TC-SEC-01 part 1
        db = _mock_db(
            [
                {
                    "id": INT_ID_A,
                    "org_id": ORG_A,
                    "provider": "openai",
                    "display_name": "Main",
                    "status": "active",
                    "last_synced_at": None,
                    "last_error": None,
                    "created_at": NOW_ISO,
                }
            ]
        )
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations._ADAPTERS", {"openai": MagicMock(validate=MagicMock())}),
            patch("api.routers.integrations.backfill_integration") as mock_bf,
        ):
            mock_bf.delay = MagicMock()
            resp = client.post(
                "/api/v1/integrations",
                json={"provider": "openai", "display_name": "Main", "api_key": "sk-admin-key-1234567890"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "api_key" not in data
        assert "api_key_enc" not in data

    def test_list_integrations_no_api_key_in_response(self) -> None:  # TC-SEC-01 part 2
        db = _mock_db(
            [
                {
                    "id": INT_ID_A,
                    "org_id": ORG_A,
                    "provider": "openai",
                    "display_name": "Main",
                    "status": "active",
                    "last_synced_at": None,
                    "last_error": None,
                    "created_at": NOW_ISO,
                }
            ]
        )
        with patch("api.routers.integrations._get_supabase", return_value=db):
            resp = client.get("/api/v1/integrations")
        assert resp.status_code == 200
        for item in resp.json():
            assert "api_key" not in item
            assert "api_key_enc" not in item


# ── TC-SEC-02: Org isolation - integrations ───────────────────────────────────

class TestOrgIsolationIntegrations:
    def test_org_b_cannot_access_org_a_integration(self) -> None:  # TC-SEC-02
        """Org B deleting Org A's integration must get 404, not 403."""
        # DB returns empty (org_id filter mismatches, simulating real RLS behavior)
        db = _mock_db([])
        with patch("api.routers.integrations._get_supabase", return_value=db):
            resp = client.delete(f"/api/v1/integrations/{INT_ID_A}")
        assert resp.status_code == 404  # not 403 (no info leak)


# ── TC-SEC-03: Org isolation - budgets ────────────────────────────────────────

class TestOrgIsolationBudgets:
    def test_org_b_cannot_patch_org_a_budget(self) -> None:  # TC-SEC-03
        db = _mock_db([])  # ownership check returns empty
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("0")),
        ):
            resp = client.patch(f"/api/v1/budgets/{BUDGET_ID_A}", json={"monthly_limit": 9999})
        assert resp.status_code == 404


# ── TC-SEC-04: Org isolation - anomalies ─────────────────────────────────────

class TestOrgIsolationAnomalies:
    def test_org_b_cannot_dismiss_org_a_anomaly(self) -> None:  # TC-SEC-04
        db = _mock_db([])  # ownership check returns empty
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.patch(
                f"/api/v1/anomalies/{ANOMALY_ID_A}", json={"status": "dismissed"}
            )
        assert resp.status_code == 404


# ── TC-SEC-05: EncryptionService rejects 31-byte key ─────────────────────────

class TestEncryptionKeyLength:
    def test_31_byte_key_raises_valueerror(self) -> None:  # TC-SEC-05
        short_key = base64.b64encode(b"\xdd" * 31).decode()
        with pytest.raises(ValueError, match="32 bytes"):
            EncryptionService(short_key)


# ── TC-SEC-06: Tampered token unreadable ──────────────────────────────────────

class TestTamperedToken:
    def test_tampered_token_decrypt_fails(self) -> None:  # TC-SEC-06
        key_b64 = base64.b64encode(b"\xee" * 32).decode()
        cipher = EncryptionService(key_b64)
        # Encrypt a valid token
        encrypted = cipher.encrypt(b"xoxb-valid-token")
        # Flip bits in the authentication tag (last 16 bytes)
        tampered = bytearray(encrypted)
        tampered[-1] ^= 0xFF
        with pytest.raises(Exception):  # InvalidTag or ValueError
            cipher.decrypt(bytes(tampered))


# ── TC-SEC-07: Budget 80% alert fires only once per month ─────────────────────

class TestBudgetAlertIdempotency:
    def test_80pct_alert_fires_at_most_once_per_month(self) -> None:  # TC-SEC-07
        """
        check_org is responsible for the once-per-month guard.
        When notified_80_at is already set for this month, send_budget_alert.delay
        should NOT be called again.
        """
        from datetime import date

        db = _mock_db()
        today = date.today()
        first_of_month = today.replace(day=1).isoformat()

        # Budget row with notified_80_at already set this month
        budget = {
            "id": BUDGET_ID_A,
            "org_id": ORG_A,
            "scope_type": "global",
            "scope_value": None,
            "monthly_limit": "1000.00",
            "alert_at_pct": 80,
            "notified_80_at": f"{today.isoformat()}T00:00:00+00:00",
            "notified_100_at": None,
        }

        db.execute.return_value = MagicMock(data=[budget])

        mock_alert = MagicMock()
        mock_alert.delay = MagicMock()

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks.send_budget_alert", mock_alert),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("850")),
        ):
            from api.workers.budget_checks import check_org

            check_org(ORG_A)

        mock_alert.delay.assert_not_called()


# ── TC-SEC-08: Budget 100% supersedes 80% warning ────────────────────────────

class TestBudgetExceededAlert:
    def test_100pct_alert_fires_when_not_yet_notified(self) -> None:  # TC-SEC-08
        """
        When spend ≥ 100% and notified_100_at is None, send_budget_alert.delay
        should fire with pct=100 (exceeded), not 80 (warning).
        """
        from datetime import date

        db = _mock_db()

        # Budget row: spend > 100%, 80% guard already fired but 100% has not
        budget = {
            "id": BUDGET_ID_A,
            "org_id": ORG_A,
            "scope_type": "global",
            "scope_value": None,
            "monthly_limit": "1000.00",
            "alert_at_pct": 80,
            "notified_80_at": f"{date.today().isoformat()}T00:00:00+00:00",
            "notified_100_at": None,
        }

        db.execute.side_effect = [
            MagicMock(data=[budget]),   # budgets SELECT
            MagicMock(data=[]),         # update notified_100_at
        ]

        mock_alert = MagicMock()
        mock_alert.delay = MagicMock()

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks.send_budget_alert", mock_alert),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("1200")),
        ):
            from api.workers.budget_checks import check_org

            check_org(ORG_A)

        # Only the 100% alert should fire
        assert mock_alert.delay.call_count == 1
        call_args = mock_alert.delay.call_args[0]
        assert call_args[1] == 100  # pct=100


# ── M1-I-SEC-001: Unauthenticated requests return 401 ─────────────────────────
#
# Use a dedicated mini-app (not the shared `app`) so we never touch the global
# dependency_overrides dict and cannot corrupt other test files' state.

from fastapi import FastAPI as _FastAPI
from api.deps import OrgDep as _OrgDep

_auth_guard_app = _FastAPI()


@_auth_guard_app.get("/check")
async def _check(org: _OrgDep) -> dict:
    return {"org_id": org.org_id}


_auth_guard_client = TestClient(_auth_guard_app, raise_server_exceptions=False)


class TestUnauthenticatedEndpoints:
    """M1-I-SEC-001: Routes protected by _require_org return 401 when no token is provided."""

    def test_usage_dashboard_requires_auth(self) -> None:
        """GET without a Bearer token must return 401 - the dependency enforces it."""
        resp = _auth_guard_client.get("/check")
        assert resp.status_code == 401, (
            f"Expected 401 without auth, got {resp.status_code}"
        )


# ── M1-I-SEC-005: api_key min_length validation ────────────────────────────────

class TestInputValidation:
    """M1-I-SEC-005: api_key shorter than 10 chars rejected before any adapter call."""

    def test_api_key_too_short_returns_422(self) -> None:
        """IntegrationCreate.api_key has min_length=10. Keys shorter than 10 chars → 422."""
        resp = client.post(
            "/api/v1/integrations",
            json={
                "provider": "openai",
                "display_name": "Test",
                "api_key": "sk-short",  # 8 chars - below min_length=10
            },
        )
        assert resp.status_code == 422


# ── TC-SEC-09: GET /anomalies - org isolation (list) ──────────────────────────

class TestOrgIsolationAnomaliesList:
    """TC-SEC-09 (CRITICAL) - Org B cannot see Org A's anomalies via GET /anomalies."""

    def test_org_b_sees_empty_anomalies_list(self) -> None:
        """TC-SEC-09 - DB filtered by Org B's org_id returns empty; 200 [] returned."""
        # Switch to Org B context for this test
        app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_b", org_id=ORG_B)
        try:
            # DB mock returns empty (Org B has no anomalies, and org_id filter prevents
            # leaking Org A's anomaly IDs)
            db = _mock_db([])
            with patch("api.routers.anomalies._get_supabase", return_value=db):
                resp = client.get("/api/v1/anomalies")
        finally:
            app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE

        assert resp.status_code == 200
        assert resp.json() == [], (
            "Org B must receive an empty list - not Org A's anomalies."
        )


# ── TC-SEC-10: GET /recommendations - org isolation (list) ────────────────────

class TestOrgIsolationRecommendationsList:
    """TC-SEC-10 (CRITICAL) - Org B cannot see Org A's recommendations."""

    def test_org_b_sees_empty_recommendations_list(self) -> None:
        """TC-SEC-10 - DB filtered by Org B's org_id returns empty; 200 [] returned."""
        app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_b", org_id=ORG_B)
        try:
            db = _mock_db([])
            with patch("api.routers.recommendations._get_supabase", return_value=db):
                resp = client.get("/api/v1/recommendations")
        finally:
            app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE

        assert resp.status_code == 200
        assert resp.json() == [], (
            "Org B must receive an empty list - not Org A's recommendations."
        )


# ── TC-SEC-11: GET /usage/summary - org isolation ─────────────────────────────

class TestOrgIsolationUsageSummary:
    """TC-SEC-11 (HIGH) - Org B sees zero spend, not Org A's data."""

    def test_org_b_sees_zero_usage_summary(self) -> None:
        """TC-SEC-11 - Org B's usage/summary returns zeros when DB filtered by Org B's org_id."""
        app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_b", org_id=ORG_B)
        try:
            db = _mock_db([])  # no rows for Org B
            with patch("api.routers.usage._get_supabase", return_value=db):
                resp = client.get("/api/v1/usage/summary?range=30d")
        finally:
            app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE

        assert resp.status_code == 200
        data = resp.json()
        assert float(data["total_cost_usd"]) == 0.0, (
            "Org B must see zero total cost, not Org A's spend data."
        )


# ── TC-SEC-12: GET /slack/status - org isolation ──────────────────────────────

class TestOrgIsolationSlackStatus:
    """TC-SEC-12 (HIGH) - Org B sees {connected: false}, not Org A's Slack workspace_id."""

    def test_org_b_sees_slack_disconnected(self) -> None:
        """TC-SEC-12 - DB filtered by Org B's org_id returns empty; {connected: false}."""
        app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_b", org_id=ORG_B)
        try:
            db = _mock_db([])  # Org B has no Slack integration
            with patch("api.routers.slack._get_supabase", return_value=db):
                resp = client.get("/api/v1/slack/status")
        finally:
            app.dependency_overrides[_require_org] = _ORG_A_OVERRIDE

        assert resp.status_code == 200
        assert resp.json()["connected"] is False, (
            "Org B must see connected=false - not Org A's Slack workspace_id."
        )
