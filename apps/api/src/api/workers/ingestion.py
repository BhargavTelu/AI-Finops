"""
Ingestion workers.
  backfill_integration - triggered on key connect (30d historical data)
  refresh_all_integrations - Celery beat every 4h
  refresh_integration - incremental fetch since last_synced_at
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from celery import shared_task
from supabase import create_client

from api.adapters.anthropic import AnthropicAdapter
from api.adapters.gemini import GeminiAdapter
from api.adapters.openai import OpenAIAdapter
from api.config import settings
from api.services.encryption import EncryptionService
from api.services.tag_engine import apply_rules, compile_rules

log = structlog.get_logger()

_BACKFILL_DAYS = 30
_BATCH_SIZE = 500


# ── Manual override helpers ────────────────────────────────────────────────────

def _norm_bucket_hour(ts: str) -> str:
    """Normalise a timestamptz string (DB or ISO) to a canonical UTC isoformat."""
    dt = datetime.fromisoformat(ts.replace(" ", "T"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _snapshot_overrides(
    db, org_id: str, integration_id: str, start: datetime, end: datetime
) -> dict[tuple[str, str, str], dict]:
    """
    Before delete-before-insert, fetch all manually-pinned rows for this window.
    Returns a dict keyed by (model, api_key_label, normalised_bucket_hour) so
    they can be restored after the fresh insert.
    """
    result = (
        db.table("usage_events")
        .select(
            "model, api_key_label, bucket_hour,"
            " feature_tag, team_tag, customer_tag, env_tag,"
            " manual_override_by, manual_override_at"
        )
        .eq("org_id", org_id)
        .eq("integration_id", integration_id)
        .eq("manual_override", True)
        .gte("bucket_hour", start.isoformat())
        .lt("bucket_hour", end.isoformat())
        .execute()
    )
    snapshot: dict[tuple[str, str, str], dict] = {}
    for row in result.data:
        # 'model' is NOT NULL in the schema; skip malformed rows defensively.
        if not row.get("model") or not row.get("bucket_hour"):
            continue
        key = (row["model"], row.get("api_key_label") or "", _norm_bucket_hour(row["bucket_hour"]))
        snapshot[key] = {
            "feature_tag": row.get("feature_tag"),
            "team_tag": row.get("team_tag"),
            "customer_tag": row.get("customer_tag"),
            "env_tag": row.get("env_tag"),
            "manual_override": True,
            "manual_override_by": row.get("manual_override_by"),
            "manual_override_at": row.get("manual_override_at"),
        }
    return snapshot


def _restore_overrides(
    db, org_id: str, integration_id: str, rows: list[dict], snapshot: dict
) -> None:
    """Patch back pinned tag values for any re-inserted row that had a manual override."""
    for row in rows:
        key = (row["model"], row.get("api_key_label") or "", _norm_bucket_hour(row["bucket_hour"]))
        if key not in snapshot:
            continue
        (
            db.table("usage_events")
            .update(snapshot[key])
            .eq("org_id", org_id)
            .eq("integration_id", integration_id)
            .eq("model", row["model"])
            .eq("api_key_label", row.get("api_key_label") or "")
            .eq("bucket_hour", row["bucket_hour"])
            .execute()
        )

# Map provider slug → adapter instance
_ADAPTERS: dict[str, Any] = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
    "gemini": GeminiAdapter(),
}


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _floor_utc_day(dt: datetime) -> datetime:
    """Floor a datetime to 00:00 UTC of its calendar day (tz-aware)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


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

    The delete window is floored to the UTC day boundary: adapters fetch complete
    1d buckets, so a mid-day `start` (e.g. last_synced_at from a 4h refresh) still
    re-fetches today's full-day bucket stamped at 00:00. Deleting only [start, end)
    would leave the earlier snapshot of that bucket in place and double-count the day.
    """
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError(f"Unsupported provider: {provider}")

    # Must match the day-bucket window the adapters actually fetch.
    window_start = _floor_utc_day(start)

    events = list(adapter.fetch_costs(key_bytes, start, end))

    # Load enabled tag rules for this org once - compiled before the event loop
    rules_result = (
        db.table("tag_rules")
        .select("match_type, match_pattern, priority, enabled, tags(type, name)")
        .eq("org_id", org_id)
        .eq("enabled", True)
        .execute()
    )
    compiled = compile_rules(rules_result.data)

    # Snapshot pinned overrides before the delete so they survive re-ingestion
    override_snapshot = _snapshot_overrides(db, org_id, integration_id, window_start, end)

    # Remove existing rows for this integration+window before inserting
    db.table("usage_events").delete().eq("integration_id", integration_id).gte(
        "bucket_hour", window_start.isoformat()
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
            **apply_rules(event.api_key_label, compiled),
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

    # Restore any admin-pinned tag assignments wiped by the delete
    if override_snapshot:
        _restore_overrides(db, org_id, integration_id, rows, override_snapshot)

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
        # Supabase returns BYTEA with \x prefix (PostgreSQL hex format); strip it.
        enc_hex = row["api_key_enc"]
        if enc_hex.startswith("\\x"):
            enc_hex = enc_hex[2:]
        key_bytes = cipher.decrypt(bytes.fromhex(enc_hex))

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
    Enqueue a refresh job for every refreshable integration.
    Runs every 4 hours via Celery beat.

    status='error' is included so a transient provider failure self-heals on
    the next sweep - excluding it permanently (and silently) stopped sync for
    any integration that exhausted its task retries once. Only 'revoked' is
    terminal.
    """
    db = _get_supabase()
    result = (
        db.table("integrations")
        .select("id, org_id")
        .in_("status", ["active", "error"])
        .execute()
    )

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
        # Supabase returns BYTEA with \x prefix (PostgreSQL hex format); strip it.
        enc_hex = row["api_key_enc"]
        if enc_hex.startswith("\\x"):
            enc_hex = enc_hex[2:]
        key_bytes = cipher.decrypt(bytes.fromhex(enc_hex))

        now = datetime.now(timezone.utc)
        # Fall back to 4h lookback if no prior sync - matches the beat cadence
        if row.get("last_synced_at"):
            start = datetime.fromisoformat(row["last_synced_at"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
        else:
            start = now - timedelta(hours=4)

        count = _ingest_window(db, integration_id, org_id, row["provider"], key_bytes, start, now)

        # status back to 'active': a previously errored integration that
        # refreshes successfully has recovered.
        db.table("integrations").update(
            {"last_synced_at": now.isoformat(), "last_error": None, "status": "active"}
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
