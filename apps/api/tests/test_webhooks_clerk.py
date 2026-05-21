"""
Webhook security and event handler tests for POST /api/webhooks/clerk.
TC-WH-01 to TC-WH-11.

Svix signature verification uses HMAC-SHA256:
  key = base64.b64decode(webhook_secret.removeprefix("whsec_"))
  signed_payload = f"{svix_id}.{svix_timestamp}.{body_bytes}"
  expected = base64.b64encode(hmac.new(key, signed_payload, sha256).digest())
"""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# Use the webhook secret from .env (tests run against real settings)
_WEBHOOK_SECRET = "whsec_s/bK18MLB7SHB8pfU0IhurJlTY22zI82"
_SECRET_KEY = base64.b64decode(_WEBHOOK_SECRET.removeprefix("whsec_"))


# ── Signature helpers ──────────────────────────────────────────────────────────

def _make_signature(svix_id: str, svix_timestamp: str, body: bytes) -> str:
    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    digest = base64.b64encode(hmac.new(_SECRET_KEY, signed, hashlib.sha256).digest()).decode()
    return f"v1,{digest}"


def _svix_headers(body: bytes, ts: int | None = None, svix_id: str = "msg_test_001") -> dict:
    ts_str = str(ts if ts is not None else int(time.time()))
    sig = _make_signature(svix_id, ts_str, body)
    return {
        "svix-id": svix_id,
        "svix-timestamp": ts_str,
        "svix-signature": sig,
        "Content-Type": "application/json",
    }


def _post_webhook(payload: dict, ts: int | None = None, bad_sig: bool = False) -> MagicMock:
    body = json.dumps(payload).encode()
    headers = _svix_headers(body, ts)
    if bad_sig:
        headers["svix-signature"] = "v1,aGVsbG8gd29ybGQ="  # wrong signature
    return client.post("/api/webhooks/clerk", content=body, headers=headers)


# ── Signature verification ─────────────────────────────────────────────────────

