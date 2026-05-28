"""
Tests for GET /usage/dashboard - the multi-period summary endpoint added in M1 gap-close.

Tests cover:
- Period boundary arithmetic (day / week / 30d / MTD windows)
- pct_change calculation (positive, negative, null-when-prev-zero)
- MTD edge case when today is the 1st of the month
- Empty org returns all-zero periods, not an error
- mom_pct_change mirrors mtd.pct_change
- last_month_cost_usd sums the full prior calendar month
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000002"

app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)
client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_row(day: date, cost: str, reqs: int = 1, tokens: int = 100) -> dict:
    return {
        "day": day.isoformat(),
        "total_cost_usd": cost,
        "total_requests": reqs,
        "total_tokens": tokens,
    }


def _mock_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows
    db.table.return_value = db
    db.select.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.execute.return_value = result
    return db


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _yesterday() -> date:
    return _today() - timedelta(days=1)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDashboardEndpointStructure:
    def test_returns_200_with_all_period_keys(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("day", "week", "month", "mtd", "mom_pct_change", "last_month_cost_usd"):
            assert key in data, f"Missing key: {key}"

    def test_each_period_has_required_fields(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        data = resp.json()
        for period_key in ("day", "week", "month", "mtd"):
            period = data[period_key]
            for field in (
                "total_cost_usd",
                "total_requests",
                "total_tokens",
                "period_start",
                "period_end",
                "period_label",
                "prev_period_cost_usd",
                "pct_change",
            ):
                assert field in period, f"Period '{period_key}' missing field '{field}'"

    def test_empty_db_returns_zeros_not_error(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["day"]["total_cost_usd"]) == 0.0
        assert float(data["week"]["total_cost_usd"]) == 0.0
        assert float(data["month"]["total_cost_usd"]) == 0.0
        assert data["mom_pct_change"] is None  # prev = 0, no baseline


class TestDashboardPeriodBoundaries:
    def test_day_period_end_is_yesterday(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        period = resp.json()["day"]
        assert period["period_end"] == _yesterday().isoformat()
        assert period["period_start"] == _yesterday().isoformat()

    def test_week_period_spans_7_days(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        period = resp.json()["week"]
        start = date.fromisoformat(period["period_start"])
        end = date.fromisoformat(period["period_end"])
        assert (end - start).days == 6  # 7 days inclusive

    def test_month_period_spans_30_days(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        period = resp.json()["month"]
        start = date.fromisoformat(period["period_start"])
        end = date.fromisoformat(period["period_end"])
        assert (end - start).days == 29  # 30 days inclusive

    def test_mtd_start_is_first_of_current_month(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        period = resp.json()["mtd"]
        start = date.fromisoformat(period["period_start"])
        assert start.day == 1
        assert start.month == _today().month
        assert start.year == _today().year

    def test_period_labels_are_correct(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        data = resp.json()
        assert data["day"]["period_label"] == "Latest day"
        assert data["week"]["period_label"] == "7 days"
        assert data["month"]["period_label"] == "30 days"
        assert data["mtd"]["period_label"] == "Month to date"


class TestDashboardPctChange:
    def test_pct_change_positive_when_current_exceeds_prior(self) -> None:
        yesterday = _yesterday()
        day_before = yesterday - timedelta(days=1)
        rows = [
            _make_row(yesterday, "20.00"),     # current day
            _make_row(day_before, "10.00"),    # prior day
        ]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        pct = resp.json()["day"]["pct_change"]
        assert pct == pytest.approx(100.0, rel=0.01)  # +100%

    def test_pct_change_negative_when_current_below_prior(self) -> None:
        yesterday = _yesterday()
        day_before = yesterday - timedelta(days=1)
        rows = [
            _make_row(yesterday, "5.00"),
            _make_row(day_before, "10.00"),
        ]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        pct = resp.json()["day"]["pct_change"]
        assert pct == pytest.approx(-50.0, rel=0.01)  # -50%

    def test_pct_change_null_when_no_prior_data(self) -> None:
        # Only provide yesterday's data - prior day has nothing
        rows = [_make_row(_yesterday(), "10.00")]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        assert resp.json()["day"]["pct_change"] is None

    def test_pct_change_zero_when_current_equals_prior(self) -> None:  # M1-U-DASH-004
        yesterday = _yesterday()
        day_before = yesterday - timedelta(days=1)
        rows = [
            _make_row(yesterday, "10.00"),   # current day
            _make_row(day_before, "10.00"),  # prior day - identical cost
        ]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        pct = resp.json()["day"]["pct_change"]
        assert pct == pytest.approx(0.0, abs=0.01)

    def test_mom_pct_change_mirrors_mtd_pct_change(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        data = resp.json()
        assert data["mom_pct_change"] == data["mtd"]["pct_change"]


class TestDashboardAggregation:
    def test_multiple_rows_same_day_are_summed(self) -> None:
        """Multiple tag-dimension rows for the same day must aggregate to one total."""
        yesterday = _yesterday()
        rows = [
            _make_row(yesterday, "3.00"),   # e.g. feature_tag=A
            _make_row(yesterday, "7.00"),   # e.g. feature_tag=B - same day
        ]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        cost = float(resp.json()["day"]["total_cost_usd"])
        assert cost == pytest.approx(10.0)

    def test_last_month_cost_usd_sums_full_prior_month(self) -> None:
        today = _today()
        first_of_this_month = today.replace(day=1)
        last_month_last = first_of_this_month - timedelta(days=1)
        last_month_first = last_month_last.replace(day=1)

        # Seed two rows in the prior calendar month
        mid_last_month = last_month_first + timedelta(days=10)
        rows = [
            _make_row(last_month_first, "100.00"),
            _make_row(mid_last_month, "50.00"),
        ]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        last_month_total = float(resp.json()["last_month_cost_usd"])
        assert last_month_total == pytest.approx(150.0)


class TestDashboardMtdEdgeCase:
    def test_mtd_returns_zeros_when_no_data_this_month(self) -> None:
        """If aggregation hasn't run yet this month, MTD should be $0 not an error."""
        # Only feed prior-month data
        today = _today()
        first_of_this_month = today.replace(day=1)
        last_month_day = (first_of_this_month - timedelta(days=1)).replace(day=1)
        rows = [_make_row(last_month_day, "42.00")]
        db = _mock_db(rows)
        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.get("/api/v1/usage/dashboard")
        mtd = resp.json()["mtd"]
        assert float(mtd["total_cost_usd"]) == pytest.approx(0.0)
        assert mtd["total_requests"] == 0
