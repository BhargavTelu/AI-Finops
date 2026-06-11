"""
Unit tests for the weekly email digest (Phase 3) in workers/notifications.py.
Supabase + Resend mocked.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from api.workers import notifications

ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"
ORG_C = "00000000-0000-0000-0000-00000000000c"


def _db_for_fanout(
    active_orgs: list[str],
    slack_orgs: list[str],
    opted_in_orgs: list[str],
) -> MagicMock:
    db = MagicMock()

    def table(name: str) -> MagicMock:
        chain = MagicMock()
        for method in ("select", "eq", "limit", "order"):
            getattr(chain, method).return_value = chain
        result = MagicMock()
        if name == "integrations":
            result.data = [{"org_id": o} for o in active_orgs]
        elif name == "slack_integrations":
            result.data = [{"org_id": o} for o in slack_orgs]
        elif name == "organizations":
            result.data = [{"id": o} for o in opted_in_orgs]
        else:
            result.data = []
        chain.execute.return_value = result
        return chain

    db.table.side_effect = table
    return db


_DIGEST_DATA = {
    "yesterday_usd": Decimal("42.00"),
    "avg_7d_usd": Decimal("40.00"),
    "mom_pct": 12,
    "top_drivers": [{"label": "gpt-4o", "usd": Decimal("30.00")}],
    "open_anomaly_count": 2,
}


def _all_accessible(db, org_ids):
    return set(org_ids)


class TestWeeklyFanOut:
    def test_excludes_slack_connected_orgs(self) -> None:
        db = _db_for_fanout(
            active_orgs=[ORG_A, ORG_B],
            slack_orgs=[ORG_B],
            opted_in_orgs=[ORG_A, ORG_B],
        )
        with (
            patch.object(notifications, "_get_supabase", return_value=db),
            patch(
                "api.services.billing_access.filter_accessible_org_ids",
                side_effect=_all_accessible,
            ),
            patch.object(notifications.send_weekly_email_digest, "delay") as mock_delay,
        ):
            notifications.send_weekly_email_digests()
        mock_delay.assert_called_once_with(ORG_A)

    def test_excludes_opted_out_orgs(self) -> None:
        db = _db_for_fanout(
            active_orgs=[ORG_A, ORG_C],
            slack_orgs=[],
            opted_in_orgs=[ORG_C],  # ORG_A opted out
        )
        with (
            patch.object(notifications, "_get_supabase", return_value=db),
            patch(
                "api.services.billing_access.filter_accessible_org_ids",
                side_effect=_all_accessible,
            ),
            patch.object(notifications.send_weekly_email_digest, "delay") as mock_delay,
        ):
            notifications.send_weekly_email_digests()
        mock_delay.assert_called_once_with(ORG_C)

    def test_excludes_lapsed_orgs(self) -> None:
        # Regression: an org whose trial lapsed must not keep getting weekly
        # email - that's spam to someone who churned.
        db = _db_for_fanout(
            active_orgs=[ORG_A, ORG_B],
            slack_orgs=[],
            opted_in_orgs=[ORG_A, ORG_B],
        )
        with (
            patch.object(notifications, "_get_supabase", return_value=db),
            patch(
                "api.services.billing_access.filter_accessible_org_ids",
                return_value={ORG_B},  # ORG_A lapsed
            ),
            patch.object(notifications.send_weekly_email_digest, "delay") as mock_delay,
        ):
            notifications.send_weekly_email_digests()
        mock_delay.assert_called_once_with(ORG_B)

    def test_no_candidates_no_dispatch(self) -> None:
        db = _db_for_fanout(active_orgs=[ORG_A], slack_orgs=[ORG_A], opted_in_orgs=[ORG_A])
        with (
            patch.object(notifications, "_get_supabase", return_value=db),
            patch.object(notifications.send_weekly_email_digest, "delay") as mock_delay,
        ):
            notifications.send_weekly_email_digests()
        mock_delay.assert_not_called()


class TestWeeklyEmailSend:
    def test_sends_email_with_subject(self) -> None:
        with (
            patch.object(notifications, "_get_supabase", return_value=MagicMock()),
            patch.object(notifications, "_get_org_admin_email", return_value="cto@acme.com"),
            patch.object(notifications, "_fetch_digest_data", return_value=_DIGEST_DATA),
            patch.object(notifications.resend.Emails, "send") as mock_send,
        ):
            notifications.send_weekly_email_digest(ORG_A)
        payload = mock_send.call_args.args[0]
        assert payload["to"] == ["cto@acme.com"]
        assert payload["subject"] == "Your week in LLM spend"
        assert "280.00" in payload["html"]  # 40/day * 7

    def test_no_admin_email_skips_quietly(self) -> None:
        with (
            patch.object(notifications, "_get_supabase", return_value=MagicMock()),
            patch.object(notifications, "_get_org_admin_email", return_value=None),
            patch.object(notifications.resend.Emails, "send") as mock_send,
        ):
            notifications.send_weekly_email_digest(ORG_A)
        mock_send.assert_not_called()

    def test_zero_spend_week_skips_send(self) -> None:
        # Regression: an org with a connected key but no usage must not get
        # a "$0.00 this week" email.
        zero_data = {**_DIGEST_DATA, "avg_7d_usd": Decimal("0")}
        with (
            patch.object(notifications, "_get_supabase", return_value=MagicMock()),
            patch.object(notifications, "_get_org_admin_email", return_value="cto@acme.com"),
            patch.object(notifications, "_fetch_digest_data", return_value=zero_data),
            patch.object(notifications.resend.Emails, "send") as mock_send,
        ):
            notifications.send_weekly_email_digest(ORG_A)
        mock_send.assert_not_called()


class TestWeeklyEmailHtml:
    def test_contains_metrics_and_unsubscribe(self) -> None:
        html = notifications._weekly_email_html(_DIGEST_DATA)
        assert "$280.00" in html       # week total
        assert "$40.00" in html        # daily average
        assert "+12%" in html          # MoM
        assert "gpt-4o" in html        # top driver
        assert "2 open" in html        # anomalies
        assert "unsubscribe" in html.lower()

    def test_negative_mom_renders_green(self) -> None:
        data = {**_DIGEST_DATA, "mom_pct": -8}
        html = notifications._weekly_email_html(data)
        assert "-8%" in html
        assert "#16825d" in html  # green

    def test_handles_no_mom_and_no_drivers(self) -> None:
        data = {**_DIGEST_DATA, "mom_pct": None, "top_drivers": [], "open_anomaly_count": 0}
        html = notifications._weekly_email_html(data)
        assert "no prior-month baseline" in html
        assert "No spend recorded" in html
        assert "none open" in html
