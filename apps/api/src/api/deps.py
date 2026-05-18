import json
import time
from typing import Annotated, Any

import httpx
import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status

from api.config import settings

log = structlog.get_logger()


# ── JWKS cache ────────────────────────────────────────────────────────────────
# Simple in-memory cache keyed by kid. Each FastAPI worker process maintains
# its own copy — fine at this scale. Refreshed every hour or on unknown kid
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
    # Any is unavoidable here — JWKS is untyped JSON from an external endpoint.
    keys: list[dict[str, Any]] = resp.json().get("keys", [])  # type: ignore[assignment]
    return {k["kid"]: k for k in keys}


async def _get_jwks() -> dict[str, dict[str, Any]]:
    """Return cached JWKS, refreshing if stale."""
    now = time.monotonic()
    if not _cache.keys or now - _cache.fetched_at > _JWKS_TTL:
        _cache.keys = await _fetch_jwks()
        _cache.fetched_at = now
    return _cache.keys


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
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.removeprefix("Bearer ")

    # Read the header without verifying the signature — we need kid to look
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
    # annotation here — PyJWT does not expose a narrower public type.
    public_key: Any = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))  # type: ignore[attr-defined]

    try:
        # Clerk session tokens don't carry an aud claim — disable that check.
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
    org_id: str | None = claims.get("org_id")

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing sub claim")
    if not org_id:
        # org_id is absent when the user has no active organization in their
        # Clerk session. The frontend must set org context before calling
        # any protected API routes (see docs/setup.md § Clerk session config).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active organization — activate an org in the Clerk session",
        )

    return OrgContext(user_id=user_id, org_id=org_id)


# Shorthand for route signatures: `org: OrgDep`
OrgDep = Annotated[OrgContext, Depends(_require_org)]
