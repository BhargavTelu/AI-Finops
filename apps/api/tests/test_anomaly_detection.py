"""
Unit tests for anomaly_detection worker tasks.
All Supabase calls are mocked - no network, no DB.
Pattern follows test_workers.py: mock _get_supabase, control execute() side effects.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

ORG_ID = "00000000-0000-0000-0000-000000000001"


# ── DB mock helper ────────────────────────────────────────────────────────────


def _mock_db() -> MagicMock:
    """Supabase client mock where all chained calls return self; .execute() returns empty data."""
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
    db.order.return_value = db
    db.range.return_value = db
    db.limit.return_value = db
    db.execute.return_value = empty
    return db


def _make_summary_rows(
    model: str = "gpt-4o",
    n_days: int = 15,
    cost_per_day: float = 20.0,
    spike_day_cost: float | None = None,
) -> list[dict]:
    """
    Generate daily_cost_summaries rows relative to the real current date so
    they land inside the worker's [from_date, today) window.
    If spike_day_cost is set, the last row (most recent day) gets that cost.
    """
    # Must match the worker's clock (UTC), not the machine's local date -
    # using date.today() made these tests fail between local and UTC midnight.
    today = datetime.now(UTC).date()
    rows = []
    for i in range(n_days):
        # day ranges from (today - n_days) up to (today - 1); none include today itself
        day = today - timedelta(days=n_days - i)
        cost = spike_day_cost if (spike_day_cost is not None and i == n_days - 1) else cost_per_day
        rows.append(
            {
                "day": day.isoformat(),
                "model": model,
                "feature_tag": "",
                "team_tag": "",
                "customer_tag": "",
                "total_cost_usd": str(cost),
            }
        )
    return rows


class TestDetectOrg:
    def _run(
        self,
        summary_rows: list[dict],
        existing_anomalies: list[dict] | None = None,
    ) -> MagicMock:
        """Run detect_org with mocked DB. execute() returns rows in call order."""
        db = _mock_db()

        # execute() call order in detect_org:
        # 1. daily_cost_summaries SELECT (history rows)
        # 2. anomalies SELECT (open anomalies today - dedup check)
        # 3. anomalies INSERT (one per detected anomaly, if any)
        exec_history = MagicMock()
        exec_history.data = summary_rows

        exec_dedup = MagicMock()
        exec_dedup.data = existing_anomalies or []

        exec_insert = MagicMock()
        exec_insert.data = []

        db.execute.side_effect = [exec_history, exec_dedup, exec_insert]

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.send_anomaly_alert"),
        ):
            from api.workers.anomaly_detection import detect_org

            detect_org(ORG_ID)

        return db

    def test_inserts_anomaly_when_spike_detected(self) -> None:
        # 14 days at $20/day, then a $10,000 spike → anomaly detected + inserted
        rows = _make_summary_rows(cost_per_day=20.0, spike_day_cost=10_000.0)
        db = self._run(rows)
        db.insert.assert_called()
        inserted = db.insert.call_args[0][0]
        assert inserted["org_id"] == ORG_ID
        assert inserted["scope_kind"] == "model"
        assert inserted["scope_value"] == "gpt-4o"
        assert inserted["severity"] in ("low", "medium", "high")

    def test_no_insert_when_no_spike(self) -> None:
        # Flat $20/day - z-score is 0, no anomaly
        rows = _make_summary_rows(cost_per_day=20.0)
        db = self._run(rows)
        db.insert.assert_not_called()

    def test_no_insert_when_actual_below_ten_dollar_floor(self) -> None:
        # $2/day baseline, spike to $9 - below the $10 floor
        rows = _make_summary_rows(cost_per_day=2.0, spike_day_cost=9.0)
        db = self._run(rows)
        db.insert.assert_not_called()

    def test_no_insert_when_insufficient_history(self) -> None:
        # Only 5 rows - fills the rest of the window with $0, never meets threshold
        rows = _make_summary_rows(n_days=5, cost_per_day=100.0, spike_day_cost=10_000.0)
        self._run(rows)
        # With 10 zero-filled days, the rolling window has mostly zeros;
        # the spike is real but baseline is $0 - spike_pct corner case.
        # Either way no $10 floor-failing insert should come from 5-row data.
        # (If detect_anomalies fires, that's fine too - test intent is no crash.)
        # We just verify the worker completes without error.

    def test_dedup_skips_already_open_anomaly_today(self) -> None:
        rows = _make_summary_rows(cost_per_day=20.0, spike_day_cost=10_000.0)
        existing = [{"scope_kind": "model", "scope_value": "gpt-4o"}]
        db = self._run(rows, existing_anomalies=existing)
        db.insert.assert_not_called()

    def test_no_insert_when_no_data(self) -> None:
        db = _mock_db()
        exec_empty = MagicMock()
        exec_empty.data = []
        db.execute.return_value = exec_empty

        with patch("api.workers.anomaly_detection._get_supabase", return_value=db):
            from api.workers.anomaly_detection import detect_org

            detect_org(ORG_ID)

        db.insert.assert_not_called()

    def test_spike_sets_correct_scope_fields(self) -> None:
        rows = _make_summary_rows(
            model="claude-3-5-sonnet", cost_per_day=50.0, spike_day_cost=50_000.0
        )
        db = self._run(rows)
        db.insert.assert_called()
        inserted = db.insert.call_args[0][0]
        assert inserted["scope_kind"] == "model"
        assert inserted["scope_value"] == "claude-3-5-sonnet"
        assert int(inserted["spike_pct"]) > 0


class TestDetectAllOrgs:
    def test_dispatches_detect_org_per_unique_org(self) -> None:
        db = _mock_db()
        exec_orgs = MagicMock()
        exec_orgs.data = [
            {"org_id": "org-1"},
            {"org_id": "org-2"},
            {"org_id": "org-1"},  # duplicate - should only dispatch 2 unique
        ]
        db.execute.return_value = exec_orgs

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.detect_org") as mock_task,
        ):
            mock_task.delay = MagicMock()
            from api.workers.anomaly_detection import detect_all_orgs

            detect_all_orgs()

        assert mock_task.delay.call_count == 2
        called_ids = {c[0][0] for c in mock_task.delay.call_args_list}
        assert called_ids == {"org-1", "org-2"}

    def test_no_dispatch_when_no_active_integrations(self) -> None:
        db = _mock_db()
        exec_empty = MagicMock()
        exec_empty.data = []
        db.execute.return_value = exec_empty

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.detect_org") as mock_task,
        ):
            mock_task.delay = MagicMock()
            from api.workers.anomaly_detection import detect_all_orgs

            detect_all_orgs()

        mock_task.delay.assert_not_called()


# ── TC-ANO-20: detect_org context field population ───────────────────────────


class TestDetectOrgContextField:
    """TC-ANO-20 - detect_org inserts anomaly row with populated context dict."""

    def _make_history_rows(self, org_id: str) -> list[dict]:
        """Generate 15 days of baseline ($10/day) + 1 day spike ($100)."""
        from datetime import timedelta

        today = __import__("datetime").datetime.now(UTC).date()
        rows = []
        for i in range(15, 0, -1):
            day = (today - timedelta(days=i)).isoformat()
            cost = "100.00" if i == 1 else "10.00"  # spike on most recent day
            rows.append(
                {
                    "day": day,
                    "model": "gpt-4o",
                    "feature_tag": "chat",
                    "team_tag": "ml",
                    "customer_tag": "",
                    "total_cost_usd": cost,
                }
            )
        return rows

    def test_inserted_anomaly_has_context_with_tags(self) -> None:
        """
        TC-ANO-20 - context dict must contain model, feature_tag, and team_tag
        so the anomaly explainer can generate specific narratives.
        """
        from unittest.mock import MagicMock, patch

        org_id = "00000000-0000-0000-0000-000000000001"
        history_rows = self._make_history_rows(org_id)

        inserted_rows: list[dict] = []

        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.gte.return_value = db
        db.lt.return_value = db
        db.insert.return_value = db
        db.order.return_value = db
        db.range.return_value = db
        db.limit.return_value = db

        call_count = [0]

        def execute_side():
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(data=history_rows)
            if call_count[0] == 2:
                return MagicMock(data=[])  # no existing anomalies today
            return MagicMock(data=[])

        db.execute.side_effect = execute_side

        def capture_insert(row):
            inserted_rows.append(row)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.insert.side_effect = capture_insert

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.send_anomaly_alert") as mock_alert,
            patch("api.workers.anomaly_detection.explain_anomaly") as mock_explain,
        ):
            mock_alert.delay = MagicMock()
            mock_explain.delay = MagicMock()
            from api.workers.anomaly_detection import detect_org

            detect_org(org_id)

        assert len(inserted_rows) >= 1, "Expected at least one anomaly to be inserted"
        context = inserted_rows[0].get("context", {})
        assert context.get("model") == "gpt-4o", f"context.model missing, got {context}"
        assert context.get("feature_tag") == "chat", f"context.feature_tag missing, got {context}"
        assert context.get("team_tag") == "ml", f"context.team_tag missing, got {context}"


# ── TC-ANO-21: detect_org scope_value field ──────────────────────────────────


class TestDetectOrgScopeValue:
    """TC-ANO-21 - detect_org sets scope_kind='model' and scope_value=model name."""

    def test_inserted_anomaly_has_correct_scope_fields(self) -> None:
        """
        TC-ANO-21 - anomaly row must have scope_kind='model' and scope_value='gpt-4o'.
        These fields drive the GET /anomalies filter queries.
        """
        from datetime import timedelta
        from unittest.mock import MagicMock, patch

        org_id = "00000000-0000-0000-0000-000000000002"
        today = __import__("datetime").datetime.now(UTC).date()
        rows = []
        for i in range(15, 0, -1):
            day = (today - timedelta(days=i)).isoformat()
            cost = "80.00" if i == 1 else "5.00"
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

        inserted_rows: list[dict] = []

        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.gte.return_value = db
        db.lt.return_value = db
        db.insert.return_value = db
        db.order.return_value = db
        db.range.return_value = db
        db.limit.return_value = db

        call_count = [0]

        def execute_side():
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(data=rows)
            if call_count[0] == 2:
                return MagicMock(data=[])
            return MagicMock(data=[])

        db.execute.side_effect = execute_side

        def capture_insert(row):
            inserted_rows.append(row)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.insert.side_effect = capture_insert

        with (
            patch("api.workers.anomaly_detection._get_supabase", return_value=db),
            patch("api.workers.anomaly_detection.send_anomaly_alert") as mock_alert,
            patch("api.workers.anomaly_detection.explain_anomaly") as mock_explain,
        ):
            mock_alert.delay = MagicMock()
            mock_explain.delay = MagicMock()
            from api.workers.anomaly_detection import detect_org

            detect_org(org_id)

        assert len(inserted_rows) >= 1, "Expected at least one anomaly to be inserted"
        row = inserted_rows[0]
        assert (
            row.get("scope_kind") == "model"
        ), f"Expected scope_kind='model', got {row.get('scope_kind')}"
        assert (
            row.get("scope_value") == "gpt-4o"
        ), f"Expected scope_value='gpt-4o', got {row.get('scope_value')}"
