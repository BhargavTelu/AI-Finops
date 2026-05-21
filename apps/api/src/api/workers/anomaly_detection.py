"""
Nightly anomaly detection — runs at 01:00 UTC (after aggregation).
Algorithm: rolling mean + 2σ over 7 days; $10 floor; ≥15 days of data required.
See architecture.md § Anomaly Algorithm and services/anomaly.py.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import structlog
from celery import shared_task
from supabase import create_client

from api.config import settings
from api.services.anomaly import detect_anomalies
from api.workers.notifications import send_anomaly_alert

log = structlog.get_logger()

_HISTORY_DAYS = 15  # need ≥15 to have a 7-day rolling window + today


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@shared_task
def detect_all_orgs() -> None:
    """Enqueue detect_org for every org with at least one active integration."""
    db = _get_supabase()
    result = db.table("integrations").select("org_id").eq("status", "active").execute()

    org_ids = {row["org_id"] for row in result.data}
    for org_id in org_ids:
        detect_org.delay(org_id)

    log.info("anomaly_detection_dispatched", count=len(org_ids))


@shared_task
def detect_org(org_id: str) -> None:
    """
    For each (model, feature_tag, team_tag, customer_tag) group:
      1. Load last _HISTORY_DAYS of daily_cost_summaries (oldest → newest)
      2. Call services.anomaly.detect_anomalies
      3. INSERT anomaly row if threshold crossed (with today-dedup guard)
      4. Enqueue send_anomaly_alert for severity ≥ medium
    """
    db = _get_supabase()
    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=_HISTORY_DAYS)

    # Pull all relevant daily rows for the period in one query.
    # daily_cost_summaries uses '' (empty string) for unset tags — no nulls.
    rows_result = (
        db.table("daily_cost_summaries")
        .select("day, model, feature_tag, team_tag, customer_tag, total_cost_usd")
        .eq("org_id", org_id)
        .gte("day", from_date.isoformat())
        .lt("day", today.isoformat())  # exclude today (partial day)
        .execute()
    )

    if not rows_result.data:
        log.info("anomaly_detection_no_data", org_id=org_id)
        return

    # Group rows by (model, feature_tag, team_tag, customer_tag).
    # Sum costs per day within each group — multiple provider rows can share
    # the same model+tag combo on the same day.
    GroupKey = tuple[str, str, str, str]
    group_days: dict[GroupKey, dict[date, Decimal]] = defaultdict(dict)

    for row in rows_result.data:
        key: GroupKey = (
            row["model"],
            row.get("feature_tag") or "",
            row.get("team_tag") or "",
            row.get("customer_tag") or "",
        )
        row_date = date.fromisoformat(row["day"])
        existing = group_days[key].get(row_date, Decimal("0"))
        group_days[key][row_date] = existing + Decimal(str(row["total_cost_usd"]))

    # Fetch open anomalies already detected today for this org (dedup guard).
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    existing_result = (
        db.table("anomalies")
        .select("scope_kind, scope_value")
        .eq("org_id", org_id)
        .eq("status", "open")
        .gte("detected_at", today_start.isoformat())
        .execute()
    )
    already_open: set[tuple[str, str]] = {
        (r["scope_kind"], r.get("scope_value") or "") for r in existing_result.data
    }

    inserted = 0
    # from_date is today - _HISTORY_DAYS; the cursor must start there so
    # the history list is exactly _HISTORY_DAYS long for the algorithm.
    first_day = today - timedelta(days=_HISTORY_DAYS)

    for (model, feature_tag, team_tag, customer_tag), day_map in group_days.items():
        # Build a dense history list (oldest → newest), filling gaps with $0.
        history: list[Decimal] = []
        cursor = first_day
        while cursor < today:
            history.append(day_map.get(cursor, Decimal("0")))
            cursor += timedelta(days=1)

        result_obj = detect_anomalies(history)
        if result_obj is None:
            continue

        scope_kind = "model"
        scope_value = model
        dedup_key = (scope_kind, scope_value)

        if dedup_key in already_open:
            log.debug(
                "anomaly_dedup_skip",
                org_id=org_id,
                scope_kind=scope_kind,
                scope_value=scope_value,
            )
            continue

        anomaly_id = str(uuid.uuid4())
        context = {
            "model": model,
            "feature_tag": feature_tag or None,
            "team_tag": team_tag or None,
            "customer_tag": customer_tag or None,
        }

        db.table("anomalies").insert(
            {
                "id": anomaly_id,
                "org_id": org_id,
                "scope_kind": scope_kind,
                "scope_value": scope_value,
                "baseline_usd": str(result_obj.baseline_usd),
                "actual_usd": str(result_obj.actual_usd),
                "spike_pct": result_obj.spike_pct,
                "severity": result_obj.severity,
                "status": "open",
                "context": context,
            }
        ).execute()

        inserted += 1
        already_open.add(dedup_key)

        # Group C implements the alert body — enqueueing here so the wire is
        # complete even while send_anomaly_alert is still a stub.
        if result_obj.severity in ("medium", "high"):
            send_anomaly_alert.delay(anomaly_id)

        log.info(
            "anomaly_inserted",
            org_id=org_id,
            anomaly_id=anomaly_id,
            scope_value=scope_value,
            severity=result_obj.severity,
            spike_pct=result_obj.spike_pct,
        )

    log.info("anomaly_detection_complete", org_id=org_id, inserted=inserted)
