"""
Notification workers:
  send_daily_digests  - Slack digest at 09:00 UTC (Group C)
  send_anomaly_alert  - real-time Slack alert on new anomaly (Group C)
  send_budget_alert   - email at alert_at_pct / 100% of budget (Group B)
                        + Slack (Group C)
"""

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from celery import shared_task
import resend
import structlog
from supabase import create_client

from api.config import settings
from api.services.db import fetch_all_pages
from api.services.encryption import EncryptionService
from api.services.slack_client import post_message

log = structlog.get_logger()

_SEVERITY_EMOJI = {
    "low": ":warning:",
    "medium": ":large_orange_diamond:",
    "high": ":rotating_light:",
}


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


def _get_slack_channel(db, org_id: str) -> tuple[str, str, bool] | None:
    """
    Return (bot_token, channel_id, alerts_muted) for the org's Slack integration.
    Returns None if no Slack integration is connected.
    Decrypts the bot token using EncryptionService.
    """
    result = (
        db.table("slack_integrations")
        .select("bot_token_enc, channel_id, alerts_muted")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    row = result.data[0]
    raw_hex: str = row["bot_token_enc"]
    try:
        cipher = EncryptionService(settings.encryption_key)
        # Supabase returns bytea as \x<hex>; strip prefix before decoding.
        blob = bytes.fromhex(raw_hex.lstrip("\\x"))
        bot_token = cipher.decrypt(blob).decode()
    except Exception as exc:
        log.error("slack_token_decrypt_failed", org_id=org_id, error=str(exc))
        return None

    return bot_token, row["channel_id"], bool(row.get("alerts_muted", False))


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
    Review your spend in the SpendOps AI dashboard. If this is unexpected, check for anomalies.
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
    Review your spend in the SpendOps AI dashboard and consider increasing your limit or
    reducing usage.
  </p>
</div>
"""


def _anomaly_slack_blocks(anomaly: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Slack Block Kit payload for an anomaly alert."""
    severity: str = anomaly.get("severity", "low")
    emoji = _SEVERITY_EMOJI.get(severity, ":warning:")
    scope_value: str = anomaly.get("scope_value", "unknown")
    spike_pct: int = anomaly.get("spike_pct", 0)
    baseline: str = f"${Decimal(str(anomaly['baseline_usd'])):,.2f}"
    actual: str = f"${Decimal(str(anomaly['actual_usd'])):,.2f}"

    context = anomaly.get("context") or {}
    tag_parts = [
        f"Team: {context['team_tag']}" for _ in [1] if context.get("team_tag")
    ] + [
        f"Feature: {context['feature_tag']}" for _ in [1] if context.get("feature_tag")
    ] + [
        f"Customer: {context['customer_tag']}" for _ in [1] if context.get("customer_tag")
    ]

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *Cost Anomaly Detected* - `{scope_value}`",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity*\n{severity.capitalize()}"},
                {"type": "mrkdwn", "text": f"*Spike*\n+{spike_pct}% above baseline"},
                {"type": "mrkdwn", "text": f"*Baseline/day*\n{baseline}"},
                {"type": "mrkdwn", "text": f"*Yesterday*\n{actual}"},
            ],
        },
    ]

    if tag_parts:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " · ".join(tag_parts)}],
            }
        )

    return blocks


def _budget_slack_blocks(
    scope_label: str,
    limit_usd: Decimal,
    spend_usd: Decimal,
    pct: int,
    is_exceeded: bool,
) -> list[dict[str, Any]]:
    """Build Slack Block Kit payload for a budget alert."""
    if is_exceeded:
        header = f":red_circle: *Budget Exceeded* - {pct}% of limit used"
    else:
        header = f":warning: *Budget Warning* - {pct}% of limit used"

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Scope*\n{scope_label}"},
                {"type": "mrkdwn", "text": f"*Monthly Limit*\n${limit_usd:,.2f}"},
                {"type": "mrkdwn", "text": f"*MTD Spend*\n${spend_usd:,.2f}"},
                {"type": "mrkdwn", "text": f"*% Used*\n{pct}%"},
            ],
        },
    ]


