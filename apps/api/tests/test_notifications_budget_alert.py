"""
Additional notification worker tests focused on send_budget_alert email path.
TC-NOT-17: send_budget_alert sends email via Resend when configured.
TC-NOT-18: send_budget_alert no admin email → returns early without sending.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from api.workers.notifications import send_budget_alert

ORG_ID = "00000000-0000-0000-0000-000000000001"
BUDGET_ID = "bbbbbbbb-0000-0000-0000-000000000002"

_SCOPE_SPEND_PATCH = "api.workers.budget_checks._compute_scope_spend"


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


def _budget_row() -> dict:
    return {
        "id": BUDGET_ID,
        "org_id": ORG_ID,
        "scope_type": "global",
        "scope_value": None,
        "monthly_limit": "1000.00",
        "alert_at_pct": 80,
    }


class TestSendBudgetAlertEmail:
    def test_sends_email_via_resend(self) -> None:  # TC-NOT-17
        """When admin email is available, resend.Emails.send is called with budget details."""
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_budget_row()]),             # budget fetch
            MagicMock(data=[{"user_id": "u1"}]),         # admin member
            MagicMock(data=[{"email": "cfo@company.com"}]),  # admin email
            MagicMock(data=[]),                          # no Slack
        ]
        mock_resend = MagicMock()

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch(
                "api.workers.notifications.resend",
                mock_resend,
            ),
            patch(_SCOPE_SPEND_PATCH, return_value=Decimal("820")),
            patch("api.workers.notifications.settings") as mock_settings,
        ):
            mock_settings.resend_api_key = "re_test_key"
            mock_settings.from_email = "noreply@test.com"
            mock_settings.encryption_key = ""
            send_budget_alert.apply(args=[BUDGET_ID, 82, ORG_ID])

        mock_resend.Emails.send.assert_called_once()
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["cfo@company.com"]
        assert "82" in call_args["subject"] or "82" in call_args["html"]

    def test_no_admin_email_returns_without_sending(self) -> None:  # TC-NOT-18
        """If no admin email exists, task returns early without calling resend."""
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[_budget_row()]),  # budget fetch
            MagicMock(data=[]),               # no admin members
        ]
        mock_resend = MagicMock()

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.resend", mock_resend),
            patch(_SCOPE_SPEND_PATCH, return_value=Decimal("820")),
            patch("api.workers.notifications.settings") as mock_settings,
        ):
            mock_settings.resend_api_key = "re_test_key"
            mock_settings.from_email = "noreply@test.com"
            mock_settings.encryption_key = ""
            send_budget_alert.apply(args=[BUDGET_ID, 82, ORG_ID])

        mock_resend.Emails.send.assert_not_called()
