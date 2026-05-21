"""
Aggregation worker tests — gap-analysis batch 2.

Gap-01 (critical):  aggregate_org happy path — 0% direct coverage; verify the pipeline.
Gap-02 (critical):  Concurrent aggregate_org race condition (no distributed lock).
Gap-03 (high):      Pagination terminates correctly even when a partial page is returned.
Gap-04 (medium):    NULL and empty-string tags coalesce into the same summary group.
"""

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

ORG_ID = "00000000-0000-0000-0000-000000000001"


# ── shared mock helpers ──────────────────────────────────────────────────────────

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
    db.in_.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.range.return_value = db
    empty = MagicMock()
    empty.data = []
    db.execute.return_value = empty
    return db


def _event_row(model: str, cost: str, feature_tag: str = "") -> dict:
    today = datetime.now(timezone.utc).date()
    bucket_ts = (today - timedelta(days=1)).isoformat() + "T00:00:00+00:00"
    return {
        "provider": "openai",
        "model": model,
        "feature_tag": feature_tag,
        "team_tag": "",
        "customer_tag": "",
        "env_tag": "",
        "cost_usd": cost,
        "request_count": 1,
        "input_tokens": 100,
        "output_tokens": 50,
        "cached_tokens": 0,
        "bucket_hour": bucket_ts,
    }


# ── Gap-01: Happy path ──────────────────────────────────────────────────────────

