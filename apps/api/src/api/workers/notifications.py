"""
Notification workers:
  send_daily_digests  — Slack digest at 09:00 UTC (Group C)
  send_anomaly_alert  — real-time Slack alert on new anomaly (Group C)
  send_budget_alert   — email at alert_at_pct / 100% of budget (Group B)
"""

from decimal import Decimal

import resend
import structlog
from celery import shared_task
from supabase import create_client

from api.config import settings

log = structlog.get_logger()


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _get_org_admin_email(db, org_id: str) -> str | None:
    """Return the email of the first (oldest) admin member of the org."""
    members = (
        db.table("organization_members")
        .select("user_id")
        .eq("org_id", org_id)
        .eq("role", "admin")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not members.data:
        return None

    user_id = members.data[0]["user_id"]
    user = (
        db.table("users")
        .select("email")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return user.data[0]["email"] if user.data else None


def _scope_label(scope_type: str, scope_value: str | None) -> str:
    """Human-readable scope label for email templates."""
    if scope_type == "global":
        return "all providers (global)"
    labels = {
        "provider": "provider",
        "model": "model",
        "feature_tag": "feature",
        "team_tag": "team",
        "customer_tag": "customer",
        "env_tag": "environment",
    }
    kind = labels.get(scope_type, scope_type)
    return f"{kind}: {scope_value}"


def _warning_email_html(scope_label: str, limit_usd: Decimal, spend_usd: Decimal, pct: int) -> str:
    return f"""
<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#1a1a1a">
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:600">
    Budget warning: {pct}% used
  </h2>
  <p style="margin:0 0 24px;font-size:14px;color:#555">
    You've used <strong>{pct}%</strong> of your monthly budget for <strong>{scope_label}</strong>.
  </p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr style="border-bottom:1px solid #e5e7eb">
      <td style="padding:10px 0;color:#888">Scope</td>
      <td style="padding:10px 0;text-align:right;font-weight:500">{scope_label}</td>
    </tr>
    <tr style="border-bottom:1px solid #e5e7eb">
      <td style="padding:10px 0;color:#888">Monthly limit</td>
      <td style="padding:10px 0;text-align:right;font-weight:500">${limit_usd:,.2f}</td>
    </tr>
    <tr style="border-bottom:1px solid #e5e7eb">
      <td style="padding:10px 0;color:#888">MTD spend</td>
      <td style="padding:10px 0;text-align:right;font-weight:500">${spend_usd:,.2f}</td>
    </tr>
    <tr>
      <td style="padding:10px 0;color:#888">% used</td>
      <td style="padding:10px 0;text-align:right;font-weight:600;color:#d97706">{pct}%</td>
    </tr>
  </table>
  <p style="margin:24px 0 0;font-size:13px;color:#888">
    Review your spend in the AI FinOps dashboard. If this is unexpected, check for anomalies.
  </p>
</div>
"""


def _exceeded_email_html(scope_label: str, limit_usd: Decimal, spend_usd: Decimal, pct: int) -> str:
    return f"""
<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#1a1a1a">
  <h2 style="margin:0 0 8px;font-size:20px;font-weight:600;color:#dc2626">
    Budget exceeded
  </h2>
  <p style="margin:0 0 24px;font-size:14px;color:#555">
    Your monthly budget for <strong>{scope_label}</strong> has been exceeded
    ({pct}% of limit used).
  </p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr style="border-bottom:1px solid #e5e7eb">
      <td style="padding:10px 0;color:#888">Scope</td>
      <td style="padding:10px 0;text-align:right;font-weight:500">{scope_label}</td>
    </tr>
    <tr style="border-bottom:1px solid #e5e7eb">
      <td style="padding:10px 0;color:#888">Monthly limit</td>
      <td style="padding:10px 0;text-align:right;font-weight:500">${limit_usd:,.2f}</td>
    </tr>
    <tr style="border-bottom:1px solid #e5e7eb">
      <td style="padding:10px 0;color:#888">MTD spend</td>
      <td style="padding:10px 0;text-align:right;font-weight:500">${spend_usd:,.2f}</td>
    </tr>
    <tr>
      <td style="padding:10px 0;color:#888">% used</td>
      <td style="padding:10px 0;text-align:right;font-weight:600;color:#dc2626">{pct}%</td>
    </tr>
  </table>
  <p style="margin:24px 0 0;font-size:13px;color:#888">
    Review your spend in the AI FinOps dashboard and consider increasing your limit or
    reducing usage.
  </p>
</div>
"""


@shared_task
def send_daily_digests() -> None:
    """
    Enqueue send_slack_digest for every org with Slack connected.
    Sent at 09:00 UTC; per-org timezone adjustment is a V1 improvement.
    """
    raise NotImplementedError


@shared_task(bind=True, max_retries=2)
def send_slack_digest(self, org_id: str) -> None:  # type: ignore[misc]
    """
    Build digest payload and call chat.postMessage.
    Payload: yesterday spend, 7d avg, MoM delta, top 3 cost drivers, open anomalies.
    Records sent_at for idempotency.
    """
    raise NotImplementedError


@shared_task(bind=True, max_retries=3)
def send_anomaly_alert(self, anomaly_id: str) -> None:  # type: ignore[misc]
    """Send real-time Slack alert when a new anomaly is inserted."""
    raise NotImplementedError


@shared_task(bind=True, max_retries=3)
def send_budget_alert(self, budget_id: str, pct: int, org_id: str) -> None:  # type: ignore[misc]
    """
    Send email via Resend when spend crosses alert_at_pct (warning) or 100% (exceeded).
    The notified_*_at guard in budget_checks.py ensures this fires at most once per
    threshold per calendar month — this task is idempotent by design.
    """
    db = _get_supabase()

    budget_result = (
        db.table("budgets")
        .select("id, org_id, scope_type, scope_value, monthly_limit, alert_at_pct")
        .eq("id", budget_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not budget_result.data:
        log.warning("budget_alert_budget_not_found", budget_id=budget_id, org_id=org_id)
        return

    budget = budget_result.data[0]
    monthly_limit = Decimal(str(budget["monthly_limit"]))

    # Compute current MTD spend to include in the email
    from api.workers.budget_checks import _compute_scope_spend  # local import avoids circular dep

    mtd_spend = _compute_scope_spend(db, org_id, budget["scope_type"], budget.get("scope_value"))

    to_email = _get_org_admin_email(db, org_id)
    if not to_email:
        log.warning("budget_alert_no_admin_email", org_id=org_id, budget_id=budget_id)
        return

    scope_label = _scope_label(budget["scope_type"], budget.get("scope_value"))
    is_exceeded = pct >= 100

    subject = (
        f"Budget exceeded: {scope_label} at {pct}% of limit"
        if is_exceeded
        else f"Budget alert: {pct}% used for {scope_label}"
    )
    html = (
        _exceeded_email_html(scope_label, monthly_limit, mtd_spend, pct)
        if is_exceeded
        else _warning_email_html(scope_label, monthly_limit, mtd_spend, pct)
    )

    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {
                "from": settings.from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            }
        )
        log.info(
            "budget_alert_sent",
            org_id=org_id,
            budget_id=budget_id,
            pct=pct,
            to=to_email,
        )
    except Exception as exc:
        log.error("budget_alert_send_failed", org_id=org_id, budget_id=budget_id, error=str(exc))
        raise self.retry(exc=exc)