def _fetch_digest_data(db, org_id: str, yesterday: date) -> dict[str, Any]:
    """
    Collect metrics for the daily digest from daily_cost_summaries and anomalies.
    Returns: yesterday_usd, avg_7d_usd, mom_pct (None if no prior data),
             top_drivers (list of {label, usd}), open_anomaly_count.
    """
    yesterday_str = yesterday.isoformat()
    week_ago_str = (yesterday - timedelta(days=6)).isoformat()

    # 7 days of data (includes yesterday) - drives three metrics at once.
    # All digest reads are paged: an unpaged select is silently truncated at
    # the PostgREST max-rows cap and skews every number in the digest.
    week_rows: list[dict[str, Any]] = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("day, model, total_cost_usd")
        .eq("org_id", org_id)
        .gte("day", week_ago_str)
        .lte("day", yesterday_str)
    )

    yesterday_rows = [r for r in week_rows if r["day"][:10] == yesterday_str]
    yesterday_usd = sum(Decimal(str(r["total_cost_usd"])) for r in yesterday_rows)

    driver_by_model: dict[str, Decimal] = {}
    for r in yesterday_rows:
        model_name = r.get("model") or "unknown"
        driver_by_model[model_name] = (
            driver_by_model.get(model_name, Decimal("0")) + Decimal(str(r["total_cost_usd"]))
        )
    top_drivers = sorted(driver_by_model.items(), key=lambda kv: kv[1], reverse=True)[:3]

    # Divide by 7 regardless of how many days have data (sparse = cheaper than expected).
    week_total = sum(Decimal(str(r["total_cost_usd"])) for r in week_rows)
    avg_7d_usd = week_total / 7

    # This-month MTD (month start → yesterday).
    first_of_month = yesterday.replace(day=1)
    mtd_rows: list[dict[str, Any]] = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("total_cost_usd")
        .eq("org_id", org_id)
        .gte("day", first_of_month.isoformat())
        .lte("day", yesterday_str)
    )
    this_mtd = sum(Decimal(str(r["total_cost_usd"])) for r in mtd_rows)

    # Previous month, same day range (handles month-length differences).
    lm_year = yesterday.year if yesterday.month > 1 else yesterday.year - 1
    lm_month = yesterday.month - 1 if yesterday.month > 1 else 12
    lm_max_day = calendar.monthrange(lm_year, lm_month)[1]
    lm_end = date(lm_year, lm_month, min(yesterday.day, lm_max_day))
    lm_start = date(lm_year, lm_month, 1)

    lm_rows: list[dict[str, Any]] = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("total_cost_usd")
        .eq("org_id", org_id)
        .gte("day", lm_start.isoformat())
        .lte("day", lm_end.isoformat())
    )
    last_mtd = sum(Decimal(str(r["total_cost_usd"])) for r in lm_rows)

    mom_pct: int | None = None
    if last_mtd > 0:
        mom_pct = int(((this_mtd - last_mtd) / last_mtd * 100).to_integral_value())

    anomaly_count = len(
        db.table("anomalies")
        .select("id")
        .eq("org_id", org_id)
        .eq("status", "open")
        .execute()
        .data
    )

    return {
        "yesterday_usd": yesterday_usd,
        "avg_7d_usd": avg_7d_usd,
        "mom_pct": mom_pct,
        "top_drivers": [{"label": model, "usd": usd} for model, usd in top_drivers],
        "open_anomaly_count": anomaly_count,
    }


def _digest_slack_blocks(
    digest_date: date,
    yesterday_usd: Decimal,
    avg_7d_usd: Decimal,
    mom_pct: int | None,
    top_drivers: list[dict[str, Any]],
    open_anomaly_count: int,
) -> list[dict[str, Any]]:
    """Build Slack Block Kit payload for the daily cost digest."""
    # Cross-platform date string (%-d is Linux-only).
    date_str = f"{digest_date.strftime('%A, %b')} {digest_date.day}"

    if mom_pct is None:
        mom_text = "No prior month data"
    elif mom_pct > 0:
        mom_text = f"+{mom_pct}% vs last month"
    elif mom_pct < 0:
        mom_text = f"{mom_pct}% vs last month"
    else:
        mom_text = "Flat vs last month"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"AI Cost Digest - {date_str}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Yesterday*\n${yesterday_usd:,.2f}"},
                {"type": "mrkdwn", "text": f"*7-day avg*\n${avg_7d_usd:,.2f}/day"},
                {"type": "mrkdwn", "text": f"*Month-over-month*\n{mom_text}"},
                {"type": "mrkdwn", "text": f"*Open anomalies*\n{open_anomaly_count}"},
            ],
        },
    ]

    if top_drivers:
        driver_lines = "\n".join(
            f"• `{d['label']}` - ${d['usd']:,.2f}" for d in top_drivers
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top cost drivers (yesterday)*\n{driver_lines}",
                },
            }
        )

    return blocks


