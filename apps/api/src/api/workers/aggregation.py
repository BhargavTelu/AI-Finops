"""
Nightly aggregation: usage_events → daily_cost_summaries.
Runs at 00:30 UTC via Celery beat.

Uses UPSERT so it's idempotent - safe to re-run on failure.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from celery import shared_task
import structlog
from supabase import create_client

from api.config import settings
from api.workers.ingestion import _chunks

log = structlog.get_logger()

_PAGE_SIZE = 1000

# (day, provider, model, feature_tag, team_tag, customer_tag, env_tag)
_SummaryKey = tuple[date, str, str, str, str, str, str]


def _get_supabase() -> Any:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@shared_task
def aggregate_all_orgs() -> None:
    """Enqueue aggregate_org for every org with active integrations."""
    db = _get_supabase()
    result = db.table("integrations").select("org_id").eq("status", "active").execute()

    org_ids = {row["org_id"] for row in result.data}
    for org_id in org_ids:
        aggregate_org.delay(org_id)

    log.info("aggregation_dispatched", count=len(org_ids))


@shared_task
def aggregate_org(org_id: str) -> None:
    """
    GROUP BY (day, provider, model, *_tag) → rebuild daily_cost_summaries.
    Processes all days up to yesterday UTC - never today's partial-day data.
    Delete-before-insert ensures revoked-integration data is purged on every run.
    """
    db = _get_supabase()

    today = datetime.now(UTC).date()
    from_date = today - timedelta(days=31)

    # Only aggregate events from non-revoked integrations so revoking an
    # integration immediately removes its data on the next aggregation run.
    integrations_result = (
        db.table("integrations")
        .select("id")
        .eq("org_id", org_id)
        .neq("status", "revoked")
        .execute()
    )
    active_ids = [row["id"] for row in integrations_result.data]

    # Always wipe the window first - removes stale rows from previously revoked
    # integrations even when no active events exist for the period.
    db.table("daily_cost_summaries").delete().eq("org_id", org_id).gte(
        "day", from_date.isoformat()
    ).execute()

    if not active_ids:
        log.info("aggregation_no_active_integrations", org_id=org_id)
        return

    # Paginate through usage_events scoped to active integrations only
    offset = 0
    all_rows: list[dict[str, Any]] = []
    while True:
        result = (
            db.table("usage_events")
            .select(
                "provider, model, feature_tag, team_tag, customer_tag, env_tag, "
                "cost_usd, request_count, input_tokens, output_tokens, cached_tokens, bucket_hour"
            )
            .eq("org_id", org_id)
            .in_("integration_id", active_ids)
            .gte("bucket_hour", from_date.isoformat())
            .lt("bucket_hour", today.isoformat())
            # Deterministic ordering is required for offset pagination -
            # without it Postgres may repeat/skip rows across pages and the
            # summaries silently drift once an org exceeds one page.
            .order("id", desc=False)
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        all_rows.extend(result.data)
        if len(result.data) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    if not all_rows:
        log.info("aggregation_no_data", org_id=org_id)
        return

    # Group in Python: (day, provider, model, feature_tag, team_tag, customer_tag, env_tag)
    # → {total_cost_usd, total_requests, total_tokens}
    groups: dict[_SummaryKey, dict[str, Any]] = defaultdict(
        lambda: {"total_cost_usd": Decimal("0"), "total_requests": 0, "total_tokens": 0}
    )

    for row in all_rows:
        # Supabase returns TIMESTAMPTZ as an ISO string; parse it and floor to UTC date
        bucket_dt = datetime.fromisoformat(row["bucket_hour"])
        if bucket_dt.tzinfo is None:
            bucket_dt = bucket_dt.replace(tzinfo=UTC)
        row_date = bucket_dt.astimezone(UTC).date()

        key: _SummaryKey = (
            row_date,
            row["provider"],
            row["model"],
            row.get("feature_tag") or "",
            row.get("team_tag") or "",
            row.get("customer_tag") or "",
            row.get("env_tag") or "",
        )

        totals = groups[key]
        totals["total_cost_usd"] += Decimal(str(row["cost_usd"]))
        totals["total_requests"] += row["request_count"]
        totals["total_tokens"] += (
            (row["input_tokens"] or 0) + (row["output_tokens"] or 0) + (row["cached_tokens"] or 0)
        )

    upsert_rows = [
        {
            "org_id": org_id,
            "day": str(key[0]),
            "provider": key[1],
            "model": key[2],
            "feature_tag": key[3],
            "team_tag": key[4],
            "customer_tag": key[5],
            "env_tag": key[6],
            "total_cost_usd": str(totals["total_cost_usd"]),
            "total_requests": totals["total_requests"],
            "total_tokens": totals["total_tokens"],
        }
        for key, totals in groups.items()
    ]

    for chunk in _chunks(upsert_rows, 500):
        db.table("daily_cost_summaries").upsert(
            chunk,
            on_conflict="org_id,day,provider,model,feature_tag,team_tag,customer_tag,env_tag",
        ).execute()

    unique_days = len({row["day"] for row in upsert_rows})
    log.info(
        "aggregation_complete",
        org_id=org_id,
        days=unique_days,
        summaries=len(upsert_rows),
    )
