"""
Nightly budget checks — runs at 02:00 UTC (after aggregation + anomaly detection).
Algorithm: compare MTD spend per scope against monthly_limit.
Fires email alert at alert_at_pct (default 80%) and 100%.
Idempotent: notified_80_at / notified_100_at guard prevents re-alerts within the same calendar month.
"""

from datetime import datetime, timezone
from decimal import Decimal

import structlog
from celery import shared_task
from supabase import create_client

from api.config import settings
from api.workers.notifications import send_budget_alert

log = structlog.get_logger()


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _mtd_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return today.replace(day=1).isoformat(), today.isoformat()


def _compute_scope_spend(db, org_id: str, scope_type: str, scope_value: str | None) -> Decimal:
    """Sum total_cost_usd from daily_cost_summaries for the current calendar month, filtered by scope."""
    first_day, today = _mtd_range()
    q = (
        db.table("daily_cost_summaries")
        .select("total_cost_usd")
        .eq("org_id", org_id)
        .gte("day", first_day)
        .lte("day", today)
    )
    if scope_type == "provider":
        q = q.eq("provider", scope_value)
    elif scope_type == "model":
        q = q.eq("model", scope_value)
    elif scope_type == "feature_tag":
        q = q.eq("feature_tag", scope_value)
    elif scope_type == "team_tag":
        q = q.eq("team_tag", scope_value)
    elif scope_type == "customer_tag":
        q = q.eq("customer_tag", scope_value)
    elif scope_type == "env_tag":
        q = q.eq("env_tag", scope_value)
    # 'global' → no extra filter

    result = q.execute()
    return sum(Decimal(str(row["total_cost_usd"])) for row in result.data)


def _same_calendar_month(ts_str: str | None) -> bool:
    """Return True if the given ISO timestamp falls in the current UTC calendar month."""
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return ts.year == now.year and ts.month == now.month
    except ValueError:
        return False


@shared_task
def check_all_orgs() -> None:
    """Enqueue check_org for every org that has at least one budget configured."""
    db = _get_supabase()
    result = db.table("budgets").select("org_id").execute()
    org_ids = {row["org_id"] for row in result.data}
    for org_id in org_ids:
        check_org.delay(org_id)
    log.info("budget_check_dispatched", count=len(org_ids))


@shared_task
def check_org(org_id: str) -> None:
    """
    For each budget in the org:
      1. Compute MTD spend for the budget's scope
      2. Compare against monthly_limit
      3. Fire alert at alert_at_pct and 100% thresholds (once per threshold per month)
      4. Write notified_*_at timestamps to prevent re-alerts in the same month
    """
    db = _get_supabase()

    budgets_result = (
        db.table("budgets")
        .select(
            "id, org_id, scope_type, scope_value, monthly_limit, alert_at_pct, "
            "notified_80_at, notified_100_at"
        )
        .eq("org_id", org_id)
        .execute()
    )

    if not budgets_result.data:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    alerted = 0

    for budget in budgets_result.data:
        budget_id: str = budget["id"]
        monthly_limit = Decimal(str(budget["monthly_limit"]))
        alert_at_pct: int = budget["alert_at_pct"]

        mtd_spend = _compute_scope_spend(
            db, org_id, budget["scope_type"], budget.get("scope_value")
        )

        if monthly_limit == 0:
            continue

        spent_pct = int((mtd_spend / monthly_limit * 100).to_integral_value())

        # ── 100% threshold ────────────────────────────────────────────────────
        if spent_pct >= 100:
            if not _same_calendar_month(budget.get("notified_100_at")):
                send_budget_alert.delay(budget_id, 100, org_id)
                db.table("budgets").update({"notified_100_at": now_iso}).eq("id", budget_id).execute()
                alerted += 1
                log.info(
                    "budget_alert_queued",
                    org_id=org_id,
                    budget_id=budget_id,
                    pct=100,
                    spent_pct=spent_pct,
                )
            # Always skip the warning threshold when already at 100%+
            continue

        # ── alert_at_pct threshold (default 80%) ─────────────────────────────
        if spent_pct >= alert_at_pct and not _same_calendar_month(budget.get("notified_80_at")):
            send_budget_alert.delay(budget_id, alert_at_pct, org_id)
            db.table("budgets").update({"notified_80_at": now_iso}).eq("id", budget_id).execute()
            alerted += 1
            log.info(
                "budget_alert_queued",
                org_id=org_id,
                budget_id=budget_id,
                pct=alert_at_pct,
                spent_pct=spent_pct,
            )

    log.info("budget_check_complete", org_id=org_id, alerted=alerted)