# ── Celery tasks ───────────────────────────────────────────────────────────────

@shared_task
def send_daily_digests() -> None:
    """
    Enqueue send_slack_digest for every org with Slack connected.
    Sent at 09:00 UTC; per-org timezone adjustment is a V1 improvement.
    """
    db = _get_supabase()
    result = db.table("slack_integrations").select("org_id").execute()
    org_ids = [row["org_id"] for row in result.data]
    for org_id in org_ids:
        send_slack_digest.delay(org_id)
    log.info("daily_digests_dispatched", count=len(org_ids))


@shared_task(bind=True, max_retries=2)
def send_slack_digest(self, org_id: str) -> None:  # type: ignore[misc]
    """
    Build digest payload and call chat.postMessage.
    Payload: yesterday spend, 7d avg, MoM delta, top 3 cost drivers, open anomalies.
    Records sent_at for idempotency.
    """
    db = _get_supabase()
    yesterday = datetime.now(UTC).date() - timedelta(days=1)

    # Skip if already sent for this date (Celery retry guard).
    existing = (
        db.table("slack_digests")
        .select("id")
        .eq("org_id", org_id)
        .eq("digest_date", yesterday.isoformat())
        .limit(1)
        .execute()
    )
    if existing.data:
        log.info("digest_already_sent", org_id=org_id, digest_date=yesterday.isoformat())
        return

    slack = _get_slack_channel(db, org_id)
    if slack is None:
        return

    bot_token, channel_id, _ = slack  # digest is not an alert - never suppressed by mute
    data = _fetch_digest_data(db, org_id, yesterday)
    blocks = _digest_slack_blocks(
        digest_date=yesterday,
        yesterday_usd=data["yesterday_usd"],
        avg_7d_usd=data["avg_7d_usd"],
        mom_pct=data["mom_pct"],
        top_drivers=data["top_drivers"],
        open_anomaly_count=data["open_anomaly_count"],
    )
    fallback = (
        f"AI Cost Digest for {yesterday.isoformat()}: "
        f"${data['yesterday_usd']:,.2f} yesterday, "
        f"{data['open_anomaly_count']} open anomalies"
    )

    try:
        post_message(bot_token, channel_id, blocks, fallback)
    except ValueError as exc:
        log.error("digest_send_failed", org_id=org_id, error=str(exc))
        raise self.retry(exc=exc)

    # Record successful send; failure here is non-fatal - digest is already posted.
    try:
        db.table("slack_digests").insert(
            {
                "org_id": org_id,
                "digest_date": yesterday.isoformat(),
                "channel_id": channel_id,
            }
        ).execute()
    except Exception as exc:
        log.warning("digest_record_failed", org_id=org_id, error=str(exc))

    log.info(
        "digest_sent",
        org_id=org_id,
        digest_date=yesterday.isoformat(),
        channel_id=channel_id,
    )


