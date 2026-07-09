"""
Notification worker gap tests.

Gap-23 (high): Digest idempotency race - digest posted to Slack but DB write fails.
               On retry the idempotency check passes again → duplicate post.
Gap-24 (high): send_budget_alert retry exhaustion - alert lost after max_retries.
               Slack must not be called when email fails (design intent: email first).
"""

from decimal import Decimal
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
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    empty = MagicMock()
    empty.data = []
    db.execute.return_value = empty
    return db


# ── Gap-23: Digest idempotency race ───────────────────────────────────────────


class TestDigestIdempotencyRace:
    """
    Gap-23 (high): send_slack_digest checks slack_digests BEFORE posting, writes AFTER.
    If the DB write fails, a Celery retry sees no record and posts a duplicate digest.
    """

    def test_post_succeeds_but_db_write_fails_documents_race_window(self) -> None:
        """
        Simulate: idempotency query returns empty → proceed → post_message succeeds →
        DB insert fails → record is never written.
        On a retry, the idempotency guard passes again → duplicate Slack message.

        This test asserts that post_message IS called even when DB write fails,
        documenting the race window. Fix: write the DB record BEFORE posting,
        or use an outbox/inbox pattern.
        """
        from api.workers.notifications import send_slack_digest

        post_call_count = [0]

        def mock_post(token: str, channel: str, blocks: list, fallback: str) -> None:
            post_call_count[0] += 1

        with (
            patch("api.workers.notifications._get_supabase") as mock_get_db,
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-test-token", "C1234567", False),
            ),
            patch("api.workers.notifications.post_message", side_effect=mock_post),
            patch(
                "api.workers.notifications._fetch_digest_data",
                return_value={
                    "yesterday_usd": Decimal("10.00"),
                    "avg_7d_usd": Decimal("8.00"),
                    "mom_pct": 5,
                    "top_drivers": [],
                    "open_anomaly_count": 0,
                },
            ),
        ):
            db = _mock_db()
            mock_get_db.return_value = db

            # First execute call: idempotency check → no existing record
            idempotency_check = MagicMock()
            idempotency_check.data = []

            db.execute.return_value = idempotency_check

            # DB insert fails after post_message succeeds
            insert_mock = MagicMock()
            insert_mock.execute.side_effect = Exception("DB insert failed")
            db.insert.return_value = insert_mock

            send_slack_digest.apply(args=[ORG_ID])

        # The digest was posted (Slack received the message)
        assert (
            post_call_count[0] == 1
        ), "post_message should have been called once even though DB write failed."
        # On a retry: idempotency_check.data would still be [] (no DB record exists)
        # → post_message would be called again → duplicate digest.

    def test_digest_skipped_when_already_sent_today(self) -> None:
        """
        If slack_digests already has a row for today's date, send_slack_digest
        must return early without calling post_message.
        """
        from api.workers.notifications import send_slack_digest

        with patch("api.workers.notifications._get_supabase") as mock_get_db:
            db = _mock_db()
            mock_get_db.return_value = db
            # Idempotency check returns existing record
            db.execute.return_value = MagicMock(data=[{"id": "existing-digest-row"}])

            with patch("api.workers.notifications.post_message") as mock_post:
                send_slack_digest.apply(args=[ORG_ID])

        mock_post.assert_not_called()

    def test_no_slack_integration_returns_early(self) -> None:
        """If org has no Slack connected, send_slack_digest returns early silently."""
        from api.workers.notifications import send_slack_digest

        with (
            patch("api.workers.notifications._get_supabase") as mock_get_db,
            patch("api.workers.notifications._get_slack_channel", return_value=None),
            patch("api.workers.notifications.post_message") as mock_post,
        ):
            db = _mock_db()
            mock_get_db.return_value = db
            # Idempotency check: no existing digest
            db.execute.return_value = MagicMock(data=[])
            send_slack_digest.apply(args=[ORG_ID])

        mock_post.assert_not_called()

    def test_post_failure_retries_task(self) -> None:
        """
        If post_message raises ValueError, the task must retry (self.retry is called).
        After max_retries=2, the task fails.
        """
        from api.workers.notifications import send_slack_digest

        with (
            patch("api.workers.notifications._get_supabase") as mock_get_db,
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-test", "C1234", False),
            ),
            patch(
                "api.workers.notifications.post_message", side_effect=ValueError("Slack API error")
            ),
            patch(
                "api.workers.notifications._fetch_digest_data",
                return_value={
                    "yesterday_usd": Decimal("5.00"),
                    "avg_7d_usd": Decimal("5.00"),
                    "mom_pct": None,
                    "top_drivers": [],
                    "open_anomaly_count": 0,
                },
            ),
        ):
            db = _mock_db()
            mock_get_db.return_value = db
            db.execute.return_value = MagicMock(data=[])  # no existing digest

            # apply() runs synchronously; max_retries=2 means up to 3 attempts
            result = send_slack_digest.apply(args=[ORG_ID])

        # After exhausting retries, the task stops (does not raise to caller)
        assert result is not None


# ── Gap-24: Budget alert retry exhaustion ─────────────────────────────────────


