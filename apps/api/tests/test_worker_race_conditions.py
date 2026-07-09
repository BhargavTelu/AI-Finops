"""
Race condition tests for anomaly detection and budget checks workers.

Gap-08 (critical): Concurrent detect_org inserts duplicate anomaly records.
Gap-09 (medium):   Dedup guard with existing open anomaly prevents duplicate insert.
Gap-10 (critical): Concurrent check_org sends duplicate budget alerts.
"""

from datetime import UTC, datetime, timedelta
import threading
from unittest.mock import MagicMock, patch

ORG_ID = "00000000-0000-0000-0000-000000000001"
BUDGET_ID = "cccccccc-0000-0000-0000-000000000001"


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
    db.range.return_value = db
    db.limit.return_value = db
    db.in_.return_value = db
    empty = MagicMock()
    empty.data = []
    db.execute.return_value = empty
    return db


def _history_rows(spike_on_last: bool = True) -> list[dict]:
    """Build 15 daily summary rows, optionally with a cost spike on the last day."""
    today = datetime.now(UTC).date()
    rows = []
    for i in range(15, 0, -1):
        day = (today - timedelta(days=i)).isoformat()
        cost = "50.00" if (i == 1 and spike_on_last) else "1.00"
        rows.append(
            {
                "day": day,
                "model": "gpt-4o",
                "feature_tag": "",
                "team_tag": "",
                "customer_tag": "",
                "total_cost_usd": cost,
            }
        )
    return rows


# ── Gap-08: Concurrent detect_org race ─────────────────────────────────────────


class TestAnomalyDetectionConcurrentRace:
    """
    Gap-08 (critical): No lock on detect_org - two concurrent tasks both see an
    empty dedup state and both insert the same anomaly.
    """

    def test_concurrent_detect_org_documents_duplicate_insert_risk(self) -> None:
        """
        Two threads run detect_org simultaneously. Both:
          1. Read daily_cost_summaries (spike detected)
          2. Query existing open anomalies → empty (race window)
          3. Detect anomaly, insert → duplicate

        This test asserts insert is attempted from both threads (documenting the race).
        Fix: add a UNIQUE constraint on (org_id, scope_kind, scope_value, detected_at::date)
        or a Redis lock. When fixed, update assertion to insert_count == 1.
        """
        from api.workers.anomaly_detection import detect_org

        history = _history_rows(spike_on_last=True)
        insert_count = [0]
        count_lock = threading.Lock()
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def track_insert(data):
            with count_lock:
                insert_count[0] += 1
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        def make_thread_db():
            # Each detect_org call gets its own DB mock with its own responses list,
            # so the two concurrent threads don't interfere with each other's data.
            db = _mock_db()
            responses = [
                MagicMock(data=history),  # daily_cost_summaries
                MagicMock(data=[]),  # open anomalies for today → empty (race!)
            ]

            def execute_side():
                return responses.pop(0) if responses else MagicMock(data=[])

            db.execute.side_effect = execute_side
            db.insert.side_effect = track_insert
            return db

        def run_task():
            try:
                barrier.wait()
                detect_org(ORG_ID)
            except Exception as exc:
                errors.append(exc)

        with (
            patch("api.workers.anomaly_detection._get_supabase", side_effect=make_thread_db),
            patch("api.workers.anomaly_detection.send_anomaly_alert"),
            patch("api.workers.anomaly_detection.explain_anomaly"),
        ):
            t1 = threading.Thread(target=run_task)
            t2 = threading.Thread(target=run_task)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        assert errors == [], f"detect_org raised exceptions: {errors}"
        assert insert_count[0] >= 2, (
            f"Gap-08: Expected both concurrent tasks to attempt insert (no DB-level dedup). "
            f"Got insert_count={insert_count[0]}. "
            "When a UNIQUE constraint or lock is added, update assertion to insert_count == 1."
        )


# ── Gap-09: Dedup guard boundary ───────────────────────────────────────────────


