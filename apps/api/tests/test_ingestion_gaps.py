"""
Ingestion worker gap tests - gap-analysis batch 2.

Gap-05 (critical): Concurrent refresh_integration race (no distributed lock).
Gap-06 (critical): Partial batch insert failure - last_synced_at must NOT advance.
Gap-07 (high):     refresh_all_integrations enqueues exactly one task per active integration.
"""

import base64
import threading
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from api.services.encryption import EncryptionService

ORG_ID = "00000000-0000-0000-0000-000000000001"
INT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
INT_ID_2 = "bbbbbbbb-0000-0000-0000-000000000002"

_KEY_B64 = base64.b64encode(b"\xcc" * 32).decode()
_CIPHER = EncryptionService(_KEY_B64)


def _encrypted_key_hex() -> str:
    return "\\x" + _CIPHER.encrypt(b"sk-test-key").hex()


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.upsert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.lt.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.in_.return_value = db
    db.range.return_value = db
    empty = MagicMock()
    empty.data = []
    db.execute.return_value = empty
    return db


# ── Gap-05: Concurrent refresh race ────────────────────────────────────────────

class TestConcurrentRefreshRace:
    """
    Gap-05 (critical): Two concurrent refresh_integration tasks for the same integration
    both call _ingest_window independently - no distributed lock prevents double-execution.
    """

    def test_concurrent_refresh_documents_known_race(self) -> None:
        """
        Two threads run refresh_integration simultaneously. Without a lock:
          - Both read last_synced_at at T1
          - Both call _ingest_window([T1, now))
          - Both delete then re-insert the same window of events

        This test asserts _ingest_window is called twice (documenting the race).
        When a Redis SETNX or advisory lock is added, update assertion to count == 1.
        """
        from api.workers.ingestion import refresh_integration

        ingest_call_count = [0]
        count_lock = threading.Lock()
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def mock_ingest_window(db, integration_id, org_id, provider, key_bytes, start, end):
            with count_lock:
                ingest_call_count[0] += 1
            return 10

        integration_data = {
            "provider": "openai",
            "api_key_enc": _encrypted_key_hex(),
            "last_synced_at": "2026-05-20T00:00:00+00:00",
            "status": "active",
        }

        def run_task():
            try:
                db = _mock_db()
                db.execute.return_value = MagicMock(data=[integration_data])
                barrier.wait()
                with (
                    patch("api.workers.ingestion._get_supabase", return_value=db),
                    patch("api.workers.ingestion._ingest_window", side_effect=mock_ingest_window),
                    patch("api.workers.ingestion.EncryptionService", return_value=_CIPHER),
                    patch("api.workers.ingestion.settings") as ms,
                ):
                    ms.encryption_key = _KEY_B64
                    refresh_integration.apply(args=[INT_ID, ORG_ID])
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=run_task)
        t2 = threading.Thread(target=run_task)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert errors == [], f"Concurrent refresh_integration raised exceptions: {errors}"
        assert ingest_call_count[0] == 2, (
            f"Gap-05: Expected _ingest_window to be called twice (no lock). "
            f"Got {ingest_call_count[0]}. "
            "If count == 1, a distributed lock was added - update assertion to count == 1."
        )


# ── Gap-06: Partial batch failure ──────────────────────────────────────────────

