from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
import structlog

from api.adapters.anthropic import AnthropicAdapter
from api.adapters.gemini import GeminiAdapter
from api.adapters.openai import OpenAIAdapter
from api.config import settings
from api.deps import OrgDep
from api.schemas.integrations import IntegrationCreate, IntegrationRead
from api.services.db import get_supabase
from api.services.encryption import EncryptionService
from api.workers.aggregation import aggregate_org
from api.workers.ingestion import backfill_integration

log = structlog.get_logger()

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Map provider slug → adapter instance
_ADAPTERS = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
    "gemini": GeminiAdapter(),
}


def _get_supabase():
    return get_supabase()


def _resolve_user_uuid(db, clerk_user_id: str) -> str | None:
    """
    Map the Clerk sub claim to the Supabase users.id UUID.

    audit_events.actor_user_id is a UUID FK to users(id) - inserting the raw
    Clerk sub fails the cast and the surrounding try/except swallowed it, so
    no integration audit row was ever written.
    """
    result = db.table("users").select("id").eq("clerk_id", clerk_user_id).limit(1).execute()
    return result.data[0]["id"] if result.data else None


@router.post("", status_code=201)
def create_integration(body: IntegrationCreate, org: OrgDep) -> IntegrationRead:
    """
    Add a provider Admin API key.
    Validates the key, AES-256-GCM encrypts it, stores it, and enqueues backfill.
    Key is never returned after this call.
    """
    adapter = _ADAPTERS.get(body.provider)
    if adapter is None:
        raise HTTPException(status_code=422, detail=f"Provider '{body.provider}' is not yet supported")

    # Validate key before persisting anything
    try:
        adapter.validate(body.api_key.encode())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cipher = EncryptionService(settings.encryption_key)
    api_key_enc: bytes = cipher.encrypt(body.api_key.encode())

    db = _get_supabase()

    # Insert integration row
    try:
        result = (
            db.table("integrations")
            .insert(
                {
                    "org_id": org.org_id,
                    "provider": body.provider,
                    "display_name": body.display_name,
                    "api_key_enc": "\\x" + api_key_enc.hex(),  # PostgreSQL bytea hex literal: \x<hex>
                    "status": "active",
                }
            )
            .execute()
        )
    except Exception as exc:
        # Unique violation: (org_id, provider, display_name) already exists
        err_msg = str(exc)
        if "unique" in err_msg.lower() or "duplicate" in err_msg.lower():
            raise HTTPException(status_code=409, detail="An integration with this name already exists") from exc
        log.error("integration_insert_failed", org_id=org.org_id, error=err_msg)
        raise HTTPException(status_code=500, detail="Failed to save integration") from exc

    row = result.data[0]

    # Audit log - non-fatal if this fails
    try:
        db.table("audit_events").insert(
            {
                "org_id": org.org_id,
                "actor_user_id": _resolve_user_uuid(db, org.user_id),
                "action": "integration.create",
                "target_kind": "integration",
                "target_id": row["id"],
            }
        ).execute()
    except Exception:
        log.warning("audit_log_failed", org_id=org.org_id, action="integration.create")

    # Fire-and-forget backfill - Celery task handles retry logic
    backfill_integration.delay(str(row["id"]), org.org_id)

    log.info("integration_created", org_id=org.org_id, integration_id=row["id"], provider=body.provider)

    return IntegrationRead(
        id=row["id"],
        org_id=row["org_id"],
        provider=row["provider"],
        display_name=row["display_name"],
        status=row["status"],
        last_synced_at=row.get("last_synced_at"),
        last_error=row.get("last_error"),
        created_at=row["created_at"],
    )


@router.get("")
def list_integrations(org: OrgDep) -> list[IntegrationRead]:
    """List all integrations for the org (key redacted)."""
    db = _get_supabase()

    result = (
        db.table("integrations")
        .select("id, org_id, provider, display_name, status, last_synced_at, last_error, created_at")
        .eq("org_id", org.org_id)
        .neq("status", "revoked")
        .order("created_at", desc=True)
        .execute()
    )

    return [
        IntegrationRead(
            id=row["id"],
            org_id=row["org_id"],
            provider=row["provider"],
            display_name=row["display_name"],
            status=row["status"],
            last_synced_at=row.get("last_synced_at"),
            last_error=row.get("last_error"),
            created_at=row["created_at"],
        )
        for row in result.data
    ]


@router.delete("/{integration_id}", status_code=204)
def delete_integration(integration_id: str, org: OrgDep) -> None:
    """Soft-revoke a provider integration. Logs to audit_events."""
    db = _get_supabase()

    result = (
        db.table("integrations")
        .update({"status": "revoked"})
        .eq("id", integration_id)
        .eq("org_id", org.org_id)  # org isolation enforced in code (service role client)
        .neq("status", "revoked")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Remove all raw events for this integration so they no longer appear in dashboards.
    # Summaries are rebuilt by the aggregation task triggered below.
    try:
        db.table("usage_events").delete().eq("integration_id", integration_id).execute()
        # Wipe org summaries for this date range so stale provider rows are removed,
        # then immediately re-aggregate from the remaining usage_events.
        today = datetime.now(timezone.utc).date()
        from_date = today - timedelta(days=31)
        db.table("daily_cost_summaries").delete().eq("org_id", org.org_id).gte(
            "day", from_date.isoformat()
        ).execute()
        aggregate_org.delay(org.org_id)
    except Exception as exc:
        # Non-fatal - stale data will be cleaned up on the next nightly aggregation run
        log.warning("revoke_cleanup_failed", org_id=org.org_id, integration_id=integration_id, error=str(exc))

    # Audit log - non-fatal if this fails
    try:
        db.table("audit_events").insert(
            {
                "org_id": org.org_id,
                "actor_user_id": _resolve_user_uuid(db, org.user_id),
                "action": "integration.delete",
                "target_kind": "integration",
                "target_id": integration_id,
            }
        ).execute()
    except Exception:
        log.warning("audit_log_failed", org_id=org.org_id, action="integration.delete")

    log.info("integration_revoked", org_id=org.org_id, integration_id=integration_id)


@router.post("/{integration_id}/test")
def test_integration(integration_id: str, org: OrgDep) -> dict:
    """Revalidate the stored key and trigger a fresh backfill job."""
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")