class TestAnomalyDetectionDedupGuard:
    """Gap-09 (medium): Dedup guard (today-scoped open anomaly) prevents duplicate insert."""

    def test_existing_open_anomaly_today_blocks_insert(self) -> None:
        """
        If scope_kind='model', scope_value='gpt-4o' already has an open anomaly
        detected today, detect_org must skip insertion and not fire the alert.
        """
        from api.workers.anomaly_detection import detect_org

        history = _history_rows(spike_on_last=True)
        existing_open = [{"scope_kind": "model", "scope_value": "gpt-4o"}]

        db = _mock_db()
        responses = [
            MagicMock(data=history),  # daily_cost_summaries
            MagicMock(data=existing_open),  # dedup guard: anomaly already open today
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.send_anomaly_alert") as mock_alert,
        ):
            detect_org(ORG_ID)

        db.insert.assert_not_called()
        mock_alert.delay.assert_not_called()

    def test_no_prior_anomaly_today_allows_insert(self) -> None:
        """If no open anomaly exists for this scope today, insertion must proceed."""
        from api.workers.anomaly_detection import detect_org

        history = _history_rows(spike_on_last=True)

        db = _mock_db()
        responses = [
            MagicMock(data=history),  # daily_cost_summaries
            MagicMock(data=[]),  # no open anomalies today → insert allowed
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side
        db.insert.return_value = MagicMock(**{"execute.return_value": MagicMock(data=[])})

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.send_anomaly_alert"),
            patch("api.workers.anomaly_detection.explain_anomaly"),
        ):
            detect_org(ORG_ID)

        db.insert.assert_called_once()

    def test_insufficient_history_produces_no_anomaly(self) -> None:
        """Fewer than 15 days of history → detect_anomalies returns None → no insert."""
        from api.workers.anomaly_detection import detect_org

        # Only 10 days of history (below the 15-day minimum)
        today = datetime.now(UTC).date()
        short_history = [
            {
                "day": (today - timedelta(days=i)).isoformat(),
                "model": "gpt-4o",
                "feature_tag": "",
                "team_tag": "",
                "customer_tag": "",
                "total_cost_usd": "1.00",
            }
            for i in range(10, 0, -1)
        ]

        db = _mock_db()
        responses = [
            MagicMock(data=short_history),  # only 10 rows
            MagicMock(data=[]),  # dedup (irrelevant)
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.send_anomaly_alert") as mock_alert,
        ):
            detect_org(ORG_ID)

        db.insert.assert_not_called()
        mock_alert.delay.assert_not_called()


# ── Gap-10: Concurrent check_org budget alerts ─────────────────────────────────


class TestBudgetCheckConcurrentRace:
    """
    Gap-10 (critical): No atomic check-and-set on notified_80_at.
    Two concurrent check_org tasks both see notified_80_at=None and both fire alerts.
    """

    def test_concurrent_check_org_documents_double_alert_risk(self) -> None:
        """
        Two threads run check_org simultaneously. Both read notified_80_at=None
        and both decide to alert (spend is 85% of limit). Both call
        send_budget_alert.delay independently - two emails for one threshold crossing.

        When a SELECT FOR UPDATE or Redis lock is added, update assertion to count == 1.
        """
        from api.workers.budget_checks import check_org

        budget_data = {
            "id": BUDGET_ID,
            "org_id": ORG_ID,
            "scope_type": "global",
            "scope_value": None,
            "monthly_limit": "1000.00",
            "alert_at_pct": 80,
            "notified_80_at": None,  # neither thread has seen an alert yet
            "notified_100_at": None,
        }
        spend_rows = [{"total_cost_usd": "850.00"}]  # 85% → triggers 80% threshold

        alert_count = [0]
        count_lock = threading.Lock()
        barrier = threading.Barrier(2)

        def make_thread_db():
            # Each check_org call gets its own DB mock with its own response
            # sequence, so the two concurrent threads don't share a counter.
            db = _mock_db()
            call_n = [0]

            def execute_side():
                call_n[0] += 1
                if call_n[0] == 1:
                    return MagicMock(data=[budget_data])
                return MagicMock(data=spend_rows)

            db.execute.side_effect = execute_side
            return db

        def run_task():
            try:
                barrier.wait()
                check_org(ORG_ID)
            except Exception as exc:
                errors.append(exc)

        errors: list[Exception] = []

        # Patch module globals ONCE in the main thread. Patching from inside
        # concurrent threads is a race: one thread's teardown restores the
        # other's mock as the "original", leaving the module permanently
        # patched after the test and corrupting later tests.
        with (
            patch("api.workers.budget_checks._get_supabase", side_effect=make_thread_db),
            patch("api.workers.budget_checks.send_budget_alert") as mock_alert,
        ):

            def track(*args, **kwargs):
                with count_lock:
                    alert_count[0] += 1

            mock_alert.delay.side_effect = track

            t1 = threading.Thread(target=run_task)
            t2 = threading.Thread(target=run_task)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        assert errors == [], f"check_org raised exceptions: {errors}"

        assert alert_count[0] >= 2, (
            f"Gap-10: Expected both concurrent tasks to fire alert (no atomic lock). "
            f"Got alert_count={alert_count[0]}. "
            "BUG-04: Add SELECT FOR UPDATE or a Redis lock to prevent double-alerting. "
            "When fixed, update assertion to alert_count == 1."
        )

    def test_same_calendar_month_prevents_second_alert(self) -> None:
        """
        If notified_80_at is already set to a timestamp in the current calendar month,
        a second check_org run must NOT fire the alert again.
        """
        from api.workers.budget_checks import check_org

        now_iso = datetime.now(UTC).isoformat()
        budget_data = {
            "id": BUDGET_ID,
            "org_id": ORG_ID,
            "scope_type": "global",
            "scope_value": None,
            "monthly_limit": "1000.00",
            "alert_at_pct": 80,
            "notified_80_at": now_iso,  # already alerted this month
            "notified_100_at": None,
        }
        spend_rows = [{"total_cost_usd": "850.00"}]

        db = _mock_db()
        call_n = [0]

        def execute_side():
            call_n[0] += 1
            if call_n[0] == 1:
                return MagicMock(data=[budget_data])
            return MagicMock(data=spend_rows)

        db.execute.side_effect = execute_side

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks.send_budget_alert") as mock_alert,
        ):
            check_org(ORG_ID)

        mock_alert.delay.assert_not_called()
