"""
Unit tests for workers/reports.py - dispatch fan-out, idempotency semantics,
R2-unconfigured fallback, and the email path. Supabase + R2 mocked.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from api.workers import reports as reports_worker

ORG_ID = "00000000-0000-0000-0000-000000000001"


def _query_result(rows: list[dict]) -> MagicMock:
    result = MagicMock()
    result.data = rows
    return result


def _make_db(table_rows: dict[str, list[dict]]) -> MagicMock:
    """Chainable Supabase mock returning fixed rows per table name."""
    db = MagicMock()

    def table(name: str) -> MagicMock:
        chain = MagicMock()
        for method in ("select", "eq", "gte", "lte", "lt", "order", "range", "limit",
                       "insert", "update"):
            getattr(chain, method).return_value = chain
        chain.execute.return_value = _query_result(table_rows.get(name, []))
        return chain

    db.table.side_effect = table
    return db


_SUMMARY_ROW = {
    "total_cost_usd": "100.00", "total_requests": 10, "total_tokens": 1000,
    "provider": "openai", "model": "gpt-4o",
    "feature_tag": "chat", "team_tag": "", "customer_tag": "",
}


class TestPreviousMonthRange:
    def test_mid_month(self) -> None:
        start, end = reports_worker._previous_month_range(date(2026, 6, 11))
        assert (start, end) == (date(2026, 5, 1), date(2026, 5, 31))

    def test_january_rolls_to_december(self) -> None:
        start, end = reports_worker._previous_month_range(date(2026, 1, 1))
        assert (start, end) == (date(2025, 12, 1), date(2025, 12, 31))


class TestMomComparisonRange:
    """Regression: a month-to-date report must compare against the SAME number
    of days last month, not the full prior month (-97% headline bug)."""

    def test_partial_month_compares_same_days(self) -> None:
        start, end = reports_worker._mom_comparison_range(
            date(2026, 6, 1), date(2026, 6, 11)
        )
        assert (start, end) == (date(2026, 5, 1), date(2026, 5, 11))

    def test_complete_month_compares_full_prev_month(self) -> None:
        # May (31d) vs April (30d): capped at April's length -> full April.
        start, end = reports_worker._mom_comparison_range(
            date(2026, 5, 1), date(2026, 5, 31)
        )
        assert (start, end) == (date(2026, 4, 1), date(2026, 4, 30))

    def test_march_vs_february_caps_at_28(self) -> None:
        start, end = reports_worker._mom_comparison_range(
            date(2026, 3, 1), date(2026, 3, 31)
        )
        assert (start, end) == (date(2026, 2, 1), date(2026, 2, 28))

    def test_single_day_mtd(self) -> None:
        start, end = reports_worker._mom_comparison_range(
            date(2026, 6, 1), date(2026, 6, 1)
        )
        assert (start, end) == (date(2026, 5, 1), date(2026, 5, 1))


def _all_accessible(db, org_ids):
    return set(org_ids)


class TestGenerateMonthlyReports:
    def test_dispatches_once_per_unique_org(self) -> None:
        db = _make_db({"integrations": [
            {"org_id": ORG_ID}, {"org_id": ORG_ID}, {"org_id": "other-org"},
        ]})
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch(
                "api.services.billing_access.filter_accessible_org_ids",
                side_effect=_all_accessible,
            ),
            patch.object(reports_worker.generate_org_report, "delay") as mock_delay,
        ):
            reports_worker.generate_monthly_reports()
        assert mock_delay.call_count == 2

    def test_no_active_integrations_no_dispatch(self) -> None:
        db = _make_db({"integrations": []})
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch(
                "api.services.billing_access.filter_accessible_org_ids",
                side_effect=_all_accessible,
            ),
            patch.object(reports_worker.generate_org_report, "delay") as mock_delay,
        ):
            reports_worker.generate_monthly_reports()
        mock_delay.assert_not_called()

    def test_lapsed_orgs_excluded_from_fanout(self) -> None:
        # Regression: an org whose trial lapsed must not get a report (or the
        # report-ready email) generated month after month.
        db = _make_db({"integrations": [
            {"org_id": ORG_ID}, {"org_id": "lapsed-org"},
        ]})
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch(
                "api.services.billing_access.filter_accessible_org_ids",
                return_value={ORG_ID},
            ),
            patch.object(reports_worker.generate_org_report, "delay") as mock_delay,
        ):
            reports_worker.generate_monthly_reports()
        assert mock_delay.call_count == 1
        assert mock_delay.call_args.args[0] == ORG_ID


class TestGenerateOrgReportIdempotency:
    def test_skips_when_complete_report_exists(self) -> None:
        db = _make_db({
            "reports": [{"id": "r1", "period_end": "2026-05-31"}],
        })
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch.object(reports_worker, "render_pdf") as mock_render,
        ):
            reports_worker.generate_org_report(ORG_ID, "2026-05-01", "2026-05-31")
        mock_render.assert_not_called()

    def test_partial_does_not_block_fuller_run(self) -> None:
        # Existing row covers through the 10th; the month-end run (through the
        # 31st) must regenerate even without force.
        db = _make_db({
            "reports": [{"id": "r1", "period_end": "2026-05-10"}],
            "daily_cost_summaries": [_SUMMARY_ROW],
            "organizations": [{"name": "Acme"}],
        })
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch.object(reports_worker, "render_pdf", return_value=b"%PDF") as mock_render,
            patch.object(reports_worker, "r2_configured", return_value=False),
        ):
            reports_worker.generate_org_report(ORG_ID, "2026-05-01", "2026-05-31")
        mock_render.assert_called_once()

    def test_force_regenerates_complete_report(self) -> None:
        db = _make_db({
            "reports": [{"id": "r1", "period_end": "2026-05-31"}],
            "daily_cost_summaries": [_SUMMARY_ROW],
            "organizations": [{"name": "Acme"}],
        })
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch.object(reports_worker, "render_pdf", return_value=b"%PDF") as mock_render,
            patch.object(reports_worker, "r2_configured", return_value=False),
        ):
            reports_worker.generate_org_report(
                ORG_ID, "2026-05-01", "2026-05-31", force=True
            )
        mock_render.assert_called_once()

    def test_no_data_skips_generation(self) -> None:
        db = _make_db({"reports": [], "daily_cost_summaries": []})
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch.object(reports_worker, "render_pdf") as mock_render,
        ):
            reports_worker.generate_org_report(ORG_ID, "2026-05-01", "2026-05-31")
        mock_render.assert_not_called()


class TestUploadAndRecord:
    def test_uploads_with_stable_monthly_key(self) -> None:
        db = _make_db({
            "reports": [],
            "daily_cost_summaries": [_SUMMARY_ROW],
            "organizations": [{"name": "Acme"}],
        })
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch.object(reports_worker, "r2_configured", return_value=True),
            patch.object(reports_worker, "upload_pdf") as mock_upload,
        ):
            reports_worker.generate_org_report(ORG_ID, "2026-05-01", "2026-05-31")
        key = mock_upload.call_args.args[0]
        assert key == f"reports/{ORG_ID}/2026-05-01.pdf"

    def test_r2_unconfigured_records_row_without_key(self) -> None:
        # Local dev: report row exists (visible in UI) but has_file is false.
        inserted: list[dict] = []
        db = _make_db({
            "reports": [],
            "daily_cost_summaries": [_SUMMARY_ROW],
            "organizations": [{"name": "Acme"}],
        })

        original_table = db.table.side_effect

        def table(name: str) -> MagicMock:
            chain = original_table(name)
            if name == "reports":
                def capture_insert(row: dict) -> MagicMock:
                    inserted.append(row)
                    return chain
                chain.insert.side_effect = capture_insert
            return chain

        db.table.side_effect = table
        with (
            patch.object(reports_worker, "_get_supabase", return_value=db),
            patch.object(reports_worker, "r2_configured", return_value=False),
            patch.object(reports_worker, "upload_pdf") as mock_upload,
        ):
            reports_worker.generate_org_report(ORG_ID, "2026-05-01", "2026-05-31")
        mock_upload.assert_not_called()
        assert len(inserted) == 1
        assert inserted[0]["r2_object_key"] is None


class TestReportEmail:
    def test_email_sent_with_app_link(self) -> None:
        db = _make_db({})
        with (
            patch.object(reports_worker, "_get_org_admin_email", return_value="cfo@acme.com"),
            patch.object(reports_worker.resend.Emails, "send") as mock_send,
        ):
            reports_worker._send_report_email(db, ORG_ID, date(2026, 5, 1))
        payload = mock_send.call_args.args[0]
        assert payload["to"] == ["cfo@acme.com"]
        assert "May 2026" in payload["subject"]
        assert "/reports" in payload["html"]

    def test_no_admin_email_returns_quietly(self) -> None:
        db = _make_db({})
        with (
            patch.object(reports_worker, "_get_org_admin_email", return_value=None),
            patch.object(reports_worker.resend.Emails, "send") as mock_send,
        ):
            reports_worker._send_report_email(db, ORG_ID, date(2026, 5, 1))
        mock_send.assert_not_called()

    def test_email_failure_does_not_raise(self) -> None:
        db = _make_db({})
        with (
            patch.object(reports_worker, "_get_org_admin_email", return_value="cfo@acme.com"),
            patch.object(
                reports_worker.resend.Emails, "send", side_effect=RuntimeError("resend down")
            ),
        ):
            reports_worker._send_report_email(db, ORG_ID, date(2026, 5, 1))  # must not raise