class TestAggregationHappyPath:
    """Gap-01: aggregate_org has 0% direct coverage — verify the core pipeline."""

    def test_groups_events_and_upserts_correct_summaries(self) -> None:
        """
        Three usage_events across two distinct (model, feature_tag) groups on the same
        day must produce exactly two upserted summary rows with correctly summed costs.
        """
        from api.workers.aggregation import aggregate_org

        events = [
            _event_row("gpt-4o", "5.00", "chat"),
            _event_row("gpt-4o", "3.00", "chat"),    # same group as above
            _event_row("claude-sonnet-4-5", "2.00", "api"),  # different group
        ]

        db = _mock_db()
        upserted_rows: list[dict] = []

        responses = [
            MagicMock(data=[{"id": "int-aaa"}]),  # integrations
            MagicMock(data=[]),                    # delete summaries
            MagicMock(data=events),               # first pagination page
            MagicMock(data=[]),                    # empty → stop pagination
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        def capture_upsert(rows, on_conflict=None):
            upserted_rows.extend(rows)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.upsert.side_effect = capture_upsert

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            aggregate_org(ORG_ID)

        assert len(upserted_rows) == 2, (
            f"Expected 2 summary rows (2 distinct groups), got {len(upserted_rows)}"
        )

        gpt_row = next((r for r in upserted_rows if r["model"] == "gpt-4o"), None)
        assert gpt_row is not None, "gpt-4o summary row missing"
        assert Decimal(gpt_row["total_cost_usd"]) == Decimal("8.00"), (
            f"Expected gpt-4o total cost 8.00, got {gpt_row['total_cost_usd']}"
        )
        assert gpt_row["total_requests"] == 2

        claude_row = next((r for r in upserted_rows if r["model"] == "claude-sonnet-4-5"), None)
        assert claude_row is not None, "claude-sonnet-4-5 summary row missing"
        assert Decimal(claude_row["total_cost_usd"]) == Decimal("2.00")

    def test_no_active_integrations_skips_upsert(self) -> None:
        """If no active integrations exist, delete still runs but no upsert happens."""
        from api.workers.aggregation import aggregate_org

        db = _mock_db()
        responses = [
            MagicMock(data=[]),  # integrations → empty
            MagicMock(data=[]),  # delete summaries
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            aggregate_org(ORG_ID)

        db.upsert.assert_not_called()

    def test_no_usage_events_skips_upsert(self) -> None:
        """If active integrations exist but no usage_events match, no upsert happens."""
        from api.workers.aggregation import aggregate_org

        db = _mock_db()
        responses = [
            MagicMock(data=[{"id": "int-aaa"}]),  # active integration
            MagicMock(data=[]),                    # delete summaries
            MagicMock(data=[]),                    # no events on first page
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            aggregate_org(ORG_ID)

        db.upsert.assert_not_called()

    def test_delete_scoped_to_org_id(self) -> None:
        """The summaries delete must be scoped to org_id to avoid cross-org data wipe."""
        from api.workers.aggregation import aggregate_org

        db = _mock_db()
        responses = [
            MagicMock(data=[]),  # no integrations → early return
            MagicMock(data=[]),  # delete call
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            aggregate_org(ORG_ID)

        # eq(org_id, ...) must have been called at least once during the delete chain
        eq_calls = [str(c) for c in db.eq.call_args_list]
        assert any(ORG_ID in call for call in eq_calls), (
            "Expected delete query to filter by org_id to prevent cross-org data wipe"
        )


# ── Gap-02: Concurrent race condition ──────────────────────────────────────────

class TestAggregationConcurrentRace:
    """
    Gap-02 (critical): No distributed lock on aggregate_org.
    Two concurrent tasks both delete then upsert — second delete wipes first upsert.
    This test documents the known race (does not assert correctness under concurrency).
    """

    def test_concurrent_aggregate_org_both_complete_without_exception(self) -> None:
        """
        Both concurrent tasks must complete without raising.
        The delete_call_count >= 2 assertion documents that no lock prevented
        double-execution (the known race condition).
        When a distributed lock is added, update to assert delete_call_count == 1.
        """
        from api.workers.aggregation import aggregate_org

        today = datetime.now(timezone.utc).date()
        bucket_ts = (today - timedelta(days=1)).isoformat() + "T00:00:00+00:00"
        event = _event_row("gpt-4o", "10.00")

        delete_count = [0]
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def make_db():
            db = _mock_db()
            responses = [
                MagicMock(data=[{"id": "int-aaa"}]),  # integrations
                MagicMock(data=[]),                    # delete summaries
                MagicMock(data=[event]),              # events page 1
                MagicMock(data=[]),                    # events page 2 (done)
            ]

            def execute_side():
                return responses.pop(0) if responses else MagicMock(data=[])

            db.execute.side_effect = execute_side

            original_delete = db.delete

            def track_delete(*args, **kwargs):
                with lock:
                    delete_count[0] += 1
                return db

            db.delete.side_effect = track_delete

            def capture_upsert(rows, on_conflict=None):
                m = MagicMock()
                m.execute.return_value = MagicMock(data=[])
                return m

            db.upsert.side_effect = capture_upsert
            return db

        def run_task():
            try:
                barrier.wait()
                aggregate_org(ORG_ID)
            except Exception as exc:
                errors.append(exc)

        # Patch once with side_effect so each call gets a fresh independent DB mock.
        # Patching inside each thread would race (both overwrite the same target).
        with patch("api.workers.aggregation._get_supabase", side_effect=make_db):
            t1 = threading.Thread(target=run_task)
            t2 = threading.Thread(target=run_task)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        assert errors == [], f"Concurrent aggregate_org raised exceptions: {errors}"
        # Document: no lock means both tasks ran delete independently
        assert delete_count[0] >= 2, (
            f"Expected both concurrent tasks to run delete independently (no lock). "
            f"delete_count={delete_count[0]}. "
            "If this fails (count==1), a distributed lock was added — "
            "update assertion to delete_count[0] == 1."
        )


# ── Gap-03: Pagination terminates on partial page ──────────────────────────────

class TestAggregationPagination:
    """Gap-03 (high): Verify pagination terminates when the last page is smaller than PAGE_SIZE."""

    def test_partial_last_page_stops_pagination(self) -> None:
        """
        _PAGE_SIZE = 1000. If the first page has 1000 rows and the second has 5,
        the worker should make exactly 2 pagination calls and then stop.
        """
        from api.workers.aggregation import aggregate_org, _PAGE_SIZE

        full_page = [_event_row(f"model-{i}", "1.00") for i in range(_PAGE_SIZE)]
        partial_page = [_event_row(f"extra-{i}", "0.50") for i in range(5)]

        db = _mock_db()
        setup_responses = [
            MagicMock(data=[{"id": "int-aaa"}]),  # integrations
            MagicMock(data=[]),                    # delete summaries
        ]
        pagination_pages = [full_page, partial_page]
        page_call_count = [0]

        def execute_side():
            if setup_responses:
                return setup_responses.pop(0)
            page_call_count[0] += 1
            if page_call_count[0] <= len(pagination_pages):
                return MagicMock(data=pagination_pages[page_call_count[0] - 1])
            return MagicMock(data=[])

        db.execute.side_effect = execute_side

        upserted_rows: list[dict] = []

        def capture_upsert(rows, on_conflict=None):
            upserted_rows.extend(rows)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.upsert.side_effect = capture_upsert

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            aggregate_org(ORG_ID)

        # Pagination should have stopped after the partial page
        assert page_call_count[0] == 2, (
            f"Expected exactly 2 pagination calls, got {page_call_count[0]}"
        )
        # All rows from both pages should be aggregated
        total_models = len(set(r["model"] for r in upserted_rows))
        assert total_models == _PAGE_SIZE + 5, (
            f"Expected {_PAGE_SIZE + 5} distinct models in summaries, got {total_models}"
        )


# ── Gap-04: NULL vs empty-string tag coalescing ────────────────────────────────

class TestAggregationTagCoalescing:
    """Gap-04 (medium): NULL and '' feature_tag must be merged into the same summary group."""

    def test_null_and_empty_string_tags_coalesce_to_single_row(self) -> None:
        """
        aggregate_org normalizes feature_tag with `row.get("feature_tag") or ""`.
        Two events — one with feature_tag=None (NULL from DB) and one with
        feature_tag="" — must produce ONE summary row, not two.
        """
        from api.workers.aggregation import aggregate_org

        today = datetime.now(timezone.utc).date()
        bucket_ts = (today - timedelta(days=1)).isoformat() + "T00:00:00+00:00"

        events = [
            {**_event_row("gpt-4o", "5.00"), "feature_tag": None},  # NULL
            {**_event_row("gpt-4o", "3.00"), "feature_tag": ""},    # empty string
        ]

        db = _mock_db()
        upserted_rows: list[dict] = []
        responses = [
            MagicMock(data=[{"id": "int-aaa"}]),
            MagicMock(data=[]),
            MagicMock(data=events),
            MagicMock(data=[]),
        ]

        def execute_side():
            return responses.pop(0) if responses else MagicMock(data=[])

        db.execute.side_effect = execute_side

        def capture_upsert(rows, on_conflict=None):
            upserted_rows.extend(rows)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.upsert.side_effect = capture_upsert

        with patch("api.workers.aggregation._get_supabase", return_value=db):
            aggregate_org(ORG_ID)

        assert len(upserted_rows) == 1, (
            f"Expected NULL and '' feature_tag to coalesce into 1 summary row, "
            f"got {len(upserted_rows)}. "
            "Both should map to '' via the `or ''` coercion in aggregate_org."
        )
        assert Decimal(upserted_rows[0]["total_cost_usd"]) == Decimal("8.00"), (
            f"Expected merged cost of 8.00, got {upserted_rows[0]['total_cost_usd']}"
        )
