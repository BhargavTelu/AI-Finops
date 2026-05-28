import json
import time
from typing import Annotated, Any

import httpx
import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status
from supabase import create_client

from api.config import settings

log = structlog.get_logger()


# ── JWKS cache ────────────────────────────────────────────────────────────────
# Simple in-memory cache keyed by kid. Each FastAPI worker process maintains
# its own copy - fine at this scale. Refreshed every hour or on unknown kid
# (handles Clerk key rotation without a restart).
class _JwksCache:
    def __init__(self) -> None:
        self.keys: dict[str, dict[str, Any]] = {}
        self.fetched_at: float = 0.0


_cache = _JwksCache()
_JWKS_TTL = 3600.0  # seconds


async def _fetch_jwks() -> dict[str, dict[str, Any]]:
    """Fetch Clerk's JWKS and return a {kid: jwk} mapping."""
    url = f"{settings.clerk_issuer}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    # Any is unavoidable here - JWKS is untyped JSON from an external endpoint.
    keys: list[dict[str, Any]] = resp.json().get("keys", [])  # type: ignore[assignment]
    return {k["kid"]: k for k in keys}


async def _get_jwks() -> dict[str, dict[str, Any]]:
    """Return cached JWKS, refreshing if stale."""
    now = time.monotonic()
    if not _cache.keys or now - _cache.fetched_at > _JWKS_TTL:
        _cache.keys = await _fetch_jwks()
        _cache.fetched_at = now
    return _cache.keys


def _resolve_org_id_from_clerk_claim(o_claim: Any) -> str | None:
    """
    Clerk v6 consolidates org data into the 'o' claim instead of a flat
    org_id string. Extract the Clerk org ID and resolve the Supabase UUID
    via a DB lookup.

    This fallback fires when the session token hasn't been customised to
    include org_id = {{org.public_metadata.db_id}} directly. To eliminate
    this DB round-trip: Clerk Dashboard → Configure → Sessions →
    Edit default session token → add {"org_id": "{{org.public_metadata.db_id}}"}.
    """
    if not isinstance(o_claim, dict):
        return None
    clerk_org_id: str | None = o_claim.get("id")
    if not clerk_org_id:
        return None
    db = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = (
        db.table("organizations")
        .select("id")
        .eq("clerk_id", clerk_org_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]  # type: ignore[no-any-return]
    return None


# ── OrgContext ─────────────────────────────────────────────────────────────────
class OrgContext:
    """Extracted from Clerk JWT. Injected into every protected route."""

    def __init__(self, user_id: str, org_id: str) -> None:
        self.user_id = user_id
        self.org_id = org_id


# ── Dependency ─────────────────────────────────────────────────────────────────
async def _require_org(
    authorization: Annotated[str | None, Header()] = None,
) -> OrgContext:
    """
    Validate Clerk Bearer token and extract org context.

    Verifies the RS256 signature against Clerk's JWKS endpoint.
    Enforces issuer and expiry. Extracts sub (user_id) and org_id.
    The JWKS is cached in memory and refreshed hourly or on unknown kid.

    org_id resolution order:
      1. Direct claim: org_id = {{org.public_metadata.db_id}} (custom session token)
      2. Clerk v6 'o' claim fallback: looks up Supabase UUID by Clerk org ID
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.removeprefix("Bearer ")

    # Read the header without verifying the signature - we need kid to look
    # up the right public key before we can verify anything.
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed JWT")

    if header.get("alg") != "RS256":
        # Clerk session tokens are always RS256. Reject anything else to
        # prevent algorithm confusion attacks.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unexpected JWT algorithm",
        )

    kid: str | None = header.get("kid")

    # Look up the public key. On cache miss, refresh once (handles key rotation).
    jwks = await _get_jwks()
    jwk = jwks.get(kid or "")
    if not jwk:
        _cache.keys = {}  # force one refresh
        jwks = await _get_jwks()
        jwk = jwks.get(kid or "")
    if not jwk:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown signing key",
        )

    # RSAAlgorithm.from_jwk returns a union of key types; Any is the correct
    # annotation here - PyJWT does not expose a narrower public type.
    public_key: Any = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))  # type: ignore[attr-defined]

    try:
        # Clerk session tokens don't carry an aud claim - disable that check.
        claims: dict[str, Any] = jwt.decode(  # type: ignore[assignment]
            token,
            public_key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")
    except jwt.InvalidTokenError as exc:
        log.warning("jwt_verification_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id: str | None = claims.get("sub")
    # Prefer the custom session-token claim (Supabase UUID); fall back to
    # resolving via Clerk v6's compressed 'o' claim if not present.
    org_id: str | None = claims.get("org_id") or _resolve_org_id_from_clerk_claim(claims.get("o"))

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing sub claim")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active organization - activate an org in the Clerk session",
        )

    return OrgContext(user_id=user_id, org_id=org_id)


# Shorthand for route signatures: `org: OrgDep`
OrgDep = Annotated[OrgContext, Depends(_require_org)]


async def _require_admin_org(org: OrgDep) -> OrgContext:
    """
    Extends _require_org with an admin role check.

    Queries organization_members to verify the authenticated user holds the
    'admin' role in their active org. Raises 403 for non-admins.

    We check the DB rather than a JWT claim to avoid requiring a Clerk session
    template change. The query is a single indexed primary-key lookup
    (UNIQUE on org_id, user_id) so it adds one fast round-trip.
    """
    db = create_client(settings.supabase_url, settings.supabase_service_role_key)

    # Resolve the Supabase user UUID from the Clerk sub claim (stored in users.clerk_id)
    user_result = (
        db.table("users")
        .select("id")
        .eq("clerk_id", org.user_id)
        .limit(1)
        .execute()
    )
    if not user_result.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not found")

    supabase_user_id: str = user_result.data[0]["id"]

    member_result = (
        db.table("organization_members")
        .select("role")
        .eq("org_id", org.org_id)
        .eq("user_id", supabase_user_id)
        .limit(1)
        .execute()
    )
    if not member_result.data or member_result.data[0].get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return org


# Shorthand for admin-only routes: `org: AdminOrgDep`
AdminOrgDep = Annotated[OrgContext, Depends(_require_admin_org)]
