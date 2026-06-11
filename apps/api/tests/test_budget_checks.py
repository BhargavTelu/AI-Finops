"""
Unit tests for budget check worker logic.
Covers:
  - _same_calendar_month: idempotency guard helper
  - _compute_scope_spend: correct DB filtering per scope_type
  - check_org: threshold detection, alert firing, notified_at guard
All Supabase calls are mocked - no network, no DB.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

from api.workers.budget_checks import (
    _same_calendar_month,
    _compute_scope_spend,
    check_org,
)

ORG_ID = "00000000-0000-0000-0000-000000000001"
BUDGET_ID = "bbbbbbbb-0000-0000-0000-000000000001"


# ── DB mock ─────────────────────────────────────────────────────────────────────

def _mock_db() -> MagicMock:
    """Supabase client mock; all chained query methods return self."""
    db = MagicMock()
    empty = MagicMock()
    empty.data = []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.lt.return_value = db
    db.is_.return_value = db
    db.order.return_value = db
    db.range.return_value = db
    db.limit.return_value = db
    db.execute.return_value = empty
    return db


def _db_with_rows(rows: list[dict]) -> MagicMock:
    db = _mock_db()
    result = MagicMock()
    result.data = rows
    db.execute.return_value = result
    return db


# ── _same_calendar_month ────────────────────────────────────────────────────────

class TestSameCalendarMonth:
    def test_none_returns_false(self) -> None:
        assert _same_calendar_month(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert _same_calendar_month("") is False

    def test_current_month_returns_true(self) -> None:
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        assert _same_calendar_month(ts) is True

    def test_previous_month_returns_false(self) -> None:
        now = datetime.now(timezone.utc)
        # Subtract enough days to guarantee a different month
        prev_month = now.replace(day=1)
        if prev_month.month == 1:
            prev_ts = prev_month.replace(year=prev_month.year - 1, month=12).isoformat()
        else:
            prev_ts = prev_month.replace(month=prev_month.month - 1).isoformat()
        assert _same_calendar_month(prev_ts) is False

    def test_z_suffix_parsed_correctly(self) -> None:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _same_calendar_month(ts) is True

    def test_malformed_string_returns_false(self) -> None:
        assert _same_calendar_month("not-a-date") is False


# ── _compute_scope_spend ────────────────────────────────────────────────────────

class TestComputeScopeSpend:
    def _spend_rows(self, amounts: list[float]) -> list[dict]:
        return [{"total_cost_usd": str(a)} for a in amounts]

    def test_global_sums_all_rows(self) -> None:
        db = _db_with_rows(self._spend_rows([100.0, 200.0, 50.0]))
        result = _compute_scope_spend(db, ORG_ID, "global", None)
        assert result == Decimal("350.0")

    def test_empty_rows_returns_zero(self) -> None:
        db = _db_with_rows([])
        result = _compute_scope_spend(db, ORG_ID, "global", None)
        assert result == Decimal("0")

    def test_provider_scope_calls_eq_with_provider(self) -> None:
        db = _db_with_rows(self._spend_rows([300.0]))
        _compute_scope_spend(db, ORG_ID, "provider", "openai")
        # Verify eq("provider", "openai") was called somewhere in the chain
        eq_calls = [str(c) for c in db.eq.call_args_list]
        assert any("openai" in c for c in eq_calls)

    def test_model_scope_calls_eq_with_model(self) -> None:
        db = _db_with_rows(self._spend_rows([150.0]))
        _compute_scope_spend(db, ORG_ID, "model", "gpt-4o")
        eq_calls = [str(c) for c in db.eq.call_args_list]
        assert any("gpt-4o" in c for c in eq_calls)

    def test_feature_tag_scope(self) -> None:
        db = _db_with_rows(self._spend_rows([75.0]))
        result = _compute_scope_spend(db, ORG_ID, "feature_tag", "chat")
        assert result == Decimal("75.0")

    def test_multiple_rows_summed_correctly(self) -> None:
        db = _db_with_rows(self._spend_rows([10.5, 20.25, 5.0]))
        result = _compute_scope_spend(db, ORG_ID, "team_tag", "backend")
        assert result == Decimal("35.75")


# ── check_org ────────────────────────────────────────────────────────────────────

def _budget_row(
    monthly_limit: float = 1000.0,
    alert_at_pct: int = 80,
    notified_80_at: str | None = None,
    notified_100_at: str | None = None,
) -> dict:
    return {
        "id": BUDGET_ID,
        "org_id": ORG_ID,
        "scope_type": "global",
        "scope_value": None,
        "monthly_limit": str(monthly_limit),
        "alert_at_pct": alert_at_pct,
        "notified_80_at": notified_80_at,
        "notified_100_at": notified_100_at,
    }


class TestCheckOrg:
    def _run(self, budget: dict, mtd_spend: Decimal):
        db = _mock_db()
        budgets_result = MagicMock()
        budgets_result.data = [budget]
        db.execute.return_value = budgets_result

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=mtd_spend),
            patch("api.workers.budget_checks.send_budget_alert") as mock_alert,
        ):
            check_org(ORG_ID)
        return db, mock_alert

    def test_below_threshold_no_alert(self) -> None:
        """70% spent - below default 80% threshold, no alert."""
        _, mock_alert = self._run(_budget_row(), Decimal("700"))
        mock_alert.delay.assert_not_called()

    def test_at_80pct_threshold_fires_warning_alert(self) -> None:
        """Exactly 80% spent → fires alert with pct=80."""
        _, mock_alert = self._run(_budget_row(), Decimal("800"))
        mock_alert.delay.assert_called_once_with(BUDGET_ID, 80, ORG_ID)

    def test_over_threshold_fires_alert(self) -> None:
        """85% spent → fires alert at alert_at_pct (80)."""
        _, mock_alert = self._run(_budget_row(), Decimal("850"))
        mock_alert.delay.assert_called_once_with(BUDGET_ID, 80, ORG_ID)

    def test_at_100pct_fires_exceeded_alert_not_warning(self) -> None:
        """100% spent → fires 100 alert (not the 80 warning)."""
        _, mock_alert = self._run(_budget_row(), Decimal("1000"))
        mock_alert.delay.assert_called_once_with(BUDGET_ID, 100, ORG_ID)

    def test_over_100pct_fires_exceeded_alert(self) -> None:
        """120% spent → fires 100 alert."""
        _, mock_alert = self._run(_budget_row(), Decimal("1200"))
        mock_alert.delay.assert_called_once_with(BUDGET_ID, 100, ORG_ID)

    def test_80pct_guard_prevents_resend_same_month(self) -> None:
        """80% already notified this month → no re-alert."""
        now_iso = datetime.now(timezone.utc).isoformat()
        _, mock_alert = self._run(_budget_row(notified_80_at=now_iso), Decimal("850"))
        mock_alert.delay.assert_not_called()

    def test_100pct_guard_prevents_resend_same_month(self) -> None:
        """100% already notified this month → no re-alert."""
        now_iso = datetime.now(timezone.utc).isoformat()
        _, mock_alert = self._run(_budget_row(notified_100_at=now_iso), Decimal("1000"))
        mock_alert.delay.assert_not_called()

    def test_guard_allows_resend_new_month(self) -> None:
        """notified_80_at from last month → allowed to re-alert this month."""
        now = datetime.now(timezone.utc)
        if now.month == 1:
            prev_ts = now.replace(year=now.year - 1, month=12, day=1).isoformat()
        else:
            prev_ts = now.replace(month=now.month - 1, day=1).isoformat()

        _, mock_alert = self._run(_budget_row(notified_80_at=prev_ts), Decimal("850"))
        mock_alert.delay.assert_called_once_with(BUDGET_ID, 80, ORG_ID)

    def test_no_budgets_returns_early(self) -> None:
        """Org with no budgets - no alerts, no crash."""
        db = _mock_db()
        empty_result = MagicMock()
        empty_result.data = []
        db.execute.return_value = empty_result

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks.send_budget_alert") as mock_alert,
        ):
            check_org(ORG_ID)
        mock_alert.delay.assert_not_called()

    def test_notified_80_at_written_after_alert(self) -> None:
        """After firing 80% alert, notified_80_at is written to DB."""
        db = _mock_db()
        budgets_result = MagicMock()
        budgets_result.data = [_budget_row()]
        db.execute.return_value = budgets_result

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks._compute_scope_spend", return_value=Decimal("800")),
            patch("api.workers.budget_checks.send_budget_alert"),
        ):
            check_org(ORG_ID)

        # Verify update was called with notified_80_at key
        update_calls = db.update.call_args_list
        assert any("notified_80_at" in str(c) for c in update_calls)

    def test_zero_limit_budget_skipped(self) -> None:
        """Budget with monthly_limit=0 is skipped to avoid divide-by-zero."""
        _, mock_alert = self._run(_budget_row(monthly_limit=0.0), Decimal("500"))
        mock_alert.delay.assert_not_called()

    def test_custom_alert_threshold_respected(self) -> None:
        """Budget with alert_at_pct=60 fires at 60% spend."""
        _, mock_alert = self._run(_budget_row(monthly_limit=1000.0, alert_at_pct=60), Decimal("600"))
        mock_alert.delay.assert_called_once_with(BUDGET_ID, 60, ORG_ID)


# ── TC-FAN-03 & TC-FAN-04: check_all_orgs fan-out ────────────────────────────

class TestCheckAllOrgsFanOut:
    """TC-FAN-03 and TC-FAN-04 - check_all_orgs dispatches to unique org_ids."""

    def test_dispatches_once_per_unique_org(self) -> None:
        """TC-FAN-03 - budgets from 3 distinct org_ids → check_org.delay called 3 times."""
        from api.workers.budget_checks import check_all_orgs

        rows = [
            {"org_id": "org-111"},
            {"org_id": "org-222"},
            {"org_id": "org-333"},
        ]
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.execute.return_value = MagicMock(data=rows)

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks.check_org") as mock_task,
        ):
            mock_task.delay = MagicMock()
            check_all_orgs()

        assert mock_task.delay.call_count == 3, (
            f"Expected check_org.delay called 3 times (one per unique org), "
            f"got {mock_task.delay.call_count}"
        )
        called_ids = {call.args[0] for call in mock_task.delay.call_args_list}
        assert called_ids == {"org-111", "org-222", "org-333"}

    def test_no_budgets_does_not_dispatch(self) -> None:
        """TC-FAN-04 - no budgets in DB → check_org.delay never called."""
        from api.workers.budget_checks import check_all_orgs

        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.execute.return_value = MagicMock(data=[])

        with (
            patch("api.workers.budget_checks._get_supabase", return_value=db),
            patch("api.workers.budget_checks.check_org") as mock_task,
        ):
            mock_task.delay = MagicMock()
            check_all_orgs()

        mock_task.delay.assert_not_called()
