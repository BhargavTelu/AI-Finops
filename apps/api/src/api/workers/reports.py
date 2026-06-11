"""
Monthly CFO PDF report generation (Phase 1 / FR-22).

Beat: generate_monthly_reports runs on the 1st at 06:00 UTC and fans out one
generate_org_report per org with an active integration, covering the previous
calendar month. The /reports/generate route dispatches the same task for the
current month-to-date with force=True (sales-demo path).

Idempotency: one reports row per (org, type, period_start). A later run only
regenerates when it covers MORE days (period_end advanced) or force=True, so
a month-to-date partial never blocks the full month-end report.
"""

import calendar
from datetime import UTC, date, datetime, timedelta

from celery import shared_task
import resend
import structlog
from supabase import create_client

from api.config import settings
from api.services.db import fetch_all_pages
from api.services.report_builder import build_report_data
from api.services.report_pdf import render_pdf
from api.services.storage import is_configured as r2_configured
from api.services.storage import upload_pdf
from api.workers.notifications import _get_org_admin_email

log = structlog.get_logger()

_REPORT_TYPE = "cfo_pdf"


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _previous_month_range(today: date) -> tuple[date, date]:
    period_end = today.replace(day=1) - timedelta(days=1)
    return period_end.replace(day=1), period_end


def _mom_comparison_range(start: date, end: date) -> tuple[date, date]:
    """
    Previous-month window covering the SAME number of elapsed days.

    A month-to-date report (11 days in) must compare against the first 11
    days of last month - comparing against the full prior month makes the
    MoM headline wildly misleading (e.g. -97% mid-month). Capped at the
    previous month's length, so a complete month compares to the complete
    previous month.
    """
    prev_start, _ = _previous_month_range(start)
    days_elapsed = (end - start).days + 1
    prev_month_days = calendar.monthrange(prev_start.year, prev_start.month)[1]
    return prev_start, prev_start + timedelta(days=min(days_elapsed, prev_month_days) - 1)


@shared_task
def generate_monthly_reports() -> None:
    """
    Fan-out: one report task per org with an active integration AND access
    (active subscription or running trial). Lapsed orgs are skipped entirely -
    no generation cost, and no report-ready email landing in the inbox of
    someone who churned months ago.
    """
    from api.services.billing_access import filter_accessible_org_ids

    db = _get_supabase()
    today = datetime.now(UTC).date()
    period_start, period_end = _previous_month_range(today)

    result = db.table("integrations").select("org_id").eq("status", "active").execute()
    candidates = sorted({row["org_id"] for row in result.data})
    org_ids = sorted(filter_accessible_org_ids(db, candidates))
    if len(org_ids) < len(candidates):
        log.info("monthly_reports_skipped_lapsed", count=len(candidates) - len(org_ids))
    for org_id in org_ids:
        generate_org_report.delay(
            org_id,
            period_start.isoformat(),
            period_end.isoformat(),
            force=False,
            send_email=True,
        )
    log.info("monthly_reports_dispatched", count=len(org_ids), period=period_start.isoformat())


