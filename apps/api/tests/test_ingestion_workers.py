"""
Worker tests for ingestion tasks.
TC-ING-06: backfill_integration with revoked status returns early.
TC-ING-07: backfill_integration stores error in DB on adapter exception.
TC-ING-08: refresh_integration falls back to 4h lookback when last_synced_at is None.
TC-ING-09: _ingest_window applies tag rules to events.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
            backfill_integration.apply(args=[INT_ID, ORG_ID])

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

        db = _mock_db()

        start = datetime(2026, 5, 1, tzinfo=UTC)
        end = datetime(2026, 5, 2, tzinfo=UTC)

        fake_event = NormalizedUsageEvent(
            provider="openai",
            model="gpt-4o",
            api_key_label="production-feature-a",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=0,
            cost_usd=Decimal("0.05"),
            request_count=1,
            bucket_hour=datetime(2026, 5, 1, 0, tzinfo=UTC),
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
            {
                "match_type": "contains",
                "match_pattern": "feature-a",
                "tags": {"type": "feature_tag", "name": "checkout"},
            }
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

        applied_tags = {
            "feature_tag": "checkout",
            "team_tag": None,
            "customer_tag": None,
            "env_tag": None,
        }

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


# ── M1-U-ING-005: Delete-before-insert ordering ───────────────────────────────


class TestIngestWindowIdempotency:
    def test_delete_called_before_insert(self) -> None:  # M1-U-ING-005
        """
        _ingest_window must delete existing rows before inserting new ones.
        This ensures idempotency on task retry: running the same window twice
        yields the same final state with no duplicates.
        """

        from api.adapters.base import NormalizedUsageEvent

        db = _mock_db()
        start = datetime(2026, 5, 1, tzinfo=UTC)
        end = datetime(2026, 5, 2, tzinfo=UTC)

        fake_event = NormalizedUsageEvent(
            provider="openai",
            model="gpt-4o",
            api_key_label="test-key",
            input_tokens=100,
            output_tokens=50,
            cached_tokens=0,
            cost_usd=Decimal("0.01"),
            request_count=1,
            bucket_hour=datetime(2026, 5, 1, 0, tzinfo=UTC),
            raw_meta={},
        )

        call_order: list[str] = []

        def track_delete(*args, **kwargs):
            call_order.append("delete")
            return db

        def capture_insert(rows: list[dict]) -> MagicMock:
            call_order.append("insert")
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.delete.side_effect = track_delete
        db.insert.side_effect = capture_insert

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter([fake_event])
        empty_tags = {
            "feature_tag": None,
            "team_tag": None,
            "customer_tag": None,
            "env_tag": None,
        }

        with (
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.compile_rules", return_value=[]),
            patch("api.workers.ingestion.apply_rules", return_value=empty_tags),
        ):
            _ingest_window(db, INT_ID, ORG_ID, "openai", b"sk-test", start, end)

        assert "delete" in call_order, "Expected delete() to be called"
        assert "insert" in call_order, "Expected insert() to be called"
        delete_idx = call_order.index("delete")
        insert_idx = call_order.index("insert")
        assert (
            delete_idx < insert_idx
        ), f"delete() must precede insert() for idempotency. Actual order: {call_order}"


# ── M1-U-ING-006: Batch insert size = _BATCH_SIZE ─────────────────────────────


class TestIngestWindowBatchSize:
    def test_batch_insert_in_chunks_of_batch_size(self) -> None:  # M1-U-ING-006
        """
        _ingest_window must split inserts into chunks of _BATCH_SIZE (500) rows.
        For 1200 events this means 3 insert calls: 500 + 500 + 200.
        """

        from api.adapters.base import NormalizedUsageEvent
        from api.workers.ingestion import _BATCH_SIZE

        db = _mock_db()
        start = datetime(2026, 5, 1, tzinfo=UTC)
        end = datetime(2026, 5, 2, tzinfo=UTC)

        total = _BATCH_SIZE * 2 + 200  # 1200 if _BATCH_SIZE == 500
        events = [
            NormalizedUsageEvent(
                provider="openai",
                model="gpt-4o",
                api_key_label="test-key",
                input_tokens=100,
                output_tokens=50,
                cached_tokens=0,
                cost_usd=Decimal("0.01"),
                request_count=1,
                bucket_hour=datetime(2026, 5, 1, 0, tzinfo=UTC),
                raw_meta={},
            )
            for _ in range(total)
        ]

        insert_batch_sizes: list[int] = []

        def capture_insert(rows: list[dict]) -> MagicMock:
            insert_batch_sizes.append(len(rows))
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.insert.side_effect = capture_insert

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter(events)
        empty_tags = {
            "feature_tag": None,
            "team_tag": None,
            "customer_tag": None,
            "env_tag": None,
        }

        with (
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.compile_rules", return_value=[]),
            patch("api.workers.ingestion.apply_rules", return_value=empty_tags),
        ):
            count = _ingest_window(db, INT_ID, ORG_ID, "openai", b"sk-test", start, end)

        assert count == total
        expected_batches = 3  # 500 + 500 + 200
        assert len(insert_batch_sizes) == expected_batches, (
            f"Expected {expected_batches} batches ({_BATCH_SIZE}+{_BATCH_SIZE}+200). "
            f"Got {len(insert_batch_sizes)}: {insert_batch_sizes}"
        )
        assert (
            max(insert_batch_sizes) <= _BATCH_SIZE
        ), f"No batch should exceed _BATCH_SIZE={_BATCH_SIZE}. Got: {insert_batch_sizes}"
        assert sum(insert_batch_sizes) == total


# ── BUG-C1: delete window must match the day-floored fetch window ───────────────


class TestIngestWindowDayFloorsDeleteWindow:
    """
    Adapters fetch complete 1d buckets (the OpenAI adapter floors the fetch
    window to UTC day boundaries), so a mid-day refresh start (last_synced_at)
    re-fetches today's full-day bucket stamped at 00:00. If the delete window
    starts at the raw mid-day timestamp, the earlier snapshot of that bucket
    survives the delete and the day is double-counted on every 4h refresh.
    """

    def test_delete_window_floored_to_utc_day(self) -> None:
        db = _mock_db()
        start = datetime(2026, 6, 10, 14, 23, 5, tzinfo=UTC)
        end = datetime(2026, 6, 10, 18, 23, 5, tzinfo=UTC)

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter([])

        with patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}):
            _ingest_window(db, INT_ID, ORG_ID, "openai", b"sk-test", start, end)

        floored_iso = datetime(2026, 6, 10, 0, 0, 0, tzinfo=UTC).isoformat()
        gte_args = [c.args for c in db.gte.call_args_list]

        assert (
            "bucket_hour",
            floored_iso,
        ) in gte_args, f"Delete/snapshot lower bound must be the day-floored start. Got: {gte_args}"
        assert ("bucket_hour", start.isoformat()) not in gte_args, (
            "Raw mid-day start must not be used as the bucket_hour lower bound - "
            "it leaves the day's earlier bucket snapshot in place (double-count)."
        )

    def test_naive_start_treated_as_utc(self) -> None:
        db = _mock_db()
        # last_synced_at can parse as a naive datetime depending on the DB driver
        start = datetime(2026, 6, 10, 4, 0, 0)
        end = datetime(2026, 6, 10, 8, 0, 0, tzinfo=UTC)

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter([])

        with patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}):
            _ingest_window(db, INT_ID, ORG_ID, "openai", b"sk-test", start, end)

        floored_iso = datetime(2026, 6, 10, 0, 0, 0, tzinfo=UTC).isoformat()
        gte_args = [c.args for c in db.gte.call_args_list]
        assert ("bucket_hour", floored_iso) in gte_args


# ── BUG-H3: errored integrations recover on successful refresh ──────────────────


class TestRefreshRecoversErroredIntegration:
    def test_success_resets_status_to_active(self) -> None:
        """
        A refresh that succeeds after a prior failure must set status back to
        'active' - otherwise the integration stays in 'error' and (before the
        sweep fix) was silently excluded from all future refreshes.
        """
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
                    "last_synced_at": None,
                    "status": "error",  # previously failed
                }
            ]
        )

        update_payloads: list[dict] = []

        def capture_update(payload: dict) -> MagicMock:
            update_payloads.append(payload)
            m = MagicMock()
            m.eq.return_value = m
            m.execute.return_value = MagicMock(data=[])
            return m

        db.update.side_effect = capture_update

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter([])

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.EncryptionService", return_value=cipher),
            patch("api.workers.ingestion.settings") as mock_settings,
            patch("api.workers.ingestion.compile_rules", return_value=[]),
        ):
            mock_settings.encryption_key = key_b64
            refresh_integration.apply(args=[INT_ID, ORG_ID])

        success_updates = [p for p in update_payloads if "last_synced_at" in p]
        assert success_updates, f"Expected a success update. Got: {update_payloads}"
        assert success_updates[-1].get("status") == "active", (
            "Successful refresh must reset status to 'active' so a previously "
            f"errored integration recovers. Got: {success_updates[-1]}"
        )
