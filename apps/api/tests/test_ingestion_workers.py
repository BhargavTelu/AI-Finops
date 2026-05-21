"""
Worker tests for ingestion tasks.
TC-ING-06: backfill_integration with revoked status returns early.
TC-ING-07: backfill_integration stores error in DB on adapter exception.
TC-ING-08: refresh_integration falls back to 4h lookback when last_synced_at is None.
TC-ING-09: _ingest_window applies tag rules to events.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from api.workers.ingestion import _ingest_window, backfill_integration, refresh_integration

ORG_ID = "00000000-0000-0000-0000-000000000001"
INT_ID = "aaaaaaaa-0000-0000-0000-000000000001"


# ── DB mock helpers ─────────────────────────────────────────────────────────────

def _mock_db() -> MagicMock:
    db = MagicMock()
    empty = MagicMock()
    empty.data = []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.lt.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = empty
    return db


def _integration_row(status: str = "active") -> dict:
    import base64
    from api.services.encryption import EncryptionService

    key_b64 = base64.b64encode(b"\xcc" * 32).decode()
    cipher = EncryptionService(key_b64)
    encrypted = cipher.encrypt(b"sk-test-key")

    return {
        "id": INT_ID,
        "org_id": ORG_ID,
        "provider": "openai",
        "api_key_enc": "\\x" + encrypted.hex(),
        "last_synced_at": None,
        "status": status,
    }


# ── TC-ING-06: revoked integration returns early ───────────────────────────────

class TestBackfillRevoked:
    def test_revoked_integration_returns_early(self) -> None:  # TC-ING-06
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_integration_row(status="revoked")])

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion._ADAPTERS") as mock_adapters,
        ):
            backfill_integration.apply(args=[INT_ID, ORG_ID])

        # Adapter should never be called for revoked integrations
        mock_adapters.get.assert_not_called()


# ── TC-ING-07: stores error on adapter exception ───────────────────────────────

class TestBackfillStoresError:
    def test_adapter_exception_stores_error_in_db(self) -> None:  # TC-ING-07
        import base64
        from api.services.encryption import EncryptionService

        key_b64 = base64.b64encode(b"\xcc" * 32).decode()
        cipher = EncryptionService(key_b64)
        encrypted = cipher.encrypt(b"sk-test-key")

        db = _mock_db()
        db.execute.return_value = MagicMock(
            data=[
                {
                    "provider": "openai",
                    "api_key_enc": "\\x" + encrypted.hex(),
                    "status": "active",
                }
            ]
        )

        # Adapter raises on fetch_costs
        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.side_effect = ValueError("Provider API error")

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.EncryptionService", return_value=cipher),
            patch("api.workers.ingestion.settings") as mock_settings,
        ):
            mock_settings.encryption_key = key_b64
            # apply() runs the task synchronously; max_retries=3 means it may retry
            result = backfill_integration.apply(args=[INT_ID, ORG_ID])

        # DB update with status="error" and last_error set must have been called
        update_calls = str(db.update.call_args_list)
        assert "error" in update_calls.lower()


# ── TC-ING-08: refresh fallback to 4h window ──────────────────────────────────

class TestRefreshFallback:
    def test_no_last_synced_uses_4h_lookback(self) -> None:  # TC-ING-08
        import base64
        from api.services.encryption import EncryptionService

        key_b64 = base64.b64encode(b"\xcc" * 32).decode()
        cipher = EncryptionService(key_b64)
        encrypted = cipher.encrypt(b"sk-test-key")

        db = _mock_db()
        db.execute.return_value = MagicMock(
            data=[
                {
                    "provider": "openai",
                    "api_key_enc": "\\x" + encrypted.hex(),
                    "last_synced_at": None,  # no prior sync
                    "status": "active",
                }
            ]
        )

        fetch_calls: list = []

        def capture_fetch(key, start, end):
            fetch_calls.append((start, end))
            return iter([])  # return empty events

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.side_effect = capture_fetch

        now = datetime.now(timezone.utc)

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.EncryptionService", return_value=cipher),
            patch("api.workers.ingestion.settings") as mock_settings,
            patch("api.workers.ingestion.compile_rules", return_value=[]),
            patch("api.workers.ingestion.apply_rules", return_value={}),
        ):
            mock_settings.encryption_key = key_b64
            refresh_integration.apply(args=[INT_ID, ORG_ID])

        assert len(fetch_calls) == 1
        start_used, end_used = fetch_calls[0]
        # The lookback should be approximately 4 hours before now
        diff_hours = (end_used - start_used).total_seconds() / 3600
        assert 3.9 <= diff_hours <= 4.1, f"Expected ~4h window, got {diff_hours:.2f}h"


# ── TC-ING-09: _ingest_window applies tag rules ────────────────────────────────

class TestIngestWindowTagRules:
    def test_tag_rules_applied_to_events(self) -> None:  # TC-ING-09
        from api.adapters.base import NormalizedUsageEvent
        from decimal import Decimal as D

        db = _mock_db()

        start = datetime(2026, 5, 1, tzinfo=timezone.utc)
        end = datetime(2026, 5, 2, tzinfo=timezone.utc)

        fake_event = NormalizedUsageEvent(
            provider="openai",
            model="gpt-4o",
            api_key_label="production-feature-a",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=0,
            cost_usd=D("0.05"),
            request_count=1,
            bucket_hour=datetime(2026, 5, 1, 0, tzinfo=timezone.utc),
            raw_meta={},
        )

        tag_rules_result = MagicMock()
        tag_rules_result.data = [
            {
                "match_type": "contains",
                "match_pattern": "feature-a",
                "priority": 1,
                "enabled": True,
                "tags": {"type": "feature_tag", "name": "checkout"},
            }
        ]

        compiled_rules = [
            {"match_type": "contains", "match_pattern": "feature-a", "tags": {"type": "feature_tag", "name": "checkout"}}
        ]

        inserted_rows: list[dict] = []

        def capture_insert(rows: list[dict]) -> MagicMock:
            inserted_rows.extend(rows)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.insert.side_effect = capture_insert

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter([fake_event])

        applied_tags = {"feature_tag": "checkout", "team_tag": None, "customer_tag": None, "env_tag": None}

        with (
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.compile_rules", return_value=compiled_rules),
            patch("api.workers.ingestion.apply_rules", return_value=applied_tags),
        ):
            count = _ingest_window(db, INT_ID, ORG_ID, "openai", b"sk-test", start, end)

        assert count == 1
        assert len(inserted_rows) == 1
        row = inserted_rows[0]
        assert row["feature_tag"] == "checkout"
