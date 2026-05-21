"""
Tests for severity-based Slack alert triggering in anomaly_detection worker.
TC-DET-10: low severity → send_anomaly_alert NOT called.
TC-DET-11: medium severity → send_anomaly_alert IS called.
TC-DET-12: high severity → send_anomaly_alert IS called.
"""

from datetime import date, timedelta
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
    db.limit.return_value = db
    db.execute.return_value = empty
    return db


def _summary_rows(spike_cost: float, n_days: int = 15) -> list[dict]:
    """
    Build daily_cost_summaries rows with a flat $100/day baseline and a spike
    on the last day. The worker fills any gap with $0, so we provide all n_days.
    """
    today = date.today()
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


class TestSeverityAlerts:
    def test_low_severity_no_slack_alert(self) -> None:  # TC-DET-10
        """
        z ≈ 2.5 (low severity) → send_anomaly_alert.delay must NOT be called.
        Flat $100 baseline, stdev ≈ 0 → stdev clipped to 0.01.
        actual = 100 + 0.01*2.5 = 100.025 → z = 2.5 → low.
        """
        mock_alert = _run_detect_org(100.025)
        mock_alert.delay.assert_not_called()

    def test_medium_severity_triggers_slack_alert(self) -> None:  # TC-DET-11
        """
        z ≈ 3.5 (medium severity) → send_anomaly_alert.delay IS called.
        actual = 100 + 0.01*3.5 = 100.035 → z = 3.5 → medium.
        """
        mock_alert = _run_detect_org(100.035)
        mock_alert.delay.assert_called_once()

    def test_high_severity_triggers_slack_alert(self) -> None:  # TC-DET-12
        """
        Huge spike → z >> 4 (high severity) → send_anomaly_alert.delay IS called.
        """
        mock_alert = _run_detect_org(100_000.0)
        mock_alert.delay.assert_called_once()
