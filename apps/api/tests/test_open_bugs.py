"""
Open bug regression tests.

Gap-16 (high):   BUG-02: _handle_membership_created uses .single() - if the parent
                 user/org row is missing, PostgREST raises an exception that propagates
                 as 500 from the wrong place (KeyError, not the explicit HTTPException).
Gap-17 (medium): BUG-03: _get_slack_channel uses lstrip("\\x") instead of removeprefix.
                 For hex-encoded AES ciphertext this is functionally safe today, but
                 lstrip strips any leading occurrence of the characters, not the prefix.
"""

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.encryption import EncryptionService

client = TestClient(app)

# Webhook test secret matches .env
_WEBHOOK_SECRET = "whsec_s/bK18MLB7SHB8pfU0IhurJlTY22zI82"
_SECRET_KEY = base64.b64decode(_WEBHOOK_SECRET.removeprefix("whsec_"))


def _make_signature(svix_id: str, svix_timestamp: str, body: bytes) -> str:
    import hashlib
    import hmac as _hmac

    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    digest = base64.b64encode(
        _hmac.new(_SECRET_KEY, signed, hashlib.sha256).digest()
    ).decode()
    return f"v1,{digest}"


def _post_webhook(payload: dict) -> MagicMock:
    import time as _time

    body = json.dumps(payload).encode()
    ts_str = str(int(_time.time()))
    sig = _make_signature("msg_bug_test", ts_str, body)
    return client.post(
        "/api/webhooks/clerk",
        content=body,
        headers={
            "svix-id": "msg_bug_test",
            "svix-timestamp": ts_str,
            "svix-signature": sig,
            "Content-Type": "application/json",
        },
    )


# ── Gap-16: BUG-02 - .single() on missing parent row ─────────────────────────

class TestMembershipCreatedSingleBug:
    """
    Gap-16 (high): BUG-02 - _handle_membership_created uses .single().execute()
    which raises postgrest.exceptions.APIError (or similar) when no row found.
    This exception propagates unhandled through the route, yielding 500 from a
    KeyError rather than the intended explicit HTTPException with a clear message.
    """

    def _membership_payload(self) -> dict:
        return {
            "type": "organizationMembership.created",
            "data": {
                "organization": {"id": "org_clerk_123"},
                "public_user_data": {"user_id": "user_clerk_missing"},
                "role": "org:admin",
            },
        }

    def test_missing_user_row_single_raises_returns_5xx(self) -> None:
        """
        When .single().execute() raises (simulating PostgREST PGRST116 - no rows),
        the route must return 5xx so Svix retries the delivery.

        Current behavior: KeyError from user_resp.data["id"] → 500 (wrong place).
        Expected behavior: an explicit HTTPException(500) from the not-found check.
        Fix: replace .single() with .limit(1), check result.data, raise 500 explicitly.
        """
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.single.return_value = db
        # Simulate PostgREST raising when no row found
        db.execute.side_effect = Exception("PGRST116: no rows found")

        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook(self._membership_payload())

        assert resp.status_code >= 500, (
            f"Gap-16/BUG-02: Expected 5xx for missing parent row. "
            f"Got {resp.status_code}. Svix retries on 5xx only."
        )

    def test_user_row_present_membership_created_succeeds(self) -> None:
        """Baseline: when both user and org rows exist, membership is upserted."""
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.upsert.return_value = db
        db.single.return_value = db
        db.execute.side_effect = [
            MagicMock(data={"id": "user-uuid"}),   # users.single()
            MagicMock(data={"id": "org-uuid"}),    # organizations.single()
            MagicMock(data=[]),                     # upsert
        ]

        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook(self._membership_payload())

        assert resp.status_code == 200
        db.upsert.assert_called_once()

    def test_data_dict_with_error_code_not_caught_by_falsy_check(self) -> None:
        """
        If Supabase returns a PostgREST error as a dict (not a list), the check
        'if not user_resp.data' is True for a non-empty error dict - the guard fails.
        Document: the fix is to check for list type or use .limit(1).
        """
        # Simulate the case where execute() returns {error dict} not [] or [row]
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.single.return_value = db
        db.execute.side_effect = [
            MagicMock(data={"code": "PGRST116", "message": "The result contains 0 rows"}),
            MagicMock(data={"id": "org-uuid"}),
        ]

        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook(self._membership_payload())

        # With a non-empty dict (truthy), the `if not user_resp.data` guard passes
        # and then user_resp.data["id"] raises KeyError → 500 from wrong location.
        assert resp.status_code >= 400, (
            "Gap-16: Expected failure when user_resp.data is an error dict (not a list row)."
        )


