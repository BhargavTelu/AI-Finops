"""
Unit tests for Slack notification workers (Group C):
  send_anomaly_alert  — real-time alert when anomaly is detected
  send_budget_alert   — Slack branch of the budget alert task

All external calls (Supabase, Slack postMessage, EncryptionService) are mocked.
"""

from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from api.workers.notifications import (
    _anomaly_slack_blocks,
    _budget_slack_blocks,
    _get_slack_channel,
    send_anomaly_alert,
    send_budget_alert,
)

ORG_ID = "00000000-0000-0000-0000-000000000001"
ANOMALY_ID = "aaaaaaaa-0000-0000-0000-000000000001"
BUDGET_ID = "bbbbbbbb-0000-0000-0000-000000000001"


# ── DB mock helpers ─────────────────────────────────────────────────────────────

def _mock_db() -> MagicMock:
    db = MagicMock()
    empty = MagicMock()
    empty.data = []
    db.table.return_value = db
    db.select.return_value = db
    db.eq.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = empty
    return db


def _anomaly_row(severity: str = "medium", spike_pct: int = 200) -> dict:
    return {
        "id": ANOMALY_ID,
        "org_id": ORG_ID,
        "scope_kind": "model",
        "scope_value": "gpt-4o",
        "baseline_usd": "12.40",
        "actual_usd": "37.20",
        "spike_pct": spike_pct,
        "severity": severity,
        "context": {"model": "gpt-4o", "team_tag": "backend", "feature_tag": None, "customer_tag": None},
    }


def _budget_row() -> dict:
    return {
        "id": BUDGET_ID,
        "org_id": ORG_ID,
        "scope_type": "model",
        "scope_value": "gpt-4o",
        "monthly_limit": "500.00",
        "alert_at_pct": 80,
    }


def _slack_row(alerts_muted: bool = False) -> dict:
    return {
        "bot_token_enc": "\\x" + "ab" * 28,
        "channel_id": "C01234567",
        "alerts_muted": alerts_muted,
    }


# ── _anomaly_slack_blocks ───────────────────────────────────────────────────────

class TestAnomalySlackBlocks:
    def test_includes_model_and_severity(self) -> None:
        anomaly = _anomaly_row(severity="high", spike_pct=340)
        blocks = _anomaly_slack_blocks(anomaly)
        text = blocks[0]["text"]["text"]
        assert "gpt-4o" in text
        assert ":rotating_light:" in text

    def test_spike_and_values_in_fields(self) -> None:
        anomaly = _anomaly_row(spike_pct=200)
        blocks = _anomaly_slack_blocks(anomaly)
        fields_text = str(blocks[1]["fields"])
        assert "200%" in fields_text
        assert "$12.40" in fields_text
        assert "$37.20" in fields_text

    def test_tag_context_block_appears_when_team_set(self) -> None:
        anomaly = _anomaly_row()
        blocks = _anomaly_slack_blocks(anomaly)
        assert len(blocks) == 3  # section + fields + context
        context_text = blocks[2]["elements"][0]["text"]
        assert "backend" in context_text

    def test_no_context_block_when_no_tags(self) -> None:
        anomaly = _anomaly_row()
        anomaly["context"] = {"model": "gpt-4o", "team_tag": None, "feature_tag": None, "customer_tag": None}
        blocks = _anomaly_slack_blocks(anomaly)
        assert len(blocks) == 2  # no context block

    def test_low_severity_uses_warning_emoji(self) -> None:
        anomaly = _anomaly_row(severity="low")
        blocks = _anomaly_slack_blocks(anomaly)
        assert ":warning:" in blocks[0]["text"]["text"]

    def test_medium_severity_uses_orange_emoji(self) -> None:
        anomaly = _anomaly_row(severity="medium")
        blocks = _anomaly_slack_blocks(anomaly)
        assert ":large_orange_diamond:" in blocks[0]["text"]["text"]


# ── _budget_slack_blocks ────────────────────────────────────────────────────────

class TestBudgetSlackBlocks:
    def test_warning_header(self) -> None:
        blocks = _budget_slack_blocks("model: gpt-4o", Decimal("500"), Decimal("420"), 84, False)
        header = blocks[0]["text"]["text"]
        assert ":warning:" in header
        assert "84%" in header

    def test_exceeded_header(self) -> None:
        blocks = _budget_slack_blocks("global", Decimal("1000"), Decimal("1100"), 110, True)
        header = blocks[0]["text"]["text"]
        assert ":red_circle:" in header
        assert "110%" in header

    def test_fields_contain_scope_and_amounts(self) -> None:
        blocks = _budget_slack_blocks("model: gpt-4o", Decimal("500"), Decimal("420"), 84, False)
        fields_text = str(blocks[1]["fields"])
        assert "gpt-4o" in fields_text
        assert "$500.00" in fields_text
        assert "$420.00" in fields_text
        assert "84%" in fields_text


# ── _get_slack_channel ──────────────────────────────────────────────────────────

