"""
Unit tests for GET /usage/summary and GET /usage/timeseries.
Supabase calls are mocked. Auth dependency is overridden.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app
from api.routers.usage import _parse_range

ORG_ID = "00000000-0000-0000-0000-000000000001"

# Override auth for all tests in this module
_AUTH_OVERRIDE = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)  # noqa: E731
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


client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows
    db.table.return_value = db
    db.select.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.range.return_value = db
    db.execute.return_value = result
    return db


# ── _parse_range helper ───────────────────────────────────────────────────────

class TestParseRange:
    def test_30d_period_end_is_yesterday(self) -> None:
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        _, period_end = _parse_range("30d")
        assert period_end == yesterday

    def test_30d_period_start_is_29_days_before_period_end(self) -> None:
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        period_start, period_end = _parse_range("30d")
        assert (period_end - period_start).days == 29  # inclusive window = 30 days

    def test_1d_window_is_single_day(self) -> None:
        period_start, period_end = _parse_range("1d")
        assert period_start == period_end


# ── GET /usage/summary ────────────────────────────────────────────────────────

class TestGetSummary:
    def test_empty_db_returns_zero_totals(self) -> None:
        with patch("api.routers.usage._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/usage/summary?range=30d")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_cost_usd"] == "0"
        assert body["total_requests"] == 0
        assert body["total_tokens"] == 0

    def test_sums_multiple_rows_correctly(self) -> None:
        rows = [
            {"total_cost_usd": "1.500000", "total_requests": 10, "total_tokens": 500},
            {"total_cost_usd": "2.250000", "total_requests": 5,  "total_tokens": 300},
            {"total_cost_usd": "0.750000", "total_requests": 3,  "total_tokens": 100},
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/summary?range=30d")

        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(body["total_cost_usd"]) == Decimal("4.500000")
        assert body["total_requests"] == 18
        assert body["total_tokens"] == 900

    def test_period_dates_present_and_correct(self) -> None:
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        expected_start = yesterday - timedelta(days=29)

        with patch("api.routers.usage._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/usage/summary?range=30d")

        body = resp.json()
        assert body["period_end"] == yesterday.isoformat()
        assert body["period_start"] == expected_start.isoformat()

    def test_invalid_range_rejected(self) -> None:
        resp = client.get("/api/v1/usage/summary?range=abc")
        assert resp.status_code == 422  # FastAPI query param validation


# ── GET /usage/timeseries ─────────────────────────────────────────────────────

class TestGetTimeseries:
    def test_empty_db_returns_empty_list(self) -> None:
        with patch("api.routers.usage._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/usage/timeseries?range=30d&group_by=model")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_one_point_per_day_per_model(self) -> None:
        rows = [
            {"day": "2025-01-01", "model": "gpt-4o",      "total_cost_usd": "1.00", "total_requests": 5},
            {"day": "2025-01-01", "model": "gpt-4o-mini", "total_cost_usd": "0.20", "total_requests": 2},
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/timeseries?range=30d&group_by=model")

        assert resp.status_code == 200
        points = resp.json()
        assert len(points) == 2
        by_model = {p["group_key"]: p for p in points}
        assert Decimal(by_model["gpt-4o"]["cost_usd"]) == Decimal("1.00")
        assert Decimal(by_model["gpt-4o-mini"]["cost_usd"]) == Decimal("0.20")

    def test_aggregates_multiple_tag_rows_for_same_day_model(self) -> None:
        """Rows with different tag combinations for same (day, model) must be summed."""
        rows = [
            {"day": "2025-01-01", "model": "gpt-4o", "total_cost_usd": "1.00", "total_requests": 3},
            {"day": "2025-01-01", "model": "gpt-4o", "total_cost_usd": "2.00", "total_requests": 7},
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/timeseries?range=30d&group_by=model")

        points = resp.json()
        assert len(points) == 1
        assert Decimal(points[0]["cost_usd"]) == Decimal("3.00")
        assert points[0]["requests"] == 10

    def test_points_sorted_by_day_then_model(self) -> None:
        rows = [
            {"day": "2025-01-02", "model": "gpt-4o",      "total_cost_usd": "1.00", "total_requests": 1},
            {"day": "2025-01-01", "model": "gpt-4o-mini", "total_cost_usd": "0.50", "total_requests": 1},
            {"day": "2025-01-01", "model": "gpt-4o",      "total_cost_usd": "2.00", "total_requests": 1},
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/timeseries?range=30d&group_by=model")

        points = resp.json()
        assert points[0]["day"] == "2025-01-01"
        assert points[0]["group_key"] == "gpt-4o"       # alphabetical within day
        assert points[1]["group_key"] == "gpt-4o-mini"
        assert points[2]["day"] == "2025-01-02"

    def test_unsupported_group_by_returns_400(self) -> None:
        resp = client.get("/api/v1/usage/timeseries?range=30d&group_by=feature_tag")
        assert resp.status_code == 400


# ── GET /usage/explore ────────────────────────────────────────────────────────

class TestGetExplore:
    def _row(self, dimension: str, value: str, cost: str, reqs: int, tokens: int) -> dict:
        """Build a mock daily_cost_summaries row for a given dimension column."""
        return {dimension: value, "total_cost_usd": cost, "total_requests": reqs, "total_tokens": tokens}

    def test_groups_by_provider(self) -> None:
        rows = [
            self._row("provider", "openai", "10.00", 100, 50000),
            self._row("provider", "anthropic", "5.00", 50, 25000),
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=provider&range=30d")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        keys = {r["group_key"] for r in body}
        assert keys == {"openai", "anthropic"}

    def test_groups_by_model(self) -> None:
        rows = [
            self._row("model", "gpt-4o", "8.00", 80, 40000),
            self._row("model", "claude-sonnet-4-5", "3.00", 30, 15000),
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["group_key"] == "gpt-4o"  # higher cost first

    def test_sums_cost_requests_tokens_for_same_group_key(self) -> None:
        """Multiple rows with same dimension value must be summed."""
        rows = [
            self._row("model", "gpt-4o", "3.00", 30, 10000),
            self._row("model", "gpt-4o", "2.00", 20, 8000),  # same model, different tag combo
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        r = body[0]
        assert Decimal(r["total_cost_usd"]) == Decimal("5.00")
        assert r["total_requests"] == 50
        assert r["total_tokens"] == 18000

    def test_pct_of_total_sums_to_100(self) -> None:
        rows = [
            self._row("provider", "openai", "75.00", 100, 50000),
            self._row("provider", "anthropic", "25.00", 50, 25000),
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=provider&range=30d")

        body = resp.json()
        total_pct = sum(r["pct_of_total"] for r in body)
        assert abs(total_pct - 100.0) < 0.01  # float tolerance

    def test_sorted_by_cost_descending(self) -> None:
        rows = [
            self._row("model", "gpt-4o-mini", "1.00", 10, 5000),
            self._row("model", "gpt-4o", "9.00", 90, 45000),
            self._row("model", "o1", "5.00", 5, 2000),
        ]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d")

        body = resp.json()
        costs = [Decimal(r["total_cost_usd"]) for r in body]
        assert costs == sorted(costs, reverse=True)

    def test_empty_db_returns_empty_list(self) -> None:
        with patch("api.routers.usage._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_invalid_group_by_returns_400(self) -> None:
        resp = client.get("/api/v1/usage/explore?group_by=wallet&range=30d")
        assert resp.status_code == 400
        assert "wallet" in resp.json()["detail"]

    def test_provider_filter_param_accepted(self) -> None:
        """Provider filter is forwarded to DB query without breaking the response."""
        rows = [self._row("model", "gpt-4o", "5.00", 50, 20000)]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d&provider=openai")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_pct_of_total_zero_when_all_costs_zero(self) -> None:
        """Guard against divide-by-zero when all rows have zero cost."""
        rows = [self._row("model", "gpt-4o", "0.00", 10, 5000)]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d")

        body = resp.json()
        assert body[0]["pct_of_total"] == 0.0

    def test_model_filter_applied_to_db_query(self) -> None:
        """model= param must be forwarded as an .eq() filter on the DB query."""
        rows = [self._row("feature_tag", "payments", "4.00", 40, 20000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/explore?group_by=feature_tag&range=30d&model=gpt-4o")

        assert resp.status_code == 200
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("model", "gpt-4o") in eq_calls

    def test_feature_tag_filter_applied_to_db_query(self) -> None:
        """feature_tag= param must be forwarded as an .eq() filter on the DB query."""
        rows = [self._row("model", "gpt-4o", "7.00", 70, 35000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d&feature_tag=payments")

        assert resp.status_code == 200
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("feature_tag", "payments") in eq_calls

    def test_multiple_dimension_filters_applied_simultaneously(self) -> None:
        """provider= and feature_tag= can be combined; both must reach the DB."""
        rows = [self._row("model", "gpt-4o", "3.00", 30, 15000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get(
                "/api/v1/usage/explore?group_by=model&range=30d&provider=openai&feature_tag=search"
            )

        assert resp.status_code == 200
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("provider", "openai") in eq_calls
        assert ("feature_tag", "search") in eq_calls

    def test_all_tag_dimension_filters_accepted(self) -> None:
        """team_tag, customer_tag, env_tag filter params must not cause errors."""
        rows = [self._row("model", "gpt-4o", "2.00", 20, 10000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get(
                "/api/v1/usage/explore?group_by=model&range=30d"
                "&team_tag=ml&customer_tag=acme&env_tag=prod"
            )

        assert resp.status_code == 200
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("team_tag", "ml") in eq_calls
        assert ("customer_tag", "acme") in eq_calls
        assert ("env_tag", "prod") in eq_calls

    # TC-EX-101
    def test_team_tag_filter_applied_individually(self) -> None:
        """team_tag= alone is forwarded as a single .eq() call without side effects."""
        rows = [self._row("model", "gpt-4o", "2.00", 20, 10000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d&team_tag=ml")

        assert resp.status_code == 200
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("team_tag", "ml") in eq_calls
        # No other dimension filters should have been applied
        dimension_cols = {"provider", "model", "feature_tag", "customer_tag", "env_tag"}
        assert not any(c[0] in dimension_cols for c in eq_calls)

    # TC-EX-102
    def test_customer_tag_filter_applied_individually(self) -> None:
        """customer_tag= alone is forwarded without injecting other filter calls."""
        rows = [self._row("model", "gpt-4o", "3.00", 30, 15000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d&customer_tag=acme")

        assert resp.status_code == 200
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("customer_tag", "acme") in eq_calls
        dimension_cols = {"provider", "model", "feature_tag", "team_tag", "env_tag"}
        assert not any(c[0] in dimension_cols for c in eq_calls)

    # TC-EX-103
    def test_no_filters_adds_no_dimension_eq_calls(self) -> None:
        """When no dimension filter params are given, only org_id scoping hits the DB."""
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            client.get("/api/v1/usage/explore?group_by=model&range=30d")

        eq_calls = [call.args for call in db.eq.call_args_list]
        dimension_cols = {"provider", "model", "feature_tag", "team_tag", "customer_tag", "env_tag"}
        spurious = [c for c in eq_calls if c[0] in dimension_cols]
        assert spurious == [], f"Unexpected dimension filter calls: {spurious}"

    # TC-EX-104
    def test_filter_on_same_column_as_group_by(self) -> None:
        """Filtering and grouping on the same dimension (e.g. model) must both work."""
        rows = [self._row("model", "gpt-4o", "5.00", 50, 25000)]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/explore?group_by=model&range=30d&model=gpt-4o")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["group_key"] == "gpt-4o"
        eq_calls = [call.args for call in db.eq.call_args_list]
        assert ("model", "gpt-4o") in eq_calls
