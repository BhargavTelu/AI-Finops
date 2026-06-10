"""
Slack OAuth routes.

GET   /slack/status           - check whether Slack is connected for the org
GET   /slack/oauth/state      - signed CSRF state for the OAuth install URL
POST  /slack/oauth/callback   - exchange authorization code for bot token
PATCH /slack/settings         - update mute preferences
POST  /slack/disconnect       - revoke token and remove integration
"""

import structlog
from fastapi import APIRouter, HTTPException
from supabase import create_client

from api.config import settings
from api.deps import OrgDep
from api.schemas.slack import SlackOAuthCallbackBody, SlackSettingsUpdate, SlackStatusResponse
from api.services.encryption import EncryptionService
from api.services.slack_client import exchange_code, revoke_token
from api.services.slack_state import generate_state, validate_state

log = structlog.get_logger()

router = APIRouter(prefix="/slack", tags=["slack"])


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ── GET /slack/status ──────────────────────────────────────────────────────────

@router.get("/status")
async def slack_status(org: OrgDep) -> SlackStatusResponse:
    """Return connection state for the org's Slack integration."""
    db = _get_supabase()
    result = (
        db.table("slack_integrations")
        .select("workspace_id, channel_id, channel_name, created_at, alerts_muted")
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        return SlackStatusResponse(connected=False)

    row = result.data[0]
    return SlackStatusResponse(
        connected=True,
        workspace_id=row["workspace_id"],
        channel_name=row["channel_name"],
        channel_id=row["channel_id"],
        installed_at=row["created_at"],
        alerts_muted=bool(row.get("alerts_muted", False)),
    )


# ── GET /slack/oauth/state ─────────────────────────────────────────────────────

@router.get("/oauth/state")
async def slack_oauth_state(org: OrgDep) -> dict[str, str]:
    """
    Issue a signed, expiring CSRF state token bound to the caller's org.
    The frontend embeds it in the Slack authorize URL; the callback rejects
    any code exchange whose state was not signed for the same org.
    """
    if not settings.slack_client_id or not settings.slack_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Slack integration is not configured on this server.",
        )
    if not settings.encryption_key:
        raise HTTPException(
            status_code=503,
            detail="Encryption key is not configured on this server.",
        )
    return {"state": generate_state(org.org_id, settings.encryption_key)}


# ── POST /slack/oauth/callback ─────────────────────────────────────────────────