class TestGetSlackChannel:
    def test_returns_none_when_not_connected(self) -> None:
        db = _mock_db()
        result = _get_slack_channel(db, ORG_ID)
        assert result is None

    def test_returns_token_and_channel_when_connected(self) -> None:
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_slack_row()])
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-real-token"
        with patch("api.workers.notifications.EncryptionService", return_value=mock_cipher):
            result = _get_slack_channel(db, ORG_ID)
        assert result is not None
        token, channel_id, alerts_muted = result
        assert token == "xoxb-real-token"
        assert channel_id == "C01234567"
        assert alerts_muted is False

    def test_returns_none_on_decrypt_failure(self) -> None:
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_slack_row()])
        with patch("api.workers.notifications.EncryptionService", side_effect=ValueError("bad key")):
            result = _get_slack_channel(db, ORG_ID)
        assert result is None

    def test_returns_alerts_muted_true_when_row_is_muted(self) -> None:  # TC-M3-C04
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_slack_row(alerts_muted=True)])
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-real-token"
        with patch("api.workers.notifications.EncryptionService", return_value=mock_cipher):
            result = _get_slack_channel(db, ORG_ID)
        assert result is not None
        _, _, alerts_muted = result
        assert alerts_muted is True


# ── send_anomaly_alert ──────────────────────────────────────────────────────────

class TestSendAnomalyAlert:
    def test_posts_to_slack_when_connected(self) -> None:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_anomaly_row()]),   # anomaly fetch
            MagicMock(data=[_slack_row()]),      # slack integration fetch
            MagicMock(data=[]),                  # notified_at update
        ]
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_anomaly_alert(ANOMALY_ID)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][1] == "C01234567"  # channel_id

    def test_skips_when_anomaly_not_found(self) -> None:
        db = _mock_db()  # returns empty by default
        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_anomaly_alert(ANOMALY_ID)

        mock_post.assert_not_called()

    def test_skips_when_no_slack_integration(self) -> None:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_anomaly_row()]),  # anomaly found
            MagicMock(data=[]),                # no slack
        ]
        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_anomaly_alert(ANOMALY_ID)

        mock_post.assert_not_called()

    def test_post_message_called_with_correct_channel(self) -> None:
        """post_message receives the channel_id from the Slack integration row."""
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_anomaly_row()]),
            MagicMock(data=[_slack_row()]),
            MagicMock(data=[]),  # notified_at update
        ]
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_anomaly_alert(ANOMALY_ID)  # direct call — no Celery context needed

        # Verify channel_id from _slack_row() was passed as the second positional arg.
        assert mock_post.call_args[0][1] == "C01234567"


# ── send_budget_alert — Slack branch ───────────────────────────────────────────

class TestSendBudgetAlertSlack:
    """Tests for the Slack branch added in Group C.
    We mock the email send so it's a no-op and focus on whether Slack gets called.

    _compute_scope_spend is a local import inside the task body; it lives in
    budget_checks so we patch it there, not in notifications.
    """

    _SCOPE_SPEND_PATCH = "api.workers.budget_checks._compute_scope_spend"

    def _db_for_budget(self, slack_row: dict | None) -> MagicMock:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_budget_row()]),                          # budget fetch
            MagicMock(data=[{"user_id": "u1"}]),                      # admin member
            MagicMock(data=[{"email": "admin@example.com"}]),         # admin email
            MagicMock(data=[slack_row] if slack_row else []),         # slack fetch
        ]
        return db

    def test_posts_to_slack_when_connected(self) -> None:
        db = self._db_for_budget(_slack_row())
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch(self._SCOPE_SPEND_PATCH, return_value=Decimal("420")),
            patch("api.workers.notifications.resend"),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_budget_alert.apply(args=[BUDGET_ID, 84, ORG_ID])

        mock_post.assert_called_once()

    def test_skips_slack_when_not_connected(self) -> None:
        db = self._db_for_budget(None)
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch(self._SCOPE_SPEND_PATCH, return_value=Decimal("420")),
            patch("api.workers.notifications.resend"),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_budget_alert.apply(args=[BUDGET_ID, 84, ORG_ID])

        mock_post.assert_not_called()

    def test_slack_failure_does_not_raise(self) -> None:
        """Slack failure after a successful email must not retry the whole task."""
        db = self._db_for_budget(_slack_row())
        mock_cipher = MagicMock()
        mock_cipher.decrypt.return_value = b"xoxb-test"

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.EncryptionService", return_value=mock_cipher),
            patch(self._SCOPE_SPEND_PATCH, return_value=Decimal("420")),
            patch("api.workers.notifications.resend"),
            patch("api.workers.notifications.post_message", side_effect=ValueError("token_revoked")),
        ):
            # apply() must complete without raising — Slack failure is best-effort.
            send_budget_alert.apply(args=[BUDGET_ID, 84, ORG_ID])


# ── TC-M3-C05: daily digest not suppressed when alerts are muted ────────────────


class TestDigestNotSuppressedWhenMuted:
    """
    TC-M3-C05: send_slack_digest must post even when alerts_muted=True.

    The implementation explicitly discards the third tuple element:
        bot_token, channel_id, _ = slack  # digest is not an alert — never suppressed
    This test confirms that discard is honoured.
    """

    def test_digest_posts_when_alerts_muted(self) -> None:
        from api.workers.notifications import send_slack_digest

        db = _mock_db()
        # First DB call: already-sent-today check → not sent
        db.execute.return_value = MagicMock(data=[])

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            # Return a muted tuple — third element True
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-token", "C01234567", True),
            ),
            patch(
                "api.workers.notifications._fetch_digest_data",
                return_value={
                    "yesterday_usd": Decimal("50.00"),
                    "avg_7d_usd": Decimal("45.00"),
                    "mom_pct": 10.0,
                    "top_drivers": [],
                    "open_anomaly_count": 0,
                },
            ),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_slack_digest.apply(args=[ORG_ID])

        # Digest must still be posted despite alerts_muted=True
        mock_post.assert_called_once()