@shared_task(bind=True, max_retries=3)
def send_anomaly_alert(self, anomaly_id: str) -> None:  # type: ignore[misc]
    """
    Post a real-time Slack alert when a new anomaly with severity ≥ medium is
    inserted. Called directly from anomaly_detection.detect_org for qualifying
    anomalies - the wire is live; only this task body was a stub.
    """
    db = _get_supabase()

    anomaly_result = (
        db.table("anomalies")
        .select("id, org_id, scope_kind, scope_value, baseline_usd, actual_usd, spike_pct, severity, context")
        .eq("id", anomaly_id)
        .limit(1)
        .execute()
    )
    if not anomaly_result.data:
        log.warning("anomaly_alert_not_found", anomaly_id=anomaly_id)
        return

    anomaly = anomaly_result.data[0]
    org_id: str = anomaly["org_id"]

    slack = _get_slack_channel(db, org_id)
    if slack is None:
        # Org hasn't connected Slack - silently skip (common case pre-install).
        log.debug("anomaly_alert_no_slack", org_id=org_id, anomaly_id=anomaly_id)
        return

    bot_token, channel_id, alerts_muted = slack
    if alerts_muted:
        log.info("anomaly_alert_muted", org_id=org_id, anomaly_id=anomaly_id)
        return

    blocks = _anomaly_slack_blocks(anomaly)
    severity = anomaly.get("severity", "low")
    fallback = (
        f"Cost anomaly on {anomaly.get('scope_value', 'unknown')}: "
        f"+{anomaly.get('spike_pct', 0)}% spike ({severity} severity)"
    )

    try:
        post_message(bot_token, channel_id, blocks, fallback)
    except ValueError as exc:
        log.error("anomaly_alert_send_failed", org_id=org_id, anomaly_id=anomaly_id, error=str(exc))
        raise self.retry(exc=exc)

    log.info(
        "anomaly_alert_sent",
        org_id=org_id,
        anomaly_id=anomaly_id,
        severity=severity,
        channel_id=channel_id,
    )

    # Record when the Slack alert was sent - non-fatal if the DB write fails.
    # The alert was already delivered; this is audit data only.
    try:
        db.table("anomalies").update(
            {"notified_at": datetime.now(UTC).isoformat()}
        ).eq("id", anomaly_id).execute()
    except Exception as exc:
        log.warning("anomaly_notified_at_update_failed", anomaly_id=anomaly_id, error=str(exc))