@router.post("/oauth/callback")
async def slack_oauth_callback(body: SlackOAuthCallbackBody, org: OrgDep) -> SlackStatusResponse:
    """
    Exchange a Slack OAuth authorization code for a bot token.

    The frontend receives the code from Slack's redirect and passes it here.
    We exchange it, encrypt the bot token (AES-256-GCM), and upsert a row in
    slack_integrations. One Slack workspace per org - upsert overwrites any
    prior install, allowing re-install to a different channel.
    """
    if not settings.slack_client_id or not settings.slack_client_secret:
        raise HTTPException(
            status_code=503,
            detail="Slack integration is not configured on this server.",
        )

    # CSRF guard: the state must have been issued by /slack/oauth/state for
    # this same org. Rejects codes injected via a forged callback URL.
    if not validate_state(body.state, org.org_id, settings.encryption_key):
        log.warning("slack_oauth_state_invalid", org_id=org.org_id)
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth state. Please restart the Slack connection.",
        )

    try:
        slack_resp = exchange_code(
            code=body.code,
            client_id=settings.slack_client_id,
            client_secret=settings.slack_client_secret,
            redirect_uri=settings.slack_redirect_uri,
        )
    except ValueError as exc:
        log.warning("slack_oauth_exchange_failed", org_id=org.org_id, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    bot_token: str = slack_resp["access_token"]
    team = slack_resp.get("team") or {}
    workspace_id: str = team.get("id", "")
    if not workspace_id:
        raise HTTPException(
            status_code=400,
            detail="Slack response missing workspace info. Please re-authorize.",
        )

    # incoming-webhook scope provides the user-selected channel during install.
    webhook = slack_resp.get("incoming_webhook", {})
    channel_id: str = webhook.get("channel_id", "")
    channel_name: str = webhook.get("channel", "")

    if not channel_id:
        raise HTTPException(
            status_code=400,
            detail="No channel selected. Please re-authorize and select a channel.",
        )

    cipher = EncryptionService(settings.encryption_key)
    bot_token_enc: bytes = cipher.encrypt(bot_token.encode())

    db = _get_supabase()

    # Resolve Supabase user UUID from Clerk user_id for the installed_by column.
    user_result = (
        db.table("users")
        .select("id")
        .eq("clerk_id", org.user_id)
        .limit(1)
        .execute()
    )
    db_user_id: str | None = user_result.data[0]["id"] if user_result.data else None

    # Upsert - one row per org; re-install to a new channel replaces the old row.
    try:
        db.table("slack_integrations").upsert(
            {
                "org_id": org.org_id,
                "workspace_id": workspace_id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "bot_token_enc": "\\x" + bot_token_enc.hex(),
                "installed_by": db_user_id,
            },
            on_conflict="org_id",
        ).execute()
    except Exception as exc:
        log.error("slack_upsert_failed", org_id=org.org_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to save Slack integration") from exc

    log.info(
        "slack_connected",
        org_id=org.org_id,
        workspace_id=workspace_id,
        channel_id=channel_id,
    )

    return SlackStatusResponse(
        connected=True,
        workspace_id=workspace_id,
        channel_name=channel_name,
        channel_id=channel_id,
    )


# ── PATCH /slack/settings ─────────────────────────────────────────────────────

@router.patch("/settings")
async def slack_settings(body: SlackSettingsUpdate, org: OrgDep) -> SlackStatusResponse:
    """Update mutable Slack notification preferences (currently: alerts_muted)."""
    db = _get_supabase()

    result = (
        db.table("slack_integrations")
        .select("workspace_id, channel_id, channel_name, created_at")
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No Slack integration found")

    db.table("slack_integrations").update(
        {"alerts_muted": body.alerts_muted}
    ).eq("org_id", org.org_id).execute()

    row = result.data[0]
    log.info("slack_settings_updated", org_id=org.org_id, alerts_muted=body.alerts_muted)

    return SlackStatusResponse(
        connected=True,
        workspace_id=row["workspace_id"],
        channel_name=row["channel_name"],
        channel_id=row["channel_id"],
        installed_at=row["created_at"],
        alerts_muted=body.alerts_muted,
    )


# ── POST /slack/disconnect ─────────────────────────────────────────────────────

@router.post("/disconnect", status_code=204)
async def slack_disconnect(org: OrgDep) -> None:
    """
    Revoke the Slack bot token and remove the integration.

    Token revocation is best-effort - the DB row is always deleted even if
    Slack returns an error (token already expired, workspace deleted, etc.).
    """
    db = _get_supabase()

    result = (
        db.table("slack_integrations")
        .select("bot_token_enc")
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="No Slack integration found")

    # Decrypt and revoke - best-effort, non-fatal on failure.
    raw_hex: str = result.data[0]["bot_token_enc"]
    try:
        cipher = EncryptionService(settings.encryption_key)
        # Supabase returns bytea as \x<hex>; strip the prefix before decoding.
        blob = bytes.fromhex(raw_hex.lstrip("\\x"))
        bot_token = cipher.decrypt(blob).decode()
        revoke_token(bot_token)
    except Exception as exc:
        log.warning("slack_revoke_decrypt_failed", org_id=org.org_id, error=str(exc))

    db.table("slack_integrations").delete().eq("org_id", org.org_id).execute()

    log.info("slack_disconnected", org_id=org.org_id)