# ── Gap-17: BUG-03 - lstrip vs removeprefix in _get_slack_channel ────────────

class TestSlackTokenDecryptionLstrip:
    """
    Gap-17 (medium): BUG-03 - notifications._get_slack_channel uses lstrip("\\x")
    to strip the Supabase bytea \\x prefix. lstrip strips individual CHARACTERS
    from the set {\\, x}, not the exact prefix string. For valid hex data (0-9, a-f)
    this is safe today. Regression test to ensure decryption still works correctly.
    """

    _KEY_B64 = base64.b64encode(b"\xcc" * 32).decode()
    _CIPHER = EncryptionService(_KEY_B64)

    def test_lstrip_correctly_strips_supabase_bytea_prefix(self) -> None:
        """
        lstrip("\\x") on "\\xdeadbeef" correctly strips both \\ and x,
        leaving the hex payload. Verify this is equivalent to removeprefix("\\x").
        """
        test_cases = [
            "\\xdeadbeef",
            "\\x0011aabb",
            "\\xffeeddcc",
        ]
        for raw_hex in test_cases:
            via_lstrip = raw_hex.lstrip("\\x")
            via_removeprefix = raw_hex.removeprefix("\\x")
            assert via_lstrip == via_removeprefix, (
                f"BUG-03: lstrip and removeprefix differ for {raw_hex!r}: "
                f"lstrip={via_lstrip!r}, removeprefix={via_removeprefix!r}"
            )

    def test_round_trip_encrypt_decrypt_via_lstrip(self) -> None:
        """
        Encrypt a bot token, format as Supabase bytea (\\x prefix),
        then decrypt using the lstrip path used in _get_slack_channel.
        Verifies end-to-end correctness.
        """
        original_token = b"xoxb-test-bot-token-12345"
        ciphertext = self._CIPHER.encrypt(original_token)
        raw_hex = "\\x" + ciphertext.hex()

        # Simulate what _get_slack_channel does
        stripped = raw_hex.lstrip("\\x")
        blob = bytes.fromhex(stripped)
        recovered = self._CIPHER.decrypt(blob)

        assert recovered == original_token, (
            f"BUG-03: Round-trip encrypt/decrypt via lstrip failed. "
            f"Expected {original_token!r}, got {recovered!r}."
        )

    def test_lstrip_differs_from_removeprefix_for_malformed_prefix(self) -> None:
        """
        Document the semantic difference between lstrip and removeprefix:
        lstrip strips ALL leading chars from the set; removeprefix strips the prefix once.
        For a string like 'x' + hex (missing backslash), lstrip over-strips.
        removeprefix would leave the string unchanged.
        """
        # Edge case: stored without the leading backslash (malformed)
        malformed = "xdeadbeef"  # only 'x' prefix, no backslash
        via_lstrip = malformed.lstrip("\\x")      # strips 'x' → "deadbeef" (WRONG)
        via_removeprefix = malformed.removeprefix("\\x")  # no match → "xdeadbeef" (correct)

        assert via_lstrip != via_removeprefix, (
            "BUG-03: Expected lstrip and removeprefix to differ for malformed prefix - "
            "this test documents the semantic difference."
        )
        assert via_lstrip == "deadbeef"         # lstrip silently over-strips
        assert via_removeprefix == "xdeadbeef"  # removeprefix correctly leaves it unchanged

    def test_get_slack_channel_decrypts_correctly(self) -> None:
        """
        Integration: _get_slack_channel correctly decrypts a bot token
        formatted as Supabase bytea hex.
        """
        from api.workers.notifications import _get_slack_channel

        original_token = b"xoxb-real-bot-token"
        ciphertext = self._CIPHER.encrypt(original_token)
        raw_hex = "\\x" + ciphertext.hex()

        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.limit.return_value = db
        db.execute.return_value = MagicMock(
            data=[{"bot_token_enc": raw_hex, "channel_id": "C1234", "alerts_muted": False}]
        )

        with patch("api.workers.notifications.settings") as ms:
            ms.encryption_key = self._KEY_B64
            result = _get_slack_channel(db, "org-123")

        assert result is not None
        bot_token, channel_id, alerts_muted = result
        assert bot_token == original_token.decode()
        assert channel_id == "C1234"
        assert alerts_muted is False