class TestSvixSignatureVerification:
    def test_valid_signature_passes(self) -> None:  # TC-WH-01
        payload = {"type": "user.updated", "data": {}}
        db = MagicMock()
        db.table.return_value = db
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook(payload)
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_wrong_signature_rejected(self) -> None:  # TC-WH-02
        payload = {"type": "user.updated", "data": {}}
        resp = _post_webhook(payload, bad_sig=True)
        assert resp.status_code == 400
        assert "signature" in resp.json()["detail"].lower()

    def test_stale_timestamp_rejected(self) -> None:  # TC-WH-03
        old_ts = int(time.time()) - 400  # > 5 minutes ago
        payload = {"type": "user.updated", "data": {}}
        resp = _post_webhook(payload, ts=old_ts)
        assert resp.status_code == 400
        assert "tolerance" in resp.json()["detail"].lower()

    def test_non_integer_timestamp_rejected(self) -> None:  # TC-WH-04
        body = json.dumps({"type": "user.updated", "data": {}}).encode()
        ts_str = "abc"
        sig = _make_signature("msg_test_001", ts_str, body)
        resp = client.post(
            "/api/webhooks/clerk",
            content=body,
            headers={
                "svix-id": "msg_test_001",
                "svix-timestamp": ts_str,
                "svix-signature": f"v1,{sig}",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 400
        assert "timestamp" in resp.json()["detail"].lower()


# ── user.created handler ───────────────────────────────────────────────────────

class TestUserCreatedHandler:
    def _user_payload(self, email: str | None = "test@example.com") -> dict:
        emails = (
            [{"id": "email_1", "email_address": email}] if email else []
        )
        return {
            "type": "user.created",
            "data": {
                "id": "user_clerk_123",
                "primary_email_address_id": "email_1" if email else None,
                "email_addresses": emails,
                "first_name": "Test",
                "last_name": "User",
            },
        }

    def test_user_created_upserts_user_row(self) -> None:  # TC-WH-05
        db = MagicMock()
        db.table.return_value = db
        db.upsert.return_value = db
        db.execute.return_value = MagicMock(
            data=[{"id": "aaaaaaaa-0000-0000-0000-000000000001"}]
        )

        with (
            patch("api.routers.webhooks._service_db", return_value=db),
            patch("api.routers.webhooks._write_clerk_metadata"),
        ):
            resp = _post_webhook(self._user_payload())

        assert resp.status_code == 200
        db.upsert.assert_called_once()
        upsert_data = db.upsert.call_args[0][0]
        assert upsert_data["clerk_id"] == "user_clerk_123"
        assert upsert_data["email"] == "test@example.com"

    def test_user_created_no_email_returns_400(self) -> None:  # TC-WH-06
        db = MagicMock()
        db.table.return_value = db

        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook(self._user_payload(email=None))

        assert resp.status_code == 400


# ── organization.created handler ──────────────────────────────────────────────

class TestOrgCreatedHandler:
    def _org_payload(self) -> dict:
        return {
            "type": "organization.created",
            "data": {
                "id": "org_clerk_123",
                "name": "Acme Corp",
            },
        }

    def test_org_created_upserts_org_row(self) -> None:  # TC-WH-07
        db = MagicMock()
        db.table.return_value = db
        db.upsert.return_value = db
        db.execute.return_value = MagicMock(
            data=[{"id": "bbbbbbbb-0000-0000-0000-000000000001"}]
        )

        with (
            patch("api.routers.webhooks._service_db", return_value=db),
            patch("api.routers.webhooks._write_clerk_metadata"),
        ):
            resp = _post_webhook(self._org_payload())

        assert resp.status_code == 200
        db.upsert.assert_called_once()
        upsert_data = db.upsert.call_args[0][0]
        assert upsert_data["clerk_id"] == "org_clerk_123"
        assert upsert_data["plan"] == "trial"

    def test_org_created_sets_14_day_trial(self) -> None:  # TC-WH-08
        from datetime import datetime, timedelta, timezone

        db = MagicMock()
        db.table.return_value = db
        db.upsert.return_value = db
        db.execute.return_value = MagicMock(
            data=[{"id": "bbbbbbbb-0000-0000-0000-000000000001"}]
        )

        with (
            patch("api.routers.webhooks._service_db", return_value=db),
            patch("api.routers.webhooks._write_clerk_metadata"),
        ):
            _post_webhook(self._org_payload())

        upsert_data = db.upsert.call_args[0][0]
        trial_ends_str: str = upsert_data["trial_ends_at"]
        # Parse and check it's ~14 days from now
        trial_ends = datetime.fromisoformat(trial_ends_str)
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff_days = (trial_ends - now).days
        assert 13 <= diff_days <= 14


# ── organizationMembership.created handler ────────────────────────────────────

class TestMembershipCreatedHandler:
    def _membership_payload(self, role: str = "org:admin") -> dict:
        return {
            "type": "organizationMembership.created",
            "data": {
                "organization": {"id": "org_clerk_123"},
                "public_user_data": {"user_id": "user_clerk_123"},
                "role": role,
            },
        }

    def _db_with_user_and_org(self) -> MagicMock:
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.upsert.return_value = db
        db.single.return_value = db
        db.execute.side_effect = [
            MagicMock(data={"id": "user-db-uuid"}),   # users.single()
            MagicMock(data={"id": "org-db-uuid"}),    # organizations.single()
            MagicMock(data=[]),                        # upsert
        ]
        return db

    def test_membership_created_upserts_member_row(self) -> None:  # TC-WH-09
        db = self._db_with_user_and_org()
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook(self._membership_payload())
        assert resp.status_code == 200
        db.upsert.assert_called_once()

    def test_clerk_admin_role_mapped_to_admin(self) -> None:  # TC-WH-10
        db = self._db_with_user_and_org()
        with patch("api.routers.webhooks._service_db", return_value=db):
            _post_webhook(self._membership_payload(role="org:admin"))
        upsert_data = db.upsert.call_args[0][0]
        assert upsert_data["role"] == "admin"


# ── Unhandled event ────────────────────────────────────────────────────────────

class TestUnhandledEvent:
    def test_unhandled_event_type_returns_200_no_db_write(self) -> None:  # TC-WH-11
        db = MagicMock()
        db.table.return_value = db
        with patch("api.routers.webhooks._service_db", return_value=db):
            resp = _post_webhook({"type": "user.updated", "data": {}})
        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        db.upsert.assert_not_called()
        db.insert.assert_not_called()
