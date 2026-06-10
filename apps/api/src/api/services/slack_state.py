"""
HMAC-signed OAuth state for the Slack install flow.

The state is generated server-side for the authenticated org and validated
in the OAuth callback against the caller's JWT org. Without this, an attacker
could complete OAuth against their own workspace, then trick a victim admin
into POSTing the attacker's code - silently routing the victim org's spend
digests to the attacker's Slack.

Stateless by design: no Redis/DB row. The MAC key is derived from the
AES encryption key with domain separation, so no extra secret is needed.
Format: "<expires_unix>:<hex hmac-sha256 over '<org_id>:<expires_unix>'>".
"""

import base64
import hashlib
import hmac
import time

_STATE_TTL_SECONDS = 900  # 15 minutes - generous for an OAuth round-trip
_DOMAIN = b"slack-oauth-state:"


def _mac_key(encryption_key_b64: str) -> bytes:
    raw = base64.b64decode(encryption_key_b64)
    return hashlib.sha256(_DOMAIN + raw).digest()


def generate_state(org_id: str, encryption_key_b64: str) -> str:
    """Return a signed state token bound to org_id, valid for 15 minutes."""
    expires = int(time.time()) + _STATE_TTL_SECONDS
    msg = f"{org_id}:{expires}".encode()
    sig = hmac.new(_mac_key(encryption_key_b64), msg, hashlib.sha256).hexdigest()
    return f"{expires}:{sig}"


def validate_state(state: str, org_id: str, encryption_key_b64: str) -> bool:
    """True iff state was signed for this org_id and has not expired."""
    try:
        expires_str, sig = state.split(":", 1)
        expires = int(expires_str)
        key = _mac_key(encryption_key_b64)
    except (ValueError, TypeError):
        return False
    if time.time() > expires:
        return False
    expected = hmac.new(key, f"{org_id}:{expires}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
