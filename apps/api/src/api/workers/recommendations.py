"""
Nightly recommendations generation - runs at 02:30 UTC (after budget checks at 02:00).

For each org with active integrations:
  1. Aggregate last 30d daily_cost_summaries by (provider, model, feature_tag)
  2. Run rule-based heuristics (model_swap, caching, batch)
  3. Insert new recommendations, skipping any (org, type, scope_value) that already
     has an open ('new') recommendation - dedup via explicit query rather than relying
     on partial unique index error parsing.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from celery import shared_task
from supabase import create_client

from api.config import settings
from api.services.db import fetch_all_pages
from api.services.recommendations import ModelStats, generate_recommendations

log = structlog.get_logger()


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@shared_task
def generate_all_org_recommendations() -> None:
    """Enqueue generate_org_recommendations for every org with active integrations."""
    db = _get_supabase()
    result = db.table("integrations").select("org_id").eq("status", "active").execute()
    org_ids = {row["org_id"] for row in result.data}
    for org_id in org_ids:
        generate_org_recommendations.delay(org_id)
    log.info("recommendations_dispatch", count=len(org_ids))


@shared_task
def generate_org_recommendations(org_id: str) -> None:
    """
    Run the recommendations engine for one org and persist new results.

    Uses an explicit dedup check rather than ON CONFLICT to avoid relying on
    partial-index error string parsing across Supabase client versions.
    """
    db = _get_supabase()
    today = datetime.now(timezone.utc).date()
    start_day = (today - timedelta(days=30)).isoformat()

    # Pull last 30d summaries - one row per (day, provider, model, feature_tag, ...).
    # Paged: 30 days x models x tag combos exceeds one PostgREST page for
    # larger orgs, and a truncated read skews every savings estimate.
    summary_rows = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("provider, model, feature_tag, total_cost_usd, total_requests, total_tokens")
        .eq("org_id", org_id)
        .gte("day", start_day)
    )

    if not summary_rows:
        log.info("recommendations_no_data", org_id=org_id)
        return

    # Group by (provider, model, feature_tag) and sum metrics.
    grouped: dict[tuple[str, str, str | None], dict] = {}
    for row in summary_rows:
        key = (row["provider"], row["model"], row.get("feature_tag") or None)
        if key not in grouped:
            grouped[key] = {
                "total_cost_usd": Decimal(0),
                "total_requests": 0,
                "total_tokens": 0,
            }
        grouped[key]["total_cost_usd"] += Decimal(str(row["total_cost_usd"]))
        grouped[key]["total_requests"] += row["total_requests"] or 0
        grouped[key]["total_tokens"] += row["total_tokens"] or 0

    stats = [
        ModelStats(
            provider=k[0],
            model=k[1],
            feature_tag=k[2],
            total_cost_usd=v["total_cost_usd"],
            total_requests=v["total_requests"],
            total_tokens=v["total_tokens"],
        )
        for k, v in grouped.items()
    ]

    recs = generate_recommendations(stats)
    if not recs:
        log.info("recommendations_none_generated", org_id=org_id)
        return

    # Fetch existing open recommendations to deduplicate before inserting.
    existing_result = (
        db.table("recommendations")
        .select("type, scope_value")
        .eq("org_id", org_id)
        .eq("status", "new")
        .execute()
    )
    existing_keys: set[tuple[str, str]] = {
        (row["type"], row["scope_value"] or "")
        for row in existing_result.data
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for rec in recs:
        key = (rec.type, rec.scope_value)
        if key in existing_keys:
            log.debug(
                "recommendations_dedup_skip",
                org_id=org_id,
                type=rec.type,
                scope_value=rec.scope_value,
            )
            continue

        db.table("recommendations").insert(
            {
                "org_id": org_id,
                "type": rec.type,
                "title": rec.title,
                "description": rec.description,
                "projected_savings_usd": (
                    str(rec.projected_savings_usd) if rec.projected_savings_usd else None
                ),
                "confidence": str(rec.confidence),
                "evidence": rec.evidence,
                "scope_value": rec.scope_value,
                "status": "new",
                "generated_at": now_iso,
            }
        ).execute()

        existing_keys.add(key)  # prevent double-insert within the same run
        inserted += 1

    log.info(
        "recommendations_complete",
        org_id=org_id,
        generated=len(recs),
        inserted=inserted,
        deduped=len(recs) - inserted,
    )
