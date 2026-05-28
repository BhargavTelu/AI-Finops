import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
import httpx
import structlog
from supabase import create_client

from api.config import settings

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Svix replays webhooks for up to 5 days, but the timestamp check here only
# defends against replay attacks from stale requests - not legitimate retries
# (Svix sends a fresh timestamp on each delivery attempt).
_SVIX_TOLERANCE_SECONDS = 300  # 5 minutes

_CLERK_API_BASE = "https://api.clerk.com/v1"


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_svix_signature(
    body: bytes,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
) -> None:
    """
    Verify Svix HMAC-SHA256 webhook signature.

    Signed payload format: "{svix-id}.{svix-timestamp}.{raw_body}"
    Key: base64-decode(webhook_secret.removeprefix("whsec_"))
    """
    try:
        ts = int(svix_timestamp)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid svix-timestamp",
        ) from None

    if abs(int(time.time()) - ts) > _SVIX_TOLERANCE_SECONDS:
        log.warning(
            "webhook_timestamp_out_of_tolerance",
            svix_timestamp=svix_timestamp,
            server_time=int(time.time()),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook timestamp out of tolerance",
        )

    key = base64.b64decode(
        settings.clerk_webhook_secret.removeprefix("whsec_")
    )
    signed_payload = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(
        hmac.new(key, signed_payload, hashlib.sha256).digest()
    ).decode()

    # svix-signature may contain several space-separated "v1,<b64>" entries
    provided = [
        s.removeprefix("v1,")
        for s in svix_signature.split(" ")
        if s.startswith("v1,")
    ]

    if not any(hmac.compare_digest(expected, p) for p in provided):
        # Log signature count to distinguish "no v1, signatures" from "wrong secret"
        log.warning(
            "webhook_signature_mismatch",
            provided_count=len(provided),
            svix_id=svix_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _service_db() -> Any:
    """Supabase client authenticated with the service role key (bypasses RLS)."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ── Clerk metadata write-back ──────────────────────────────────────────────────

async def _write_clerk_metadata(resource: str, clerk_id: str, db_id: UUID) -> None:
    """
    Store the Supabase DB UUID in Clerk's public_metadata so the HS256 JWT
    template can include {{user.public_metadata.db_id}} / {{org.public_metadata.db_id}}.
    This makes the org_id claim a real UUID, satisfying the ::uuid RLS cast.

    Failures are logged but do not fail the webhook - the DB row already exists.
    The metadata can be patched manually if this call fails.
    """
    url = f"{_CLERK_API_BASE}/{resource}/{clerk_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                url,
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
                json={"public_metadata": {"db_id": str(db_id)}},
            )
        if not resp.is_success:
            log.warning(
                "clerk_metadata_write_failed",
                resource=resource,
                clerk_id=clerk_id,
                http_status=resp.status_code,
            )
    except httpx.HTTPError as exc:
        log.warning(
            "clerk_metadata_write_error",
            resource=resource,
            clerk_id=clerk_id,
            error=str(exc),
        )


# ── Event handlers ─────────────────────────────────────────────────────────────

def _handle_user_created(data: dict[str, Any], db: Any) -> UUID:
    """
    Upsert a user row from a Clerk user.created event.
    Uses clerk_id as the conflict target so duplicate deliveries are harmless.
    """
    clerk_user_id: str = data["id"]

    # Resolve the primary email from primary_email_address_id
    primary_id: str | None = data.get("primary_email_address_id")
    email_entries: list[dict[str, Any]] = data.get("email_addresses", [])
    email = next(
        (e["email_address"] for e in email_entries if e["id"] == primary_id),
        email_entries[0]["email_address"] if email_entries else None,
    )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user.created event contains no email address",
        )

    first: str = data.get("first_name") or ""
    last: str = data.get("last_name") or ""
    full_name: str | None = f"{first} {last}".strip() or None

    resp = (
        db.table("users")
        .upsert(
            {"clerk_id": clerk_user_id, "email": email, "full_name": full_name},
            on_conflict="clerk_id",
        )
        .execute()
    )

    db_id = UUID(resp.data[0]["id"])
    log.info("user_synced", clerk_id=clerk_user_id, db_id=str(db_id))
    return db_id


def _handle_org_created(data: dict[str, Any], db: Any) -> UUID:
    """
    Upsert an organization row from a Clerk organization.created event.
    Sets a 14-day trial window, matching the billing table default.
    """
    clerk_org_id: str = data["id"]
    name: str = data["name"]

    trial_ends = (datetime.now(tz=UTC) + timedelta(days=14)).isoformat()

    resp = (
        db.table("organizations")
        .upsert(
            {
                "clerk_id": clerk_org_id,
                "name": name,
                "plan": "trial",
                "trial_ends_at": trial_ends,
            },
            on_conflict="clerk_id",
        )
        .execute()
    )

    db_id = UUID(resp.data[0]["id"])
    log.info("org_synced", clerk_id=clerk_org_id, db_id=str(db_id))
    return db_id


def _handle_membership_created(data: dict[str, Any], db: Any) -> None:
    """
    Insert an organization_members row from a Clerk organizationMembership.created event.

    Raises 500 (so Svix retries) if the parent user or org row is missing -
    this handles the rare race where user.created / organization.created hasn't
    been processed yet.
    """
    clerk_org_id: str = data["organization"]["id"]
    clerk_user_id: str = data["public_user_data"]["user_id"]
    clerk_role: str = data.get("role", "org:member")

    # Map Clerk's namespaced roles (org:admin, org:member) to our simple enum
    role = "admin" if "admin" in clerk_role else "member"

    # Use try/except so PostgREST PGRST116 (no rows) returns 500 for Svix retry,
    # not an unhandled exception. .single() raises when the row is absent.
    try:
        user_resp = (
            db.table("users").select("id").eq("clerk_id", clerk_user_id).single().execute()
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parent user or org row not found; webhook will be retried",
        )

    try:
        org_resp = (
            db.table("organizations")
            .select("id")
            .eq("clerk_id", clerk_org_id)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parent user or org row not found; webhook will be retried",
        )

    # PostgREST can return an error dict instead of a row dict - validate both.
    if not isinstance(user_resp.data, dict) or "id" not in user_resp.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parent user or org row not found; webhook will be retried",
        )
    if not isinstance(org_resp.data, dict) or "id" not in org_resp.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parent user or org row not found; webhook will be retried",
        )

    user_db_id: str = user_resp.data["id"]
    org_db_id: str = org_resp.data["id"]

    (
        db.table("organization_members")
        .upsert(
            {"org_id": org_db_id, "user_id": user_db_id, "role": role},
            on_conflict="org_id,user_id",
        )
        .execute()
    )

    log.info("membership_synced", org_id=org_db_id, actor_user_id=user_db_id, role=role)


# ── Route handlers ─────────────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
) -> dict[str, bool]:
    """
    Verify Stripe signature and process billing lifecycle events.
    Updates the billing table on checkout.session.completed,
    customer.subscription.updated, and customer.subscription.deleted.
    """
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(alias="svix-id"),
    svix_timestamp: str = Header(alias="svix-timestamp"),
    svix_signature: str = Header(alias="svix-signature"),
) -> dict[str, bool]:
    """
    Verify Clerk webhook signature (Svix) and sync identity data.

    Handled events:
      user.created               → upsert users row
      organization.created       → upsert organizations row
      organizationMembership.created → upsert organization_members row

    After each identity row is created the DB UUID is written back to Clerk's
    public_metadata so the HS256 Supabase JWT template can embed it as org_id,
    which satisfies the ::uuid cast in every RLS policy.
    """
    body = await request.body()
    _verify_svix_signature(body, svix_id, svix_timestamp, svix_signature)

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body"
        ) from None

    event_type: str = payload.get("type", "")
    data: dict[str, Any] = payload.get("data", {})

    db = _service_db()

    if event_type == "user.created":
        db_id = _handle_user_created(data, db)
        await _write_clerk_metadata("users", data["id"], db_id)

    elif event_type == "organization.created":
        db_id = _handle_org_created(data, db)
        await _write_clerk_metadata("organizations", data["id"], db_id)

    elif event_type == "organizationMembership.created":
        _handle_membership_created(data, db)

    else:
        log.debug("clerk_webhook_unhandled_event", event_type=event_type)

    return {"received": True}
