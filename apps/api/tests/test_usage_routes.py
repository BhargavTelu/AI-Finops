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
app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)

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
