"""
Tests for severity-based Slack alert triggering in anomaly_detection worker.
TC-DET-10: low severity → send_anomaly_alert NOT called.
TC-DET-11: medium severity → send_anomaly_alert IS called.
TC-DET-12: high severity → send_anomaly_alert IS called.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

ORG_ID = "00000000-0000-0000-0000-000000000001"


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
    db.order.return_value = db
    db.range.return_value = db
    db.limit.return_value = db
    db.execute.return_value = empty
    return db


def _summary_rows(spike_cost: float, n_days: int = 15) -> list[dict]:
    """
    Build daily_cost_summaries rows with a flat $100/day baseline and a spike
    on the last day. The worker fills any gap with $0, so we provide all n_days.
    """
    # Must match the worker's clock (UTC), not the machine's local date -
    # using date.today() made these tests fail between local and UTC midnight.
    today = datetime.now(UTC).date()
    rows = []
    for i in range(n_days):
        day = today - timedelta(days=n_days - i)
        cost = spike_cost if i == n_days - 1 else 100.0
        rows.append(
            {
                "day": day.isoformat(),
                "model": "gpt-4o",
                "feature_tag": "",
                "team_tag": "",
                "customer_tag": "",
                "total_cost_usd": str(cost),
            }
        )
    return rows


def _run_detect_org(spike_cost: float) -> MagicMock:
    """
    Run detect_org with the given spike cost and return the patched
    send_anomaly_alert mock so callers can assert on .delay().
    """
    db = _mock_db()
    rows = _summary_rows(spike_cost)

    exec_history = MagicMock()
    exec_history.data = rows
    exec_dedup = MagicMock()
    exec_dedup.data = []
    exec_insert = MagicMock()
    exec_insert.data = []

    db.execute.side_effect = [exec_history, exec_dedup, exec_insert]

    mock_alert = MagicMock()
    mock_alert.delay = MagicMock()

    with (
        patch("api.workers.anomaly_detection._get_supabase", return_value=db),
        patch("api.workers.anomaly_detection.send_anomaly_alert", mock_alert),
    ):
        from api.workers.anomaly_detection import detect_org

        detect_org(ORG_ID)

    return mock_alert


def _run_detect_org_with_explain(spike_cost: float) -> tuple[MagicMock, MagicMock]:
    """
    Run detect_org with both send_anomaly_alert and explain_anomaly patched.
    Returns (mock_send_anomaly_alert, mock_explain_anomaly).
    """
    db = _mock_db()
    rows = _summary_rows(spike_cost)

    exec_history = MagicMock()
    exec_history.data = rows
    exec_dedup = MagicMock()
    exec_dedup.data = []
    exec_insert = MagicMock()
    exec_insert.data = []

    db.execute.side_effect = [exec_history, exec_dedup, exec_insert]

    mock_alert = MagicMock()
    mock_alert.delay = MagicMock()
    mock_explain = MagicMock()
    mock_explain.delay = MagicMock()

    with (
        patch("api.workers.anomaly_detection._get_supabase", return_value=db),
        patch("api.workers.anomaly_detection.send_anomaly_alert", mock_alert),
        patch("api.workers.anomaly_detection.explain_anomaly", mock_explain),
    ):
        from api.workers.anomaly_detection import detect_org

        detect_org(ORG_ID)

    return mock_alert, mock_explain


class TestExplainAnomalyDispatch:
    """
    TC-M3-D01, D02, D03: explain_anomaly.delay dispatched for medium/high severity;
    NOT dispatched for low severity. Uses the same spike-cost thresholds as
    TestSeverityAlerts to keep the z-score semantics consistent.
    """

    def test_explain_dispatched_for_medium_severity(self) -> None:  # TC-M3-D01
        _, mock_explain = _run_detect_org_with_explain(117.5)
        mock_explain.delay.assert_called_once()

    def test_explain_dispatched_for_high_severity(self) -> None:  # TC-M3-D02
        _, mock_explain = _run_detect_org_with_explain(100_000.0)
        mock_explain.delay.assert_called_once()

    def test_explain_not_dispatched_for_low_severity(self) -> None:  # TC-M3-D03
        _, mock_explain = _run_detect_org_with_explain(112.5)
        mock_explain.delay.assert_not_called()


class TestSeverityAlerts:
    def test_low_severity_no_slack_alert(self) -> None:  # TC-DET-10
        """
        z ≈ 2.5 (low severity) → send_anomaly_alert.delay must NOT be called.
        Flat $100 baseline → pstdev=0, floored to mean*5% = $5.
        actual = 100 + 5*2.5 = 112.5 → z = 2.5 → low.
        """
        mock_alert = _run_detect_org(112.5)
        mock_alert.delay.assert_not_called()

    def test_medium_severity_triggers_slack_alert(self) -> None:  # TC-DET-11
        """
        z ≈ 3.5 (medium severity) → send_anomaly_alert.delay IS called.
        actual = 100 + 5*3.5 = 117.5 → z = 3.5 → medium.
        """
        mock_alert = _run_detect_org(117.5)
        mock_alert.delay.assert_called_once()

    def test_high_severity_triggers_slack_alert(self) -> None:  # TC-DET-12
        """
        Huge spike → z >> 4 (high severity) → send_anomaly_alert.delay IS called.
        """
        mock_alert = _run_detect_org(100_000.0)
        mock_alert.delay.assert_called_once()
