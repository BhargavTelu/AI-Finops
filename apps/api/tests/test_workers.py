"""
Unit tests for Celery workers (ingestion + aggregation).
All external calls (Supabase, provider adapters) are mocked.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from api.adapters.base import NormalizedUsageEvent
from api.workers.ingestion import _ingest_window


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_event(model: str, cost: float, hour: datetime) -> NormalizedUsageEvent:
    return NormalizedUsageEvent(
        provider="openai",
        model=model,
        api_key_label=None,
        input_tokens=1000,
        output_tokens=200,
        cached_tokens=50,
        cost_usd=Decimal(str(cost)),
        request_count=5,
        bucket_hour=hour,
        raw_meta={},
    )


def _mock_db() -> MagicMock:
    """Return a supabase client mock where all chained calls return the mock itself
    and .execute() returns an object with empty .data."""
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.data = []
    # Make every attribute access + call return the same mock so chaining works
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.delete.return_value = db
    db.update.return_value = db
    db.upsert.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.lt.return_value = db
    db.range.return_value = db
    db.execute.return_value = exec_result
    return db


START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 2, tzinfo=timezone.utc)
ORG_ID = "00000000-0000-0000-0000-000000000001"
INTEGRATION_ID = "00000000-0000-0000-0000-000000000002"
KEY_BYTES = b"sk-admin-testkey1234567890"


# ── _ingest_window ─────────────────────────────────────────────────────────────

class TestIngestWindow:
    def test_inserts_rows_for_events(self) -> None:
        db = _mock_db()
        hour = datetime(2025, 1, 1, 10, tzinfo=timezone.utc)
        events = [_make_event("gpt-4o", 1.50, hour)]

        with patch("api.workers.ingestion._ADAPTERS", {"openai": MagicMock(fetch_costs=MagicMock(return_value=events))}):
            count = _ingest_window(db, INTEGRATION_ID, ORG_ID, "openai", KEY_BYTES, START, END)

        assert count == 1
        # delete called once before insert
        db.delete.assert_called()
        db.insert.assert_called_once()
        inserted_rows = db.insert.call_args[0][0]
        assert len(inserted_rows) == 1
        row = inserted_rows[0]
        assert row["org_id"] == ORG_ID
        assert row["integration_id"] == INTEGRATION_ID
        assert row["provider"] == "openai"
        assert row["model"] == "gpt-4o"
        assert Decimal(row["cost_usd"]) == Decimal("1.50")
        assert row["feature_tag"] is None  # tag-rule engine fills this later

    def test_returns_zero_when_no_events(self) -> None:
        db = _mock_db()
        with patch("api.workers.ingestion._ADAPTERS", {"openai": MagicMock(fetch_costs=MagicMock(return_value=[]))}):
            count = _ingest_window(db, INTEGRATION_ID, ORG_ID, "openai", KEY_BYTES, START, END)

        assert count == 0
        db.insert.assert_not_called()

    def test_raises_for_unsupported_provider(self) -> None:
        db = _mock_db()
        with pytest.raises(ValueError, match="Unsupported provider"):
            _ingest_window(db, INTEGRATION_ID, ORG_ID, "cohere", KEY_BYTES, START, END)

    def test_batches_large_event_sets(self) -> None:
        """Events > 500 should be inserted in multiple batches."""
        db = _mock_db()
        hour = datetime(2025, 1, 1, 10, tzinfo=timezone.utc)
        events = [_make_event("gpt-4o", 0.01, hour) for _ in range(1050)]

        with patch("api.workers.ingestion._ADAPTERS", {"openai": MagicMock(fetch_costs=MagicMock(return_value=events))}):
            count = _ingest_window(db, INTEGRATION_ID, ORG_ID, "openai", KEY_BYTES, START, END)

        assert count == 1050
        # 1050 events → ceil(1050/500) = 3 insert calls
        assert db.insert.call_count == 3

    def test_delete_called_with_correct_window(self) -> None:
        """Existing rows for the time window must be cleared before insert."""
        db = _mock_db()
        with patch("api.workers.ingestion._ADAPTERS", {"openai": MagicMock(fetch_costs=MagicMock(return_value=[]))}):
            _ingest_window(db, INTEGRATION_ID, ORG_ID, "openai", KEY_BYTES, START, END)

        db.gte.assert_any_call("bucket_hour", START.isoformat())
        db.lt.assert_any_call("bucket_hour", END.isoformat())


# ── aggregate_org ─────────────────────────────────────────────────────────────

class TestAggregateOrg:
    def _run_aggregate(self, usage_rows: list[dict]) -> list[dict]:
        """Run aggregate_org with mocked DB returning given usage_rows."""
        exec_with_data = MagicMock()
        exec_with_data.data = usage_rows
        exec_empty = MagicMock()
        exec_empty.data = []

        db = _mock_db()

        # First call to execute() returns usage rows (single page), second returns empty page
        db.execute.side_effect = [exec_with_data, exec_empty]

        upserted: list[dict] = []

        def capture_upsert(rows, **kwargs):
            upserted.extend(rows)
            return db

        db.upsert.side_effect = capture_upsert

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            from api.workers.aggregation import aggregate_org
            aggregate_org(ORG_ID)

        return upserted

    def test_groups_events_by_day_and_model(self) -> None:
        day1 = "2025-01-01T10:00:00+00:00"
        day2 = "2025-01-02T10:00:00+00:00"
        rows = [
            {"provider": "openai", "model": "gpt-4o", "feature_tag": None, "team_tag": None,
             "customer_tag": None, "env_tag": None, "cost_usd": "1.00", "request_count": 2,
             "input_tokens": 1000, "output_tokens": 200, "cached_tokens": 0, "bucket_hour": day1},
            {"provider": "openai", "model": "gpt-4o", "feature_tag": None, "team_tag": None,
             "customer_tag": None, "env_tag": None, "cost_usd": "2.00", "request_count": 3,
             "input_tokens": 2000, "output_tokens": 400, "cached_tokens": 0, "bucket_hour": day1},
            {"provider": "openai", "model": "gpt-4o-mini", "feature_tag": None, "team_tag": None,
             "customer_tag": None, "env_tag": None, "cost_usd": "0.50", "request_count": 5,
             "input_tokens": 500, "output_tokens": 100, "cached_tokens": 0, "bucket_hour": day2},
        ]
        upserted = self._run_aggregate(rows)

        # Two groups: (day1, gpt-4o) and (day2, gpt-4o-mini)
        assert len(upserted) == 2
        by_model = {r["model"]: r for r in upserted}

        assert by_model["gpt-4o"]["total_cost_usd"] == str(Decimal("3.00"))
        assert by_model["gpt-4o"]["total_requests"] == 5
        assert by_model["gpt-4o"]["total_tokens"] == 3600  # 1000+200+0 + 2000+400+0
        assert by_model["gpt-4o"]["day"] == "2025-01-01"

        assert by_model["gpt-4o-mini"]["total_cost_usd"] == str(Decimal("0.50"))
        assert by_model["gpt-4o-mini"]["day"] == "2025-01-02"

    def test_null_tags_coerced_to_empty_string(self) -> None:
        rows = [
            {"provider": "openai", "model": "gpt-4o", "feature_tag": None, "team_tag": None,
             "customer_tag": None, "env_tag": None, "cost_usd": "1.00", "request_count": 1,
             "input_tokens": 100, "output_tokens": 10, "cached_tokens": 0,
             "bucket_hour": "2025-01-01T00:00:00+00:00"},
        ]
        upserted = self._run_aggregate(rows)

        assert len(upserted) == 1
        row = upserted[0]
        assert row["feature_tag"] == ""
        assert row["team_tag"] == ""
        assert row["customer_tag"] == ""
        assert row["env_tag"] == ""

    def test_org_id_set_correctly(self) -> None:
        rows = [
            {"provider": "openai", "model": "gpt-4o", "feature_tag": None, "team_tag": None,
             "customer_tag": None, "env_tag": None, "cost_usd": "1.00", "request_count": 1,
             "input_tokens": 100, "output_tokens": 10, "cached_tokens": 0,
             "bucket_hour": "2025-01-01T00:00:00+00:00"},
        ]
        upserted = self._run_aggregate(rows)

        assert upserted[0]["org_id"] == ORG_ID

    def test_no_upsert_when_no_events(self) -> None:
        db = _mock_db()
        with patch("api.workers.aggregation._get_supabase", return_value=db):
            from api.workers.aggregation import aggregate_org
            aggregate_org(ORG_ID)

        db.upsert.assert_not_called()
