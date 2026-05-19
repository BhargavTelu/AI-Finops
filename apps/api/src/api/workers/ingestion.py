"""
Ingestion workers.
  backfill_integration — triggered on key connect (30d historical data)
  refresh_all_integrations — Celery beat every 4h
  refresh_integration — incremental fetch since last_synced_at
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from celery import shared_task
from supabase import create_client

from api.adapters.openai import OpenAIAdapter
from api.config import settings
from api.services.encryption import EncryptionService

log = structlog.get_logger()

_BACKFILL_DAYS = 30
_BATCH_SIZE = 500

# Map provider slug → adapter instance
_ADAPTERS: dict[str, Any] = {
    "openai": OpenAIAdapter(),
}


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _ingest_window(
    db,
    integration_id: str,
    org_id: str,
    provider: str,
    key_bytes: bytes,
    start: datetime,
    end: datetime,
) -> int:
    """
    Fetch events from the provider for [start, end), delete existing rows in that
    window, then insert fresh rows into usage_events. Returns the number of rows inserted.

    Delete-before-insert ensures idempotency on task retry without requiring
    a unique constraint on the high-write usage_events table.
    """
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError(f"Unsupported provider: {provider}")

    events = list(adapter.fetch_costs(key_bytes, start, end))

    # Remove existing rows for this integration+window before inserting
    db.table("usage_events").delete().eq("integration_id", integration_id).gte(
        "bucket_hour", start.isoformat()
    ).lt("bucket_hour", end.isoformat()).execute()

    if not events:
        return 0

    rows = [
        {
            "org_id": org_id,
            "integration_id": integration_id,
            "provider": event.provider,
            "model": event.model,
            "api_key_label": event.api_key_label,
            "feature_tag": None,  # tag-rule engine fills this in a later milestone
            "team_tag": None,
            "customer_tag": None,
            "env_tag": None,
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "cached_tokens": event.cached_tokens,
            "cost_usd": str(event.cost_usd),  # NUMERIC sent as string over REST
            "request_count": event.request_count,
            "bucket_hour": event.bucket_hour.isoformat(),
            "raw_meta": event.raw_meta,
        }
        for event in events
    ]

    for chunk in _chunks(rows, _BATCH_SIZE):
        db.table("usage_events").insert(chunk).execute()

    return len(rows)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def backfill_integration(self, integration_id: str, org_id: str) -> None:  # type: ignore[misc]
    """
    Pull 30 days of historical data from the provider.
    Triggered immediately after a new integration is created.
    Target: completes in < 5 min for a $20K/mo org.
    """
    db = _get_supabase()

    result = (
        db.table("integrations")
        .select("provider, api_key_enc, status")
        .eq("id", integration_id)
        .eq("org_id", org_id)
        .execute()
    )

    if not result.data:
        log.warning("backfill_integration_not_found", integration_id=integration_id, org_id=org_id)
        return

    row = result.data[0]
    if row["status"] == "revoked":
        log.warning("backfill_integration_revoked", integration_id=integration_id, org_id=org_id)
        return

    try:
        cipher = EncryptionService(settings.encryption_key)
        key_bytes = cipher.decrypt(bytes.fromhex(row["api_key_enc"]))

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=_BACKFILL_DAYS)

        count = _ingest_window(db, integration_id, org_id, row["provider"], key_bytes, start, now)

        db.table("integrations").update(
            {"last_synced_at": now.isoformat(), "last_error": None, "status": "active"}
        ).eq("id", integration_id).eq("org_id", org_id).execute()

        # Trigger aggregation immediately so charts are populated without waiting for the nightly run
        from api.workers.aggregation import aggregate_org  # local import avoids circular dep at module load

        aggregate_org.delay(org_id)

        log.info(
            "backfill_complete",
            org_id=org_id,
            integration_id=integration_id,
            provider=row["provider"],
            events=count,
        )

    except Exception as exc:
        db.table("integrations").update(
            {"last_error": str(exc)[:500], "status": "error"}
        ).eq("id", integration_id).eq("org_id", org_id).execute()

        log.error(
            "backfill_failed",
            org_id=org_id,
            integration_id=integration_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)


@shared_task
def refresh_all_integrations() -> None:
    """
    Enqueue a refresh job for every active integration.
    Runs every 4 hours via Celery beat.
    """
    db = _get_supabase()
    result = db.table("integrations").select("id, org_id").eq("status", "active").execute()

    for row in result.data:
        refresh_integration.delay(row["id"], row["org_id"])

    log.info("refresh_dispatched", count=len(result.data))


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_integration(self, integration_id: str, org_id: str) -> None:  # type: ignore[misc]
    """Fetch incremental data (since last_synced_at) for a single integration."""
    db = _get_supabase()

    result = (
        db.table("integrations")
        .select("provider, api_key_enc, last_synced_at, status")
        .eq("id", integration_id)
        .eq("org_id", org_id)
        .execute()
    )

    if not result.data:
        log.warning("refresh_integration_not_found", integration_id=integration_id, org_id=org_id)
        return

    row = result.data[0]
    if row["status"] == "revoked":
        return

    try:
        cipher = EncryptionService(settings.encryption_key)
        key_bytes = cipher.decrypt(bytes.fromhex(row["api_key_enc"]))

        now = datetime.now(timezone.utc)
        # Fall back to 4h lookback if no prior sync — matches the beat cadence
        if row.get("last_synced_at"):
            start = datetime.fromisoformat(row["last_synced_at"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        else:
            start = now - timedelta(hours=4)

        count = _ingest_window(db, integration_id, org_id, row["provider"], key_bytes, start, now)

        db.table("integrations").update(
            {"last_synced_at": now.isoformat(), "last_error": None}
        ).eq("id", integration_id).eq("org_id", org_id).execute()

        log.info(
            "refresh_complete",
            org_id=org_id,
            integration_id=integration_id,
            provider=row["provider"],
            events=count,
        )

    except Exception as exc:
        db.table("integrations").update(
            {"last_error": str(exc)[:500], "status": "error"}
        ).eq("id", integration_id).eq("org_id", org_id).execute()

        log.error(
            "refresh_failed",
            org_id=org_id,
            integration_id=integration_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)