class TestPartialBatchInsertFailure:
    """
    Gap-06 (critical): If a mid-batch insert fails, last_synced_at must NOT be
    updated - otherwise the next retry skips the failed window entirely.
    """

    def test_batch_failure_sets_error_status_not_last_synced(self) -> None:
        """
        _ingest_window inserts events in 500-row batches via a loop. If batch 2
        of 2 raises, batch 1 is already committed (Supabase has no cross-request TX).
        backfill_integration must catch the error and:
          - Update status='error' and last_error=<message>
          - NOT update last_synced_at (so retry re-ingests from the beginning)
        """
        from api.workers.ingestion import backfill_integration
        from api.adapters.base import NormalizedUsageEvent

        # 501 events → two batches (500 + 1); second batch raises
        fake_event = NormalizedUsageEvent(
            provider="openai",
            model="gpt-4o",
            api_key_label=None,
            input_tokens=100,
            output_tokens=50,
            cached_tokens=0,
            cost_usd=Decimal("0.01"),
            request_count=1,
            bucket_hour=datetime(2026, 5, 1),
            raw_meta={},
        )
        events_501 = [fake_event] * 501

        integration_row = {
            "provider": "openai",
            "api_key_enc": _encrypted_key_hex(),
            "status": "active",
        }

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[integration_row])

        insert_call_count = [0]

        def failing_insert(rows):
            insert_call_count[0] += 1
            if insert_call_count[0] >= 2:
                raise Exception("DB constraint violation on batch 2")
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.insert.side_effect = failing_insert

        updated_payloads: list[dict] = []

        def capture_update(data):
            updated_payloads.append(data)
            return db

        db.update.side_effect = capture_update

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter(events_501)

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.EncryptionService", return_value=_CIPHER),
            patch("api.workers.ingestion.settings") as ms,
            patch("api.workers.ingestion.compile_rules", return_value=[]),
            patch("api.workers.ingestion.apply_rules", return_value={
                "feature_tag": None, "team_tag": None,
                "customer_tag": None, "env_tag": None,
            }),
        ):
            ms.encryption_key = _KEY_B64
            backfill_integration.apply(args=[INT_ID, ORG_ID])

        # At least one update must have happened (error path)
        assert updated_payloads, "Expected at least one db.update call after batch failure"

        # The error update must contain 'error' status
        error_updates = [p for p in updated_payloads if p.get("status") == "error"]
        assert error_updates, (
            f"Expected an update with status='error' after batch failure. "
            f"Got updates: {updated_payloads}"
        )

        # CRITICAL: last_synced_at must NOT appear in any update that also sets 'error'
        for update in error_updates:
            assert "last_synced_at" not in update, (
                f"Gap-06: last_synced_at was set on the error update - "
                f"next retry will advance past the failed window. Update: {update}"
            )

    def test_successful_ingest_updates_last_synced_at(self) -> None:
        """Baseline: a successful backfill must update last_synced_at."""
        from api.workers.ingestion import backfill_integration
        from api.adapters.base import NormalizedUsageEvent

        fake_event = NormalizedUsageEvent(
            provider="openai",
            model="gpt-4o",
            api_key_label=None,
            input_tokens=100,
            output_tokens=50,
            cached_tokens=0,
            cost_usd=Decimal("0.01"),
            request_count=1,
            bucket_hour=datetime(2026, 5, 1),
            raw_meta={},
        )

        integration_row = {
            "provider": "openai",
            "api_key_enc": _encrypted_key_hex(),
            "status": "active",
        }

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[integration_row])

        updated_payloads: list[dict] = []

        def capture_update(data):
            updated_payloads.append(data)
            return db

        db.update.side_effect = capture_update

        mock_adapter = MagicMock()
        mock_adapter.fetch_costs.return_value = iter([fake_event])

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion._ADAPTERS", {"openai": mock_adapter}),
            patch("api.workers.ingestion.EncryptionService", return_value=_CIPHER),
            patch("api.workers.ingestion.settings") as ms,
            patch("api.workers.ingestion.compile_rules", return_value=[]),
            patch("api.workers.ingestion.apply_rules", return_value={
                "feature_tag": None, "team_tag": None,
                "customer_tag": None, "env_tag": None,
            }),
            patch("api.workers.aggregation.aggregate_org"),
        ):
            ms.encryption_key = _KEY_B64
            backfill_integration.apply(args=[INT_ID, ORG_ID])

        success_updates = [p for p in updated_payloads if "last_synced_at" in p]
        assert success_updates, (
            f"Expected last_synced_at to be set on success. Updates: {updated_payloads}"
        )


# ── Gap-07: refresh_all_integrations task ──────────────────────────────────────

class TestRefreshAllIntegrations:
    """Gap-07 (high): refresh_all_integrations enqueues exactly one task per active integration."""

    def test_enqueues_one_task_per_active_integration(self) -> None:
        """Two active integrations → two refresh_integration.delay calls."""
        from api.workers.ingestion import refresh_all_integrations

        active = [
            {"id": INT_ID, "org_id": ORG_ID},
            {"id": INT_ID_2, "org_id": ORG_ID},
        ]

        db = _mock_db()
        db.execute.return_value = MagicMock(data=active)

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion.refresh_integration") as mock_refresh,
        ):
            refresh_all_integrations()

        assert mock_refresh.delay.call_count == 2
        dispatched = {(c.args[0], c.args[1]) for c in mock_refresh.delay.call_args_list}
        assert (INT_ID, ORG_ID) in dispatched
        assert (INT_ID_2, ORG_ID) in dispatched

    def test_sweeps_active_and_errored_but_not_revoked(self) -> None:
        """
        BUG-H3: the sweep previously selected status='active' only, so one
        exhausted-retries failure permanently (and silently) stopped sync.
        It must include 'error' so transient failures self-heal; 'revoked'
        stays terminal.
        """
        from api.workers.ingestion import refresh_all_integrations

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[{"id": INT_ID, "org_id": ORG_ID}])

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion.refresh_integration") as mock_refresh,
        ):
            refresh_all_integrations()

        in_args = [c.args for c in db.in_.call_args_list]
        assert ("status", ["active", "error"]) in in_args, (
            f"Expected .in_('status', ['active', 'error']). Got: {in_args}"
        )
        assert mock_refresh.delay.call_count == 1

    def test_no_active_integrations_enqueues_nothing(self) -> None:
        """If no active integrations exist, no tasks are enqueued."""
        from api.workers.ingestion import refresh_all_integrations

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[])

        with (
            patch("api.workers.ingestion._get_supabase", return_value=db),
            patch("api.workers.ingestion.refresh_integration") as mock_refresh,
        ):
            refresh_all_integrations()

        mock_refresh.delay.assert_not_called()