def _fetch_summaries(db, org_id: str, start: date, end: date) -> list[dict]:
    return fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select(
            "total_cost_usd, total_requests, total_tokens, "
            "provider, model, feature_tag, team_tag, customer_tag"
        )
        .eq("org_id", org_id)
        .gte("day", start.isoformat())
        .lte("day", end.isoformat())
    )


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def generate_org_report(  # type: ignore[misc]
    self,
    org_id: str,
    period_start: str,
    period_end: str,
    force: bool = False,
    send_email: bool = False,
) -> None:
    db = _get_supabase()
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)

    existing_result = (
        db.table("reports")
        .select("id, period_end")
        .eq("org_id", org_id)
        .eq("type", _REPORT_TYPE)
        .eq("period_start", period_start)
        .limit(1)
        .execute()
    )
    existing = existing_result.data[0] if existing_result.data else None
    if existing and not force and date.fromisoformat(existing["period_end"]) >= end:
        log.info("report_already_generated", org_id=org_id, period_start=period_start)
        return

    current_rows = _fetch_summaries(db, org_id, start, end)
    if not current_rows:
        log.info("report_no_data", org_id=org_id, period_start=period_start)
        return

    prev_start, prev_end = _mom_comparison_range(start, end)
    prev_rows = _fetch_summaries(db, org_id, prev_start, prev_end)

    anomaly_rows = (
        db.table("anomalies")
        .select("detected_at, scope_value, baseline_usd, actual_usd, spike_pct, severity")
        .eq("org_id", org_id)
        .gte("detected_at", start.isoformat())
        .lt("detected_at", (end + timedelta(days=1)).isoformat())
        .execute()
    ).data

    rec_rows = (
        db.table("recommendations")
        .select("projected_savings_usd")
        .eq("org_id", org_id)
        .eq("status", "applied")
        .gte("resolved_at", start.isoformat())
        .lt("resolved_at", (end + timedelta(days=1)).isoformat())
        .execute()
    ).data

    org_result = (
        db.table("organizations").select("name").eq("id", org_id).limit(1).execute()
    )
    org_name = org_result.data[0]["name"] if org_result.data else "Your organization"

    data = build_report_data(
        org_name=org_name,
        period_start=start,
        period_end=end,
        generated_on=datetime.now(UTC).date(),
        current_rows=current_rows,
        prev_month_rows=prev_rows,
        anomaly_rows=anomaly_rows,
        applied_rec_rows=rec_rows,
    )
    pdf_bytes = render_pdf(data)

    # Stable key per month: a fuller regeneration overwrites the partial.
    object_key: str | None = f"reports/{org_id}/{period_start}.pdf"
    if r2_configured():
        try:
            upload_pdf(object_key, pdf_bytes)
        except ValueError as exc:
            log.error("report_upload_failed", org_id=org_id, error=str(exc))
            raise self.retry(exc=exc) from exc
    else:
        # Local dev without R2 creds: record the report, mark file unavailable.
        log.warning("r2_not_configured_skipping_upload", org_id=org_id)
        object_key = None

    now_iso = datetime.now(UTC).isoformat()
    row = {
        "org_id": org_id,
        "type": _REPORT_TYPE,
        "period_start": period_start,
        "period_end": period_end,
        "r2_object_key": object_key,
        "generated_at": now_iso,
    }
    if existing:
        db.table("reports").update(row).eq("id", existing["id"]).execute()
    else:
        db.table("reports").insert(row).execute()
    log.info("report_generated", org_id=org_id, period_start=period_start, partial=data.is_partial)

    if send_email:
        _send_report_email(db, org_id, start)


def _report_email_html(month_label: str, reports_url: str) -> str:
    return f"""
    <div style="font-family: Inter, Arial, sans-serif; max-width: 560px; margin: 0 auto;">
      <h2 style="color: #1f3a5f;">Your {month_label} LLM spend report is ready</h2>
      <p style="color: #334155; line-height: 1.5;">
        The monthly cost report for your organization has been generated -
        spend by provider, model, feature, team, and customer, plus anomalies
        and realized savings. Finance-ready, no editing needed.
      </p>
      <p style="margin: 24px 0;">
        <a href="{reports_url}"
           style="background: #1f3a5f; color: #ffffff; padding: 10px 18px;
                  border-radius: 8px; text-decoration: none; font-weight: 600;">
          Download report
        </a>
      </p>
      <p style="color: #64748b; font-size: 12px;">
        Sent by SpendOps AI on the 1st of each month.
      </p>
    </div>
    """


def _send_report_email(db, org_id: str, period_start: date) -> None:
    """Best-effort: a failed email never fails (or retries) report generation."""
    to_email = _get_org_admin_email(db, org_id)
    if not to_email:
        log.warning("report_email_no_admin", org_id=org_id)
        return

    month_label = f"{period_start:%B %Y}"
    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {
                "from": settings.from_email,
                "to": [to_email],
                "subject": f"Your {month_label} LLM spend report is ready",
                "html": _report_email_html(month_label, f"{settings.app_url}/reports"),
            }
        )
        log.info("report_email_sent", org_id=org_id, period=month_label)
    except Exception as exc:
        log.warning("report_email_failed", org_id=org_id, error=str(exc))
