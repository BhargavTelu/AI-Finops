"""
Unit tests for Slack daily digest workers (Group C):
  _fetch_digest_data  - collects metrics from daily_cost_summaries + anomalies
  _digest_slack_blocks - builds Slack Block Kit payload
  send_daily_digests  - fan-out task (enqueues per-org)
  send_slack_digest   - per-org digest task with idempotency guard

All external calls (Supabase, Slack postMessage, EncryptionService) are mocked.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from api.workers.notifications import (
    _digest_slack_blocks,
    _fetch_digest_data,
    send_daily_digests,
    send_slack_digest,
)

ORG_ID = "00000000-0000-0000-0000-000000000001"
ORG_ID_2 = "00000000-0000-0000-0000-000000000002"
YESTERDAY = date(2026, 5, 20)


# ── DB mock helpers ─────────────────────────────────────────────────────────────

def _mock_db() -> MagicMock:
    db = MagicMock()
    empty = MagicMock()
    empty.data = []
    db.table.return_value = db
    db.select.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.insert.return_value = db
    db.execute.return_value = empty
    return db


def _slack_row() -> dict:
    return {
        "bot_token_enc": "\\x" + "ab" * 28,
        "channel_id": "C01234567",
    }


def _week_rows() -> list[dict]:
    """Minimal week of data: two days, two models."""
    return [
        {"day": "2026-05-20", "model": "gpt-4o", "total_cost_usd": "20.00"},
        {"day": "2026-05-20", "model": "claude-3-sonnet", "total_cost_usd": "5.00"},
        {"day": "2026-05-19", "model": "gpt-4o", "total_cost_usd": "18.00"},
    ]


def _db_for_digest(slack_row: dict | None = None) -> MagicMock:
    """
    Pre-wired mock for send_slack_digest. Executes in this order:
      1. slack_digests idempotency check  - empty (not yet sent)
      2. slack_integrations fetch         - slack_row (or empty)
      3. daily_cost_summaries week        - _week_rows()
      4. daily_cost_summaries MTD         - 25.00 total
      5. daily_cost_summaries last month  - 20.00 total
      6. anomalies open count             - 2 anomalies
      7. slack_digests insert             - empty (success)
    """
    db = _mock_db()
    db.execute.side_effect = [
        MagicMock(data=[]),                              # 1. idempotency - no prior digest
        MagicMock(data=[slack_row] if slack_row else []),  # 2. slack_integrations
        MagicMock(data=_week_rows()),                    # 3. week data
        MagicMock(data=[{"total_cost_usd": "25.00"}]),  # 4. MTD
        MagicMock(data=[{"total_cost_usd": "20.00"}]),  # 5. last month
        MagicMock(data=[{"id": "a1"}, {"id": "a2"}]),   # 6. open anomalies
        MagicMock(data=[]),                              # 7. insert record
    ]
    return db


# ── _digest_slack_blocks ─────────────────────────────────────────────────────────

class TestDigestSlackBlocks:
    def test_header_contains_date(self) -> None:
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("25"), Decimal("20"), 25, [], 0
        )
        header_text = blocks[0]["text"]["text"]
        assert "May" in header_text
        assert "20" in header_text

    def test_fields_contain_spend_figures(self) -> None:
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("25.50"), Decimal("18.75"), None, [], 3
        )
        fields_text = str(blocks[1]["fields"])
        assert "$25.50" in fields_text
        assert "$18.75" in fields_text
        assert "3" in fields_text

    def test_mom_positive(self) -> None:
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("0"), Decimal("0"), 25, [], 0
        )
        fields_text = str(blocks[1]["fields"])
        assert "+25%" in fields_text

    def test_mom_negative(self) -> None:
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("0"), Decimal("0"), -10, [], 0
        )
        fields_text = str(blocks[1]["fields"])
        assert "-10%" in fields_text

    def test_mom_none_shows_no_prior_data(self) -> None:
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("0"), Decimal("0"), None, [], 0
        )
        fields_text = str(blocks[1]["fields"])
        assert "No prior" in fields_text

    def test_top_drivers_block_appended(self) -> None:
        drivers = [
            {"label": "gpt-4o", "usd": Decimal("20.00")},
            {"label": "claude-3-sonnet", "usd": Decimal("5.00")},
        ]
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("25"), Decimal("18"), 25, drivers, 0
        )
        assert len(blocks) == 3
        driver_text = blocks[2]["text"]["text"]
        assert "gpt-4o" in driver_text
        assert "$20.00" in driver_text

    def test_no_drivers_block_when_empty(self) -> None:
        blocks = _digest_slack_blocks(
            YESTERDAY, Decimal("0"), Decimal("0"), None, [], 0
        )
        assert len(blocks) == 2


# ── _fetch_digest_data ───────────────────────────────────────────────────────────

class TestFetchDigestData:
    def _db_with(
        self,
        week: list[dict],
        mtd_total: str = "0",
        lm_total: str = "0",
        anomaly_count: int = 0,
    ) -> MagicMock:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=week),
            MagicMock(data=[{"total_cost_usd": mtd_total}] if mtd_total != "0" or True else []),
            MagicMock(data=[{"total_cost_usd": lm_total}] if lm_total != "0" or True else []),
            MagicMock(data=[{"id": str(i)} for i in range(anomaly_count)]),
        ]
        return db

    def test_yesterday_total_is_sum_of_yesterday_rows(self) -> None:
        db = self._db_with(
            week=[
                {"day": "2026-05-20", "model": "gpt-4o", "total_cost_usd": "20.00"},
                {"day": "2026-05-20", "model": "claude-3-sonnet", "total_cost_usd": "5.00"},
                {"day": "2026-05-19", "model": "gpt-4o", "total_cost_usd": "18.00"},
            ]
        )
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        assert data["yesterday_usd"] == Decimal("25.00")

    def test_avg_7d_divides_by_7(self) -> None:
        # 3 rows total over 2 days = 43 USD; avg = 43/7
        db = self._db_with(week=_week_rows())
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        expected = Decimal("43.00") / 7
        assert data["avg_7d_usd"] == expected

    def test_top_drivers_sorted_by_spend(self) -> None:
        db = self._db_with(
            week=[
                {"day": "2026-05-20", "model": "cheap-model", "total_cost_usd": "2.00"},
                {"day": "2026-05-20", "model": "gpt-4o", "total_cost_usd": "20.00"},
                {"day": "2026-05-20", "model": "claude-3-sonnet", "total_cost_usd": "5.00"},
            ]
        )
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        labels = [d["label"] for d in data["top_drivers"]]
        assert labels[0] == "gpt-4o"
        assert labels[1] == "claude-3-sonnet"
        assert labels[2] == "cheap-model"

    def test_top_drivers_capped_at_3(self) -> None:
        db = self._db_with(
            week=[
                {"day": "2026-05-20", "model": f"model-{i}", "total_cost_usd": str(i)}
                for i in range(5, 0, -1)
            ]
        )
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        assert len(data["top_drivers"]) == 3

    def test_mom_positive_delta(self) -> None:
        db = self._db_with(week=[], mtd_total="150.00", lm_total="100.00")
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        assert data["mom_pct"] == 50

    def test_mom_negative_delta(self) -> None:
        db = self._db_with(week=[], mtd_total="80.00", lm_total="100.00")
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        assert data["mom_pct"] == -20

    def test_mom_none_when_no_last_month_data(self) -> None:
        db = self._db_with(week=[], mtd_total="100.00", lm_total="0")
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        assert data["mom_pct"] is None

    def test_open_anomaly_count(self) -> None:
        db = self._db_with(week=[], anomaly_count=3)
        data = _fetch_digest_data(db, ORG_ID, YESTERDAY)
        assert data["open_anomaly_count"] == 3


# ── send_daily_digests ──────────────────────────────────────────────────────────

class TestSendDailyDigests:
    def test_dispatches_to_each_connected_org(self) -> None:
        db = _mock_db()
        db.execute.return_value = MagicMock(
            data=[{"org_id": ORG_ID}, {"org_id": ORG_ID_2}]
        )
        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.send_slack_digest") as mock_digest,
        ):
            send_daily_digests()

        assert mock_digest.delay.call_count == 2
        mock_digest.delay.assert_any_call(ORG_ID)
        mock_digest.delay.assert_any_call(ORG_ID_2)

    def test_no_dispatch_when_no_slack_orgs(self) -> None:
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[])
        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.send_slack_digest") as mock_digest,
        ):
            send_daily_digests()

        mock_digest.delay.assert_not_called()


# ── send_slack_digest ───────────────────────────────────────────────────────────

class TestSendSlackDigest:
    def test_posts_digest_when_connected(self) -> None:
        db = _db_for_digest(_slack_row())
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_slack_digest.apply(args=[ORG_ID])

        mock_post.assert_called_once()
        assert mock_post.call_args[0][1] == "C01234567"

    def test_skips_when_no_slack_integration(self) -> None:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[]),   # idempotency check - no prior digest
            MagicMock(data=[]),   # slack_integrations - not connected
        ]
        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_slack_digest.apply(args=[ORG_ID])

        mock_post.assert_not_called()

    def test_skips_when_already_sent_today(self) -> None:
        db = _mock_db()
        db.execute.return_value = MagicMock(
            data=[{"id": "dddddddd-0000-0000-0000-000000000001"}]
        )
        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_slack_digest.apply(args=[ORG_ID])

        mock_post.assert_not_called()

    def test_records_digest_in_slack_digests_table(self) -> None:
        db = _db_for_digest(_slack_row())
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch("api.workers.notifications.post_message"),
        ):
            send_slack_digest.apply(args=[ORG_ID])

        # The 7th execute() call is the insert into slack_digests.
        assert db.insert.called

    def test_slack_failure_retries(self) -> None:
        """post_message failure should cause the task to retry (raise Retry)."""
        # Each attempt needs: 1 (idempotency) + 1 (slack) + 4 (fetch) = 6 executes.
        # max_retries=2 → up to 3 attempts total.
        one_attempt = [
            MagicMock(data=[]),                              # idempotency check
            MagicMock(data=[_slack_row()]),                  # slack_integrations
            MagicMock(data=_week_rows()),                    # week data
            MagicMock(data=[{"total_cost_usd": "25.00"}]),  # MTD
            MagicMock(data=[{"total_cost_usd": "20.00"}]),  # last month
            MagicMock(data=[]),                              # open anomalies
        ]
        db = _mock_db()
        db.execute.side_effect = one_attempt * 3  # enough for all retry attempts
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch(
                "api.workers.notifications.post_message",
                side_effect=ValueError("token_revoked"),
            ),
        ):
            result = send_slack_digest.apply(args=[ORG_ID])

        # After max_retries=2, Celery eager mode captures the exception without raising.
        assert result.failed()


# ── TC-FAN-05: send_daily_digests fan-out ──────────────────────────────────────

class TestSendDailyDigestsFanOut:
    """TC-FAN-05 - send_daily_digests enqueues send_slack_digest once per connected org."""

    def test_dispatches_once_per_slack_connected_org(self) -> None:
        """
        Mock DB to return 2 Slack-connected orgs.
        send_daily_digests() must call send_slack_digest.delay() exactly twice.
        """
        rows = [
            {"org_id": ORG_ID},
            {"org_id": ORG_ID_2},
        ]
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.execute.return_value = MagicMock(data=rows)

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.send_slack_digest") as mock_task,
        ):
            mock_task.delay = MagicMock()
            send_daily_digests()

        assert mock_task.delay.call_count == 2, (
            f"Expected send_slack_digest.delay called 2 times (once per org), "
            f"got {mock_task.delay.call_count}"
        )
        called_org_ids = {call.args[0] for call in mock_task.delay.call_args_list}
        assert called_org_ids == {ORG_ID, ORG_ID_2}

    def test_no_slack_orgs_does_not_dispatch(self) -> None:
        """No Slack-connected orgs → send_slack_digest.delay never called."""
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.execute.return_value = MagicMock(data=[])

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.send_slack_digest") as mock_task,
        ):
            mock_task.delay = MagicMock()
            send_daily_digests()

        mock_task.delay.assert_not_called()