@shared_task(bind=True, max_retries=3)
def send_budget_alert(self, budget_id: str, pct: int, org_id: str) -> None:  # type: ignore[misc]
    """
    Send email via Resend when spend crosses alert_at_pct (warning) or 100% (exceeded).
    Also posts to Slack if the org has a connected integration (best-effort - email
    is not retried on Slack failure).
    The notified_*_at guard in budget_checks.py ensures this fires at most once per
    threshold per calendar month - this task is idempotent by design.
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
        # No recipient email in the log line - hard rule #4: no PII in logs.
        log.info(
            "budget_alert_sent",
            org_id=org_id,
            budget_id=budget_id,
            pct=pct,
        )
    except Exception as exc:
        log.error("budget_alert_send_failed", org_id=org_id, budget_id=budget_id, error=str(exc))
        raise self.retry(exc=exc)

    # ── Slack notification (best-effort - failure does not retry the email) ───
    slack = _get_slack_channel(db, org_id)
    if slack is None:
        return

    bot_token, channel_id, alerts_muted = slack
    if alerts_muted:
        log.info("budget_slack_alert_muted", org_id=org_id, budget_id=budget_id)
        return

    blocks = _budget_slack_blocks(scope_label, monthly_limit, mtd_spend, pct, is_exceeded)
    fallback = f"Budget {'exceeded' if is_exceeded else 'warning'}: {scope_label} at {pct}% of ${monthly_limit:,.2f}/mo"

    try:
        post_message(bot_token, channel_id, blocks, fallback)
        log.info(
            "budget_slack_alert_sent",
            org_id=org_id,
            budget_id=budget_id,
            pct=pct,
            channel_id=channel_id,
        )
    except Exception as exc:
        # Non-fatal - email already sent; Slack failure is logged but not retried.
        log.warning("budget_slack_alert_failed", org_id=org_id, budget_id=budget_id, error=str(exc))


# ── Weekly email digest (Phase 3) ──────────────────────────────────────────────


def _weekly_email_html(data: dict[str, Any]) -> str:
    """Branded weekly summary. Reuses the Slack digest metrics."""
    week_total = data["avg_7d_usd"] * 7
    mom = data.get("mom_pct")
    if mom is not None:
        mom_color = "#b93232" if mom > 0 else "#16825d"
        mom_line = f'<span style="color: {mom_color};">{mom:+d}% vs last month</span>'
    else:
        mom_line = "no prior-month baseline yet"
    drivers = data.get("top_drivers") or []
    driver_rows = "".join(
        f'<tr><td style="padding: 4px 12px 4px 0; color: #334155;">{d["label"]}</td>'
        f'<td style="padding: 4px 0; color: #1a1a1a; text-align: right;">'
        f"${d['usd']:,.2f}</td></tr>"
        for d in drivers
    )
    drivers_block = (
        f"<table style=\"font-size: 13px; margin: 4px 0 0 0;\">{driver_rows}</table>"
        if driver_rows
        else "<p style=\"color: #64748b; font-size: 13px;\">No spend recorded yesterday.</p>"
    )
    anomaly_count = data.get("open_anomaly_count", 0)
    anomaly_line = (
        f'<strong style="color: #b93232;">{anomaly_count} open</strong>'
        if anomaly_count
        else "none open"
    )
    avg_str = f"${data['avg_7d_usd']:,.2f}"

    return f"""
    <div style="font-family: Inter, Arial, sans-serif; max-width: 560px; margin: 0 auto;">
      <h2 style="color: #1f3a5f;">Your week in LLM spend</h2>
      <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
        <tr>
          <td style="padding: 8px 0; color: #64748b;">Last 7 days</td>
          <td style="padding: 8px 0; text-align: right; font-weight: 600;">${week_total:,.2f}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #64748b;">Daily average</td>
          <td style="padding: 8px 0; text-align: right; font-weight: 600;">{avg_str}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #64748b;">Month to date</td>
          <td style="padding: 8px 0; text-align: right;">{mom_line}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #64748b;">Cost anomalies</td>
          <td style="padding: 8px 0; text-align: right;">{anomaly_line}</td>
        </tr>
      </table>
      <h3 style="color: #1f3a5f; font-size: 14px; margin-top: 20px;">
        Top models (most recent day)</h3>
      {drivers_block}
      <p style="margin: 24px 0;">
        <a href="{settings.app_url}/dashboard"
           style="background: #1f3a5f; color: #ffffff; padding: 10px 18px;
                  border-radius: 8px; text-decoration: none; font-weight: 600;">
          Open dashboard
        </a>
      </p>
      <p style="color: #64748b; font-size: 12px;">
        Sent every Monday by SpendOps AI. Connect Slack for daily digests instead.
        Reply "unsubscribe" to stop these emails.
      </p>
    </div>
    """


@shared_task
def send_weekly_email_digests() -> None:
    """
    Fan-out (Mondays 09:00 UTC): one weekly email per org that has an active
    integration, has NOT connected Slack (Slack-first - those orgs already get
    the daily digest), and has not opted out.
    """
    db = _get_supabase()

    active = db.table("integrations").select("org_id").eq("status", "active").execute()
    candidates = {row["org_id"] for row in active.data}

    slack_rows = db.table("slack_integrations").select("org_id").execute()
    candidates -= {row["org_id"] for row in slack_rows.data}

    if not candidates:
        log.info("weekly_email_digests_none")
        return

    opted_in = db.table("organizations").select("id").eq("email_digest_opt_out", False).execute()
    recipients = sorted(candidates & {row["id"] for row in opted_in.data})

    for org_id in recipients:
        send_weekly_email_digest.delay(org_id)
    log.info("weekly_email_digests_dispatched", count=len(recipients))


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_weekly_email_digest(self, org_id: str) -> None:  # type: ignore[misc]
    """Send the weekly summary email to the org admin. Retries on Resend failure."""
    db = _get_supabase()

    to_email = _get_org_admin_email(db, org_id)
    if not to_email:
        log.warning("weekly_digest_no_admin_email", org_id=org_id)
        return

    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    data = _fetch_digest_data(db, org_id, yesterday)

    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {
                "from": settings.from_email,
                "to": [to_email],
                "subject": "Your week in LLM spend",
                "html": _weekly_email_html(data),
            }
        )
        log.info("weekly_digest_sent", org_id=org_id)
    except Exception as exc:
        log.error("weekly_digest_send_failed", org_id=org_id, error=str(exc))
        raise self.retry(exc=exc) from exc
