"""
Slack API helpers — thin wrappers over the Slack REST API using httpx.

No Slack SDK to stay within the no-new-large-deps constraint. The four
endpoints we need are simple JSON POST/GET calls:
  oauth.v2.access   — exchange auth code for bot token
  auth.revoke       — revoke token on disconnect
  chat.postMessage  — send a message to a channel

All functions are synchronous, matching the Celery worker context. Calling
them from async FastAPI routes is acceptable for low-frequency admin ops
(OAuth install, disconnect) — the minimal blocking is not a concern at
this traffic level.
"""

from typing import Any

import httpx
import structlog

log = structlog.get_logger()

_SLACK_API = "https://slack.com/api"
_TIMEOUT = 10.0  # seconds


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict[str, Any]:
    """
    Exchange a Slack OAuth v2 authorization code for a bot access token.

    Returns the full Slack API response dict on success.
    Raises ValueError with a human-readable message on failure (bad code,
    revoked app, network error, etc.).
    """
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{_SLACK_API}/oauth.v2.access",
                data={
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(client_id, client_secret),
            )
    except httpx.RequestError as exc:
        raise ValueError(f"Slack OAuth network error: {exc}") from exc

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Slack OAuth HTTP error: {exc.response.status_code}") from exc

    body: dict[str, Any] = resp.json()
    if not body.get("ok"):
        error_code = body.get("error", "unknown_error")
        raise ValueError(f"Slack OAuth failed: {error_code}")

    return body


def revoke_token(bot_token: str) -> None:
    """
    Revoke a Slack bot token via auth.revoke.

    Best-effort: logs a warning but does not raise on failure so that the
    local DB row is always deleted even if Slack is unreachable.
    """
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{_SLACK_API}/auth.revoke",
                headers={"Authorization": f"Bearer {bot_token}"},
            )
        body: dict[str, Any] = resp.json()
        if not body.get("ok"):
            log.warning("slack_revoke_failed", error=body.get("error"))
    except Exception as exc:
        # Non-fatal — Slack unreachable, token already expired, etc.
        log.warning("slack_revoke_error", error=str(exc))


def post_message(
    bot_token: str,
    channel_id: str,
    blocks: list[dict[str, Any]],
    fallback_text: str,
) -> None:
    """
    Post a Blocks-formatted message to a Slack channel.

    Raises ValueError on Slack API errors (channel_not_found, not_in_channel,
    token_revoked, etc.) so the caller (Celery task) can retry or log.
    """
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            f"{_SLACK_API}/chat.postMessage",
            headers={
                "Authorization": f"Bearer {bot_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "channel": channel_id,
                "blocks": blocks,
                "text": fallback_text,  # shown in notifications / unfurls
            },
        )

    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Slack postMessage HTTP error: {exc.response.status_code}") from exc

    body: dict[str, Any] = resp.json()
    if not body.get("ok"):
        error_code = body.get("error", "unknown_error")
        raise ValueError(f"Slack postMessage failed: {error_code}")
