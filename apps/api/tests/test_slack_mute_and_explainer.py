"""
Unit tests for:
  - Slack mute alerts (Feature C): PATCH /slack/settings endpoint,
    worker guard in send_anomaly_alert and send_budget_alert.
  - Anomaly explainer (Feature D): rate-limit, service, Celery task.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


ORG_ID = "00000000-0000-0000-0000-000000000001"


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_db() -> MagicMock:
    db = MagicMock()
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.upsert.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = MagicMock(data=[])
    return db


def _slack_row(alerts_muted: bool = False) -> dict:
    return {
        "bot_token_enc": "\\x" + "ab" * 28,
        "channel_id": "C01234567",
        "alerts_muted": alerts_muted,
        "workspace_id": "T0001",
        "channel_name": "#alerts",
        "created_at": "2026-01-01T00:00:00Z",
    }


def _anomaly_row(severity: str = "high") -> dict:
    return {
        "id": "anom-1",
        "org_id": ORG_ID,
        "scope_kind": "model",
        "scope_value": "gpt-4o",
        "baseline_usd": "20.00",
        "actual_usd": "500.00",
        "spike_pct": 2400,
        "severity": severity,
        "context": {"feature_tag": "chat"},
        "explanation_generated_at": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature C - Slack mute alerts
# ══════════════════════════════════════════════════════════════════════════════


class TestSlackSettingsEndpoint:
    """PATCH /slack/settings"""

    def test_updates_alerts_muted_true(self) -> None:
        from api.routers.slack import slack_settings
        from api.schemas.slack import SlackSettingsUpdate

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_slack_row()])

        with patch("api.routers.slack._get_supabase", return_value=db):
            from api.deps import OrgContext
            org = OrgContext(org_id=ORG_ID, user_id="user-1")
            import asyncio
            result = asyncio.run(slack_settings(SlackSettingsUpdate(alerts_muted=True), org))

        assert result.connected is True
        assert result.alerts_muted is True
        db.update.assert_called()

    def test_updates_alerts_muted_false(self) -> None:  # TC-M3-C03
        """Unmuting (alerts_muted=False) persists the flag and returns correct state."""
        from api.routers.slack import slack_settings
        from api.schemas.slack import SlackSettingsUpdate

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_slack_row(alerts_muted=True)])

        with patch("api.routers.slack._get_supabase", return_value=db):
            from api.deps import OrgContext
            org = OrgContext(org_id=ORG_ID, user_id="user-1")
            import asyncio
            result = asyncio.run(slack_settings(SlackSettingsUpdate(alerts_muted=False), org))

        assert result.connected is True
        assert result.alerts_muted is False
        db.update.assert_called()
        update_payload = db.update.call_args[0][0]
        assert update_payload["alerts_muted"] is False

    def test_returns_404_when_not_connected(self) -> None:
        from fastapi import HTTPException
        from api.routers.slack import slack_settings
        from api.schemas.slack import SlackSettingsUpdate

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[])

        with patch("api.routers.slack._get_supabase", return_value=db):
            from api.deps import OrgContext
            org = OrgContext(org_id=ORG_ID, user_id="user-1")
            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(slack_settings(SlackSettingsUpdate(alerts_muted=False), org))

        assert exc_info.value.status_code == 404


class TestAlertsMutedWorkerGuard:
    """send_anomaly_alert and send_budget_alert skip Slack when muted."""

    def test_anomaly_alert_skipped_when_muted(self) -> None:
        from api.workers.notifications import send_anomaly_alert

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_anomaly_row()])

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-token", "C1", True),  # muted=True
            ),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_anomaly_alert.apply(args=["anom-1"])

        mock_post.assert_not_called()

    def test_anomaly_alert_sent_when_not_muted(self) -> None:
        from api.workers.notifications import send_anomaly_alert

        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_anomaly_row()]),
            MagicMock(data=[]),  # notified_at update
        ]

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-token", "C1", False),  # not muted
            ),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_anomaly_alert.apply(args=["anom-1"])

        mock_post.assert_called_once()

    def test_budget_slack_skipped_when_muted(self) -> None:
        from api.workers.notifications import send_budget_alert

        budget_row = {
            "id": "budget-1",
            "org_id": ORG_ID,
            "scope_type": "global",
            "scope_value": None,
            "monthly_limit": "500.00",
            "alert_at_pct": 80,
        }

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[budget_row])

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications._get_org_admin_email", return_value="admin@example.com"),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("420.00")),
            patch("api.workers.notifications._get_slack_channel",
                  return_value=("xoxb-token", "C1", True)),  # muted
            patch("api.workers.notifications.resend"),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            send_budget_alert.apply(args=["budget-1", 84, ORG_ID])

        mock_post.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Feature D - Anomaly Explainer
# ══════════════════════════════════════════════════════════════════════════════


class TestAnomalyExplainerService:
    """services/anomaly_explainer.py - pure rate-limit + API call logic."""

    def test_returns_none_when_no_api_key(self) -> None:
        from api.services.anomaly_explainer import generate_explanation

        with patch("api.services.anomaly_explainer.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            result = generate_explanation(_anomaly_row(), ORG_ID)

        assert result is None

    def test_returns_none_when_rate_limited(self) -> None:
        from api.services.anomaly_explainer import generate_explanation

        with (
            patch("api.services.anomaly_explainer.settings") as mock_settings,
            patch("api.services.anomaly_explainer.is_rate_limited", return_value=True),
        ):
            mock_settings.anthropic_api_key = "sk-test"
            result = generate_explanation(_anomaly_row(), ORG_ID)

        assert result is None

    def test_returns_explanation_text_on_success(self) -> None:
        from api.services.anomaly_explainer import generate_explanation

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="  Usage spike caused by new chat feature.  ")]

        with (
            patch("api.services.anomaly_explainer.settings") as mock_settings,
            patch("api.services.anomaly_explainer.is_rate_limited", return_value=False),
            patch("api.services.anomaly_explainer._consume_quota"),
            patch("api.services.anomaly_explainer.anthropic") as mock_anthropic,
        ):
            mock_settings.anthropic_api_key = "sk-test"
            mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_message
            result = generate_explanation(_anomaly_row(), ORG_ID)

        assert result == "Usage spike caused by new chat feature."

    def test_returns_none_on_api_failure(self) -> None:
        from api.services.anomaly_explainer import generate_explanation

        with (
            patch("api.services.anomaly_explainer.settings") as mock_settings,
            patch("api.services.anomaly_explainer.is_rate_limited", return_value=False),
            patch("api.services.anomaly_explainer.anthropic") as mock_anthropic,
        ):
            mock_settings.anthropic_api_key = "sk-test"
            mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception("API error")
            result = generate_explanation(_anomaly_row(), ORG_ID)

        assert result is None


class TestIsRateLimited:
    def test_not_limited_when_key_absent(self) -> None:
        from api.services.anomaly_explainer import is_rate_limited

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("api.services.anomaly_explainer._redis", return_value=mock_redis):
            assert is_rate_limited(ORG_ID) is False

    def test_not_limited_below_cap(self) -> None:
        from api.services.anomaly_explainer import is_rate_limited

        mock_redis = MagicMock()
        mock_redis.get.return_value = "2"

        with (
            patch("api.services.anomaly_explainer._redis", return_value=mock_redis),
            patch("api.services.anomaly_explainer.settings") as mock_settings,
        ):
            mock_settings.ai_calls_per_org_per_day = 3
            assert is_rate_limited(ORG_ID) is False

    def test_limited_at_cap(self) -> None:
        from api.services.anomaly_explainer import is_rate_limited

        mock_redis = MagicMock()
        mock_redis.get.return_value = "3"

        with (
            patch("api.services.anomaly_explainer._redis", return_value=mock_redis),
            patch("api.services.anomaly_explainer.settings") as mock_settings,
        ):
            mock_settings.ai_calls_per_org_per_day = 3
            assert is_rate_limited(ORG_ID) is True


class TestExplainAnomalyTask:
    """workers/anomaly_explainer.py - Celery task."""

    def test_generates_and_persists_explanation(self) -> None:
        from api.workers.anomaly_explainer import explain_anomaly

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_anomaly_row()])

        with (
            patch("api.workers.anomaly_explainer._get_supabase", return_value=db),
            patch(
                "api.workers.anomaly_explainer.generate_explanation",
                return_value="Traffic spike from new chat feature rollout.",
            ),
        ):
            explain_anomaly.apply(args=["anom-1"])

        db.update.assert_called()
        update_payload = db.update.call_args[0][0]
        assert update_payload["explanation"] == "Traffic spike from new chat feature rollout."
        assert "explanation_generated_at" in update_payload

    def test_skips_when_explanation_is_fresh(self) -> None:
        from api.workers.anomaly_explainer import explain_anomaly

        # Set generated_at to 1 hour ago - within the 24h cache
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        row = {**_anomaly_row(), "explanation_generated_at": recent_ts}

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[row])

        with (
            patch("api.workers.anomaly_explainer._get_supabase", return_value=db),
            patch("api.workers.anomaly_explainer.generate_explanation") as mock_gen,
        ):
            explain_anomaly.apply(args=["anom-1"])

        mock_gen.assert_not_called()
        db.update.assert_not_called()

    def test_regenerates_after_cache_ttl(self) -> None:
        from api.workers.anomaly_explainer import explain_anomaly

        # Set generated_at to 25 hours ago - past the 24h cache TTL
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        row = {**_anomaly_row(), "explanation_generated_at": stale_ts}

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[row])

        with (
            patch("api.workers.anomaly_explainer._get_supabase", return_value=db),
            patch(
                "api.workers.anomaly_explainer.generate_explanation",
                return_value="Fresh explanation.",
            ),
        ):
            explain_anomaly.apply(args=["anom-1"])

        db.update.assert_called()

    def test_skips_when_generate_returns_none(self) -> None:
        from api.workers.anomaly_explainer import explain_anomaly

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[_anomaly_row()])

        with (
            patch("api.workers.anomaly_explainer._get_supabase", return_value=db),
            patch("api.workers.anomaly_explainer.generate_explanation", return_value=None),
        ):
            explain_anomaly.apply(args=["anom-1"])

        db.update.assert_not_called()

    def test_no_op_when_anomaly_not_found(self) -> None:
        from api.workers.anomaly_explainer import explain_anomaly

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[])

        with (
            patch("api.workers.anomaly_explainer._get_supabase", return_value=db),
            patch("api.workers.anomaly_explainer.generate_explanation") as mock_gen,
        ):
            explain_anomaly.apply(args=["does-not-exist"])

        mock_gen.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Feature D - _consume_quota Redis behaviour
# ══════════════════════════════════════════════════════════════════════════════


class TestConsumeQuota:
    """TC-M3-D06 and TC-M3-D07: _consume_quota increments counter and sets TTL."""

    def test_increments_redis_counter(self) -> None:  # TC-M3-D06
        from api.services.anomaly_explainer import _consume_quota

        mock_pipe = MagicMock()
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("api.services.anomaly_explainer._redis", return_value=mock_redis):
            _consume_quota(ORG_ID)

        mock_pipe.incr.assert_called_once()
        # The key passed to incr must contain the org_id
        incr_key = mock_pipe.incr.call_args[0][0]
        assert ORG_ID in incr_key

    def test_sets_25h_ttl(self) -> None:  # TC-M3-D07
        from api.services.anomaly_explainer import _consume_quota

        mock_pipe = MagicMock()
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("api.services.anomaly_explainer._redis", return_value=mock_redis):
            _consume_quota(ORG_ID)

        mock_pipe.expire.assert_called_once()
        expire_args = mock_pipe.expire.call_args[0]
        # Second positional arg is the TTL in seconds: 25 h = 90_000 s
        assert expire_args[1] == 90_000
