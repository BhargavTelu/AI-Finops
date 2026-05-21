"""
Webhook gap tests.

Gap-27 (high): Svix multi-signature header — one invalid + one valid → 200.
               All invalid → 400. No 'v1,' prefix → 400.
"""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_WEBHOOK_SECRET = "whsec_s/bK18MLB7SHB8pfU0IhurJlTY22zI82"
_SECRET_KEY = base64.b64decode(_WEBHOOK_SECRET.removeprefix("whsec_"))


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_valid_signature(svix_id: str, svix_timestamp: str, body: bytes) -> str:
    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    digest = base64.b64encode(
        hmac.new(_SECRET_KEY, signed, hashlib.sha256).digest()
    ).decode()
    return f"v1,{digest}"


def _post_with_signature(
    payload: dict,
    svix_signature: str,
    svix_id: str = "msg_gap27_test",
    ts_override: int | None = None,
) -> MagicMock:
    body = json.dumps(payload).encode()
    ts_str = str(ts_override if ts_override is not None else int(time.time()))
    db = MagicMock()
    db.table.return_value = db
    with patch("api.routers.webhooks._service_db", return_value=db):
        return client.post(
            "/api/webhooks/clerk",
            content=body,
            headers={
                "svix-id": svix_id,
                "svix-timestamp": ts_str,
                "svix-signature": svix_signature,
                "Content-Type": "application/json",
            },
        )


# ── Gap-27: Svix multi-signature header ───────────────────────────────────────

class TestSvixMultipleSignatures:
    """
    Gap-27 (high): Svix sends multiple space-separated signatures during key rotation.
    _verify_svix_signature uses any(hmac.compare_digest(...)) — any single valid sig passes.
    """

    def test_single_valid_signature_passes(self) -> None:
        """Baseline: a single correct v1, signature is accepted."""
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        ts_str = str(int(time.time()))
        sig = _make_valid_signature("msg_gap27_test", ts_str, body)

        db = MagicMock()
        db.table.return_value = db
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = client.post(
                "/api/webhooks/clerk",
                content=body,
                headers={
                    "svix-id": "msg_gap27_test",
                    "svix-timestamp": ts_str,
                    "svix-signature": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200

    def test_first_invalid_second_valid_signature_passes(self) -> None:
        """
        Gap-27: Two space-separated sigs where the first is wrong and the second
        is valid → 200. This is the key rotation scenario Svix uses.
        """
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        ts_str = str(int(time.time()))

        valid_sig = _make_valid_signature("msg_gap27_test", ts_str, body)
        invalid_sig = "v1,aGVsbG8gd29ybGQ="  # base64("hello world") — wrong

        # Space-separated: invalid first, valid second
        combined = f"{invalid_sig} {valid_sig}"

        db = MagicMock()
        db.table.return_value = db
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = client.post(
                "/api/webhooks/clerk",
                content=body,
                headers={
                    "svix-id": "msg_gap27_test",
                    "svix-timestamp": ts_str,
                    "svix-signature": combined,
                    "Content-Type": "application/json",
                },
            )

        assert resp.status_code == 200, (
            f"Gap-27: Expected 200 when at least one valid sig is present. "
            f"Got {resp.status_code}. Multi-sig rotation must be supported."
        )
        assert resp.json() == {"received": True}

    def test_three_sigs_only_last_valid_passes(self) -> None:
        """Three sigs — first two wrong, third valid → 200."""
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        ts_str = str(int(time.time()))

        valid_sig = _make_valid_signature("msg_gap27_test", ts_str, body)
        combined = f"v1,wrong1== v1,wrong2== {valid_sig}"

        db = MagicMock()
        db.table.return_value = db
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = client.post(
                "/api/webhooks/clerk",
                content=body,
                headers={
                    "svix-id": "msg_gap27_test",
                    "svix-timestamp": ts_str,
                    "svix-signature": combined,
                    "Content-Type": "application/json",
                },
            )

        assert resp.status_code == 200

    def test_all_invalid_signatures_returns_400(self) -> None:
        """Multiple sigs, all wrong → 400 with 'signature' in detail."""
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        ts_str = str(int(time.time()))
        combined = "v1,wrong1 v1,wrong2 v1,wrong3"

        resp = client.post(
            "/api/webhooks/clerk",
            content=body,
            headers={
                "svix-id": "msg_gap27_test",
                "svix-timestamp": ts_str,
                "svix-signature": combined,
                "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 400
        assert "signature" in resp.json()["detail"].lower()

    def test_no_v1_prefix_sigs_filtered_out_returns_400(self) -> None:
        """
        Signatures without 'v1,' prefix are filtered from the provided list.
        If no v1, sigs remain, the provided list is empty → 400.
        """
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        ts_str = str(int(time.time()))
        # All sigs use wrong prefix (v2,) — none match the v1, filter
        non_v1_sigs = "v2,somesig v3,anothersig"

        resp = client.post(
            "/api/webhooks/clerk",
            content=body,
            headers={
                "svix-id": "msg_gap27_test",
                "svix-timestamp": ts_str,
                "svix-signature": non_v1_sigs,
                "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 400

    def test_duplicate_valid_signatures_still_200(self) -> None:
        """Same valid signature repeated (edge case) → still 200."""
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        ts_str = str(int(time.time()))

        valid_sig = _make_valid_signature("msg_gap27_test", ts_str, body)
        combined = f"{valid_sig} {valid_sig}"

        db = MagicMock()
        db.table.return_value = db
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = client.post(
                "/api/webhooks/clerk",
                content=body,
                headers={
                    "svix-id": "msg_gap27_test",
                    "svix-timestamp": ts_str,
                    "svix-signature": combined,
                    "Content-Type": "application/json",
                },
            )

        assert resp.status_code == 200

    def test_stale_timestamp_with_valid_sig_rejected(self) -> None:
        """
        Even if the signature is valid, a stale timestamp (> 5 min) must be rejected.
        Replay attack protection takes priority over signature validity.
        """
        payload = {"type": "user.updated", "data": {}}
        body = json.dumps(payload).encode()
        old_ts = int(time.time()) - 400  # > 5 minutes old
        old_ts_str = str(old_ts)

        # Valid signature computed with the old timestamp
        valid_old_sig = _make_valid_signature("msg_gap27_test", old_ts_str, body)

        resp = client.post(
            "/api/webhooks/clerk",
            content=body,
            headers={
                "svix-id": "msg_gap27_test",
                "svix-timestamp": old_ts_str,
                "svix-signature": valid_old_sig,
                "Content-Type": "application/json",
            },
        )

        assert resp.status_code == 400
        assert "tolerance" in resp.json()["detail"].lower()
