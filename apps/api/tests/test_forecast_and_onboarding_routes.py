"""
Route tests for GET /usage/forecast (FR-24) and GET /onboarding/status.
Supabase mocked, auth dependency overridden.
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


def _chain_db(rows: list[dict]) -> MagicMock:
    """Chainable Supabase mock - every query resolves to the same rows."""
    db = MagicMock()
    result = MagicMock()
    result.data = rows
    db.table.return_value = db
    for method in ("select", "eq", "gte", "lte", "order", "range", "limit"):
        getattr(db, method).return_value = db
    db.execute.return_value = result
    return db


class TestForecastRoute:
    def test_404_when_no_data(self) -> None:
        with patch("api.routers.usage._get_supabase", return_value=_chain_db([])):
            resp = client.get("/api/v1/usage/forecast")
        assert resp.status_code == 404

    def test_returns_forecast_with_all_fields(self) -> None:
        # Same rows serve MTD, trailing, and prior-month queries - enough to
        # assert the response contract without modeling each window. The day
        # must be yesterday (UTC): the route reads the real clock and both its
        # windows end at yesterday (complete days only), so a hardcoded date
        # eventually falls out of every window and the route 404s.
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        rows = [{"day": yesterday.isoformat(), "total_cost_usd": "25.00"}]
        with patch("api.routers.usage._get_supabase", return_value=_chain_db(rows)):
            resp = client.get("/api/v1/usage/forecast")
        assert resp.status_code == 200
        body = resp.json()
        assert float(body["projected_month_end_usd"]) > 0
        assert float(body["confidence_low"]) <= float(body["projected_month_end_usd"])
        assert float(body["projected_month_end_usd"]) <= float(body["confidence_high"])
        assert body["method"] in ("linear_regression", "trailing_30d_average")
        assert "last_month_cost_usd" in body
        assert "delta_vs_last_month_pct" in body
        assert "as_of" in body


class TestOnboardingStatus:
    def test_all_false_for_fresh_org(self) -> None:
        with patch("api.routers.onboarding._get_supabase", return_value=_chain_db([])):
            resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        assert resp.json() == {
            "provider_connected": False,
            "tag_rule_created": False,
            "slack_connected": False,
            "budget_created": False,
        }

    def test_all_true_when_rows_exist(self) -> None:
        with patch(
            "api.routers.onboarding._get_supabase",
            return_value=_chain_db([{"id": "x"}]),
        ):
            resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        assert all(resp.json().values())

    def test_scopes_queries_to_org(self) -> None:
        db = _chain_db([])
        with patch("api.routers.onboarding._get_supabase", return_value=db):
            client.get("/api/v1/onboarding/status")
        org_filters = [c for c in db.eq.call_args_list if c.args == ("org_id", ORG_ID)]
        assert len(org_filters) == 4  # one per checked table
