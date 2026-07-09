"""
Unit tests for GET/POST /billing routes. Stripe SDK + Supabase mocked.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"

_AUTH_OVERRIDE = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)  # noqa: E731
app.dependency_overrides[_require_org] = _AUTH_OVERRIDE


@pytest.fixture(autouse=True)
def _apply_module_auth_override():
    """Re-apply this module's auth override before each test (see test_budget_routes)."""
    app.dependency_overrides[_require_org] = _AUTH_OVERRIDE
    yield


client = TestClient(app)

# +1h pad: microseconds elapse between fixture creation and the route's own
# datetime.now(), and timedelta.days floors - exactly +10d would read as 9.
FUTURE = (datetime.now(UTC) + timedelta(days=10, hours=1)).isoformat()
PAST = (datetime.now(UTC) - timedelta(days=3)).isoformat()


def _db(org_rows: list[dict], billing_rows: list[dict]) -> MagicMock:
    db = MagicMock()

    def table(name: str) -> MagicMock:
        chain = MagicMock()
        for method in ("select", "eq", "limit"):
            getattr(chain, method).return_value = chain
        result = MagicMock()
        result.data = org_rows if name == "organizations" else billing_rows
        chain.execute.return_value = result
        return chain

    db.table.side_effect = table
    return db


class TestGetBilling:
    def test_trialing_state(self) -> None:
        db = _db([{"trial_ends_at": FUTURE, "plan": "trial"}], [])
        with patch("api.routers.billing._get_supabase", return_value=db):
            resp = client.get("/api/v1/billing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "trialing"
        assert body["access_blocked"] is False
        assert body["trial_days_left"] == 10
        assert body["has_subscription"] is False

    def test_expired_state_reports_blocked(self) -> None:
        db = _db([{"trial_ends_at": PAST, "plan": "trial"}], [])
        with patch("api.routers.billing._get_supabase", return_value=db):
            resp = client.get("/api/v1/billing")
        assert resp.status_code == 200
        assert resp.json()["access_blocked"] is True

    def test_subscribed_state(self) -> None:
        billing = [
            {
                "plan": "growth",
                "status": "active",
                "stripe_customer_id": "cus_1",
                "stripe_subscription_id": "sub_1",
                "current_period_end": FUTURE,
            }
        ]
        db = _db([{"trial_ends_at": PAST, "plan": "growth"}], billing)
        with patch("api.routers.billing._get_supabase", return_value=db):
            resp = client.get("/api/v1/billing")
        body = resp.json()
        assert body["plan"] == "growth"
        assert body["has_subscription"] is True
        assert body["access_blocked"] is False


class TestCheckout:
    def _post(self, plan: str = "growth"):
        return client.post("/api/v1/billing/checkout", json={"plan": plan})

    def test_creates_session_with_org_reference(self) -> None:
        session = MagicMock(url="https://checkout.stripe.com/c/pay/cs_test")
        with (
            patch("api.routers.billing._get_supabase", return_value=_db([], [])),
            patch("api.routers.billing.settings.stripe_price_growth", "price_growth_1"),
            patch(
                "api.routers.billing.stripe.checkout.Session.create", return_value=session
            ) as mock_create,
        ):
            resp = self._post("growth")
        assert resp.status_code == 200
        assert resp.json()["url"].startswith("https://checkout.stripe.com")
        kwargs = mock_create.call_args.kwargs
        assert kwargs["client_reference_id"] == ORG_ID
        assert kwargs["line_items"] == [{"price": "price_growth_1", "quantity": 1}]
        assert kwargs["mode"] == "subscription"
        assert kwargs["metadata"]["org_id"] == ORG_ID
        assert kwargs["subscription_data"]["metadata"]["plan"] == "growth"

    def test_reuses_existing_stripe_customer(self) -> None:
        session = MagicMock(url="https://checkout.stripe.com/x")
        billing = [
            {
                "stripe_customer_id": "cus_existing",
                "plan": "trial",
                "status": "canceled",
                "stripe_subscription_id": None,
                "current_period_end": None,
            }
        ]
        with (
            patch("api.routers.billing._get_supabase", return_value=_db([], billing)),
            patch("api.routers.billing.settings.stripe_price_starter", "price_starter_1"),
            patch(
                "api.routers.billing.stripe.checkout.Session.create", return_value=session
            ) as mock_create,
        ):
            resp = self._post("starter")
        assert resp.status_code == 200
        assert mock_create.call_args.kwargs["customer"] == "cus_existing"

    def test_invalid_plan_422(self) -> None:
        resp = self._post("platinum")
        assert resp.status_code == 422

    def test_unconfigured_price_503(self) -> None:
        with patch("api.routers.billing.settings.stripe_price_growth", ""):
            resp = self._post("growth")
        assert resp.status_code == 503


class TestPortal:
    def test_no_customer_404(self) -> None:
        with patch("api.routers.billing._get_supabase", return_value=_db([], [])):
            resp = client.get("/api/v1/billing/portal")
        assert resp.status_code == 404

    def test_returns_portal_url(self) -> None:
        billing = [
            {
                "stripe_customer_id": "cus_1",
                "plan": "growth",
                "status": "active",
                "stripe_subscription_id": "sub_1",
                "current_period_end": None,
            }
        ]
        session = MagicMock(url="https://billing.stripe.com/p/session")
        with (
            patch("api.routers.billing._get_supabase", return_value=_db([], billing)),
            patch(
                "api.routers.billing.stripe.billing_portal.Session.create",
                return_value=session,
            ) as mock_create,
        ):
            resp = client.get("/api/v1/billing/portal")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://billing.stripe.com/p/session"
        assert mock_create.call_args.kwargs["customer"] == "cus_1"