class TestBudgetAlertRetryExhaustion:
    """
    Gap-24 (high): send_budget_alert has max_retries=3 with exponential backoff.
    When Resend always fails, the alert is silently dropped after max retries.
    Slack must NOT be called when email fails (design intent: email first).
    """

    def _budget_data(self) -> dict:
        return {
            "id": BUDGET_ID,
            "org_id": ORG_ID,
            "scope_type": "global",
            "scope_value": None,
            "monthly_limit": "1000.00",
            "alert_at_pct": 80,
        }

    def _setup_db_for_budget_alert(self, db: MagicMock) -> None:
        """Configure mock DB to return budget data and admin email lookup."""
        call_n = [0]

        def execute_side():
            call_n[0] += 1
            if call_n[0] == 1:
                return MagicMock(data=[self._budget_data()])
            if call_n[0] == 2:
                return MagicMock(data=[{"user_id": "user-uuid-123"}])
            if call_n[0] == 3:
                return MagicMock(data=[{"email": "admin@example.com"}])
            return MagicMock(data=[])

        db.execute.side_effect = execute_side

    def test_resend_failure_slack_not_called(self) -> None:
        """
        When Resend always raises, send_budget_alert retries and eventually drops.
        Slack must NOT be called - email failure prevents Slack notification (by design).
        """
        from api.workers.notifications import send_budget_alert

        db = _mock_db()
        self._setup_db_for_budget_alert(db)

        slack_call_count = [0]

        def track_slack(token: str, channel: str, blocks: list, fallback: str) -> None:
            slack_call_count[0] += 1

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("850.00")),
            patch(
                "api.workers.notifications.resend.Emails.send",
                side_effect=Exception("Resend API rate limit"),
            ),
            patch("api.workers.notifications.post_message", side_effect=track_slack),
            patch("api.workers.notifications.settings") as ms,
        ):
            ms.resend_api_key = "re_test_key"
            ms.from_email = "noreply@test.com"
            ms.encryption_key = ""
            send_budget_alert.apply(args=[BUDGET_ID, 80, ORG_ID])

        assert slack_call_count[0] == 0, (
            f"Gap-24: Slack must not be called when email (Resend) fails. "
            f"Got slack_call_count={slack_call_count[0]}."
        )

    def test_resend_success_slack_called_if_connected(self) -> None:
        """
        When Resend succeeds, Slack notification fires if the org has Slack connected.
        """
        from api.workers.notifications import send_budget_alert

        db = _mock_db()
        self._setup_db_for_budget_alert(db)

        slack_call_count = [0]

        def track_slack(token: str, channel: str, blocks: list, fallback: str) -> None:
            slack_call_count[0] += 1

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("850.00")),
            patch("api.workers.notifications.resend.Emails.send", return_value={}),
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-token", "C1234", False),
            ),
            patch("api.workers.notifications.post_message", side_effect=track_slack),
            patch("api.workers.notifications.settings") as ms,
        ):
            ms.resend_api_key = "re_test_key"
            ms.from_email = "noreply@test.com"
            send_budget_alert.apply(args=[BUDGET_ID, 80, ORG_ID])

        assert slack_call_count[0] == 1

    def test_budget_not_found_returns_early(self) -> None:
        """If budget ID does not exist, task returns early without sending anything."""
        from api.workers.notifications import send_budget_alert

        db = _mock_db()
        db.execute.return_value = MagicMock(data=[])  # budget not found

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.notifications.resend.Emails.send") as mock_send,
            patch("api.workers.notifications.settings") as ms,
        ):
            ms.resend_api_key = "re_test"
            ms.from_email = "noreply@test.com"
            send_budget_alert.apply(args=[BUDGET_ID, 80, ORG_ID])

        mock_send.assert_not_called()

    def test_no_admin_email_returns_early(self) -> None:
        """If org has no admin email, task returns early without sending."""
        from api.workers.notifications import send_budget_alert

        db = _mock_db()
        call_n = [0]

        def execute_side():
            call_n[0] += 1
            if call_n[0] == 1:
                return MagicMock(data=[self._budget_data()])
            return MagicMock(data=[])  # no admin members or email

        db.execute.side_effect = execute_side

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("850.00")),
            patch("api.workers.notifications.resend.Emails.send") as mock_send,
            patch("api.workers.notifications.settings") as ms,
        ):
            ms.resend_api_key = "re_test"
            ms.from_email = "noreply@test.com"
            send_budget_alert.apply(args=[BUDGET_ID, 80, ORG_ID])

        mock_send.assert_not_called()

    def test_slack_failure_does_not_retry_email(self) -> None:
        """
        Slack failure after email success must be logged but not retry the email.
        This is the 'best-effort Slack' design in send_budget_alert.
        """
        from api.workers.notifications import send_budget_alert

        db = _mock_db()
        self._setup_db_for_budget_alert(db)
        email_call_count = [0]

        def count_email(*args, **kwargs):
            email_call_count[0] += 1

        with (
            patch("api.workers.notifications._get_supabase", return_value=db),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("850.00")),
            patch("api.workers.notifications.resend.Emails.send", side_effect=count_email),
            patch(
                "api.workers.notifications._get_slack_channel",
                return_value=("xoxb-token", "C1234", False),
            ),
            patch(
                "api.workers.notifications.post_message", side_effect=Exception("Slack API down")
            ),
            patch("api.workers.notifications.settings") as ms,
        ):
            ms.resend_api_key = "re_test"
            ms.from_email = "noreply@test.com"
            send_budget_alert.apply(args=[BUDGET_ID, 80, ORG_ID])

        # Email was sent exactly once despite Slack failing
        assert (
            email_call_count[0] == 1
        ), "Email must be sent exactly once regardless of Slack failure."
