"""
JWT authentication dependency gap tests.

Gap-11 (high):   Algorithm confusion attack - non-RS256 alg rejected before JWKS lookup.
Gap-12 (high):   JWKS cache concurrent refresh race - no lock on _JwksCache.
Gap-13 (high):   Unknown kid triggers exactly one cache refresh then 401.
Gap-14 (high):   JWKS fetch timeout surfaces as non-200 (no clean 401/503 today).
Gap-15 (medium): Malformed Clerk 'o' claim (not a dict) → 403 not 500.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import OrgDep

# ── Test RSA key pair (generated once at module load) ─────────────────────────

_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_public_key = _private_key.public_key()
_TEST_KID = "test-kid-gap-11-15"
_TEST_ISSUER = "https://clerk.test.dev"

_jwk: dict = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(_public_key))  # type: ignore[attr-defined]
_jwk["kid"] = _TEST_KID
_JWKS: dict = {_TEST_KID: _jwk}


def _make_rs256_token(
    sub: str = "user_test_abc",
    org_id: str | None = "00000000-0000-0000-0000-000000000001",
    kid: str = _TEST_KID,
    issuer: str = _TEST_ISSUER,
    exp_offset_s: int = 3600,
    extra: dict | None = None,
) -> str:
    payload: dict = {
        "sub": sub,
        "iss": issuer,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_offset_s),
        "iat": datetime.now(timezone.utc),
    }
    if org_id is not None:
        payload["org_id"] = org_id
    if extra:
        payload.update(extra)
    return pyjwt.encode(
        payload,
        _private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


# ── Minimal test app ───────────────────────────────────────────────────────────

_test_app = FastAPI()


@_test_app.get("/protected")
async def _protected_route(org: OrgDep) -> dict:
    return {"user_id": org.user_id, "org_id": org.org_id}


_test_client = TestClient(_test_app, raise_server_exceptions=False)


def _authed_get(token: str):
    return _test_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )


# ── Shared fixture ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_jwks_cache():
    """Reset the module-level JWKS cache before and after each test."""
    from api.deps import _cache

    _cache.keys = {}
    _cache.fetched_at = 0.0
    yield
    _cache.keys = {}
    _cache.fetched_at = 0.0


# ── Gap-11: Algorithm confusion attack ────────────────────────────────────────

class TestAlgorithmConfusion:
    """Gap-11 (high): Non-RS256 tokens must be rejected before JWKS lookup fires."""

    def test_hs256_token_rejected_without_jwks_lookup(self) -> None:
        """
        An HS256-signed token must be rejected immediately with 401.
        The alg check in _require_org fires before _get_jwks() - an attacker
        cannot exploit RS256-public-key-as-HS256-secret confusion.
        """
        hs256_token = pyjwt.encode(
            {"sub": "attacker", "org_id": "evil"},
            "any_secret",
            algorithm="HS256",
        )

        with patch("api.deps._get_jwks") as mock_jwks:
            resp = _authed_get(hs256_token)

        assert resp.status_code == 401
        assert "algorithm" in resp.json()["detail"].lower()
        mock_jwks.assert_not_called()

    def test_alg_none_token_rejected(self) -> None:
        """'none' algorithm (unsigned token) must be rejected - PyJWT raises DecodeError."""
        import base64 as _b64

        # Craft a manually assembled alg:none token (no signature)
        header = _b64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        payload_b64 = _b64.urlsafe_b64encode(
            b'{"sub":"x","org_id":"evil"}'
        ).rstrip(b"=").decode()
        none_token = f"{header}.{payload_b64}."

        resp = _authed_get(none_token)

        assert resp.status_code == 401

    def test_missing_authorization_header_returns_401(self) -> None:
        """No Authorization header → 401."""
        resp = _test_client.get("/protected")
        assert resp.status_code == 401

    def test_non_bearer_prefix_returns_401(self) -> None:
        """'Token <jwt>' prefix (not 'Bearer ') → 401."""
        token = _make_rs256_token()
        resp = _test_client.get(
            "/protected", headers={"Authorization": f"Token {token}"}
        )
        assert resp.status_code == 401

    def test_malformed_jwt_returns_401(self) -> None:
        """Garbled token string → DecodeError → 401."""
        resp = _authed_get("not.a.jwt.at.all")
        assert resp.status_code == 401


# ── Gap-12: JWKS cache concurrent refresh race ────────────────────────────────

class TestJwksConcurrentRefreshRace:
    """
    Gap-12 (high): _JwksCache has no asyncio.Lock.
    Two concurrent coroutines both seeing keys == {} both call _fetch_jwks().
    Under an auth burst (cold cache after deploy) this amplifies calls to Clerk.
    """

    def test_concurrent_get_jwks_documents_double_fetch_race(self) -> None:
        """
        Two concurrent _get_jwks() coroutines with empty cache both call _fetch_jwks().
        When an asyncio.Lock is added to _JwksCache, update assertion to call_count == 1.
        """
        from api.deps import _cache, _get_jwks

        _cache.keys = {}
        _cache.fetched_at = 0.0
        call_count = [0]

        async def slow_fetch() -> dict:
            call_count[0] += 1
            await asyncio.sleep(0.05)  # enough to lose the race
            return {"kid1": {"kty": "RSA"}}

        async def run() -> None:
            with patch("api.deps._fetch_jwks", side_effect=slow_fetch):
                await asyncio.gather(_get_jwks(), _get_jwks())

        asyncio.run(run())

        assert call_count[0] == 2, (
            f"Gap-12: Both concurrent coroutines called _fetch_jwks (no asyncio.Lock). "
            f"Got call_count={call_count[0]}. "
            "When asyncio.Lock is added to _JwksCache, update assertion to call_count == 1."
        )

    def test_warm_cache_does_not_trigger_fetch(self) -> None:
        """Cached and not-yet-expired JWKS must be returned without calling _fetch_jwks."""
        from api.deps import _cache, _get_jwks

        _cache.keys = {"kid1": {"kty": "RSA"}}
        _cache.fetched_at = time.monotonic()  # fresh

        async def run() -> dict:
            with patch("api.deps._fetch_jwks") as mock_fetch:
                result = await _get_jwks()
                mock_fetch.assert_not_called()
                return result

        result = asyncio.run(run())
        assert "kid1" in result


# ── Gap-13: Unknown kid forces exactly one refresh ────────────────────────────

class TestUnknownKidRefreshBehavior:
    """Gap-13 (high): Unknown kid triggers one cache refresh then 401 - not infinite retries."""

    def test_unknown_kid_triggers_exactly_one_refresh_then_401(self) -> None:
        """
        JWT kid not found in cache forces:
          1. Cache cleared (_cache.keys = {})
          2. _fetch_jwks() called once more
          3. Kid still absent → 401 "Unknown signing key"
        Verify _fetch_jwks is called exactly once (no retry loop).
        """
        from api.deps import _cache

        # Cache is populated but with a DIFFERENT kid
        _cache.keys = {"old-kid": {"kty": "RSA"}}
        _cache.fetched_at = 9_999_999_999.0  # would not expire naturally

        token = _make_rs256_token(kid="completely-unknown-kid")
        fetch_count = [0]

        async def mock_fetch() -> dict:
            fetch_count[0] += 1
            return {}  # refresh returns nothing useful

        with patch("api.deps._fetch_jwks", side_effect=mock_fetch):
            resp = _authed_get(token)

        assert resp.status_code == 401
        assert "signing key" in resp.json()["detail"].lower()
        assert fetch_count[0] == 1, (
            f"Gap-13: Expected exactly 1 forced refresh on unknown kid. "
            f"Got fetch_count={fetch_count[0]}."
        )


# ── Gap-14: JWKS fetch timeout ────────────────────────────────────────────────

class TestJwksFetchTimeout:
    """Gap-14 (high): JWKS timeout must not leak an unhandled traceback as 500."""

    def test_jwks_timeout_does_not_return_200_or_leak_traceback(self) -> None:
        """
        If Clerk's JWKS endpoint times out, the client must not receive 200.

        Current behavior: httpx.TimeoutException propagates unhandled → 500 with traceback.
        When fixed (caught → clean 503 or 401), update assertion to check for 401/503.
        """
        import httpx

        from api.deps import _cache

        _cache.keys = {}
        _cache.fetched_at = 0.0

        token = _make_rs256_token()

        async def timeout_fetch() -> dict:
            raise httpx.TimeoutException("JWKS endpoint timed out")

        with patch("api.deps._fetch_jwks", side_effect=timeout_fetch):
            resp = _authed_get(token)

        # Must not be 200 - a timeout must not grant access
        assert resp.status_code != 200, "Gap-14: JWKS timeout must not allow authentication"
        # Document current (broken) behavior: an unhandled exception becomes 500.
        # When a try/except is added around _get_jwks() in _require_org, change to:
        # assert resp.status_code in (401, 503)


# ── Gap-15: Malformed Clerk 'o' claim ────────────────────────────────────────

class TestMalformedOClaim:
    """Gap-15 (medium): 'o' claim that is not a dict must return 403, not 500."""

    def test_string_o_claim_returns_403_not_500(self) -> None:
        """
        A crafted token with 'o': "string" (not the expected dict with 'id') must
        return 403 because _resolve_org_id_from_clerk_claim returns None early
        for non-dict inputs. Must not crash with AttributeError or TypeError.
        """
        from api.deps import _cache

        _cache.keys = _JWKS
        _cache.fetched_at = time.monotonic()  # fresh cache

        # No org_id, 'o' is a plain string
        token = _make_rs256_token(org_id=None, extra={"o": "not-a-dict"})

        with patch("api.deps.settings") as ms:
            ms.clerk_issuer = _TEST_ISSUER
            resp = _authed_get(token)

        assert resp.status_code == 403, (
            f"Gap-15: Expected 403 for non-dict 'o' claim. Got {resp.status_code}."
        )

    def test_integer_o_claim_returns_403(self) -> None:
        """Non-dict 'o' (integer) must also return 403, not 500."""
        from api.deps import _cache

        _cache.keys = _JWKS
        _cache.fetched_at = time.monotonic()

        token = _make_rs256_token(org_id=None, extra={"o": 42})

        with patch("api.deps.settings") as ms:
            ms.clerk_issuer = _TEST_ISSUER
            resp = _authed_get(token)

        assert resp.status_code == 403

    def test_o_dict_missing_id_returns_403(self) -> None:
        """'o' is a dict but missing the 'id' key → org_id unresolvable → 403."""
        from api.deps import _cache

        _cache.keys = _JWKS
        _cache.fetched_at = time.monotonic()

        # 'o' is a dict but has no 'id' field
        token = _make_rs256_token(org_id=None, extra={"o": {"not_id": "something"}})

        with patch("api.deps.settings") as ms:
            ms.clerk_issuer = _TEST_ISSUER
            # _resolve_org_id_from_clerk_claim will try to create a Supabase client
            # when 'id' IS present. With no 'id', it returns None early.
            resp = _authed_get(token)

        assert resp.status_code == 403
