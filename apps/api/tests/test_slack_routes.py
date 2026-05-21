"""
Unit tests for GET /slack/status, POST /slack/oauth/callback, POST /slack/disconnect.
Supabase calls and Slack client functions are mocked. Auth dependency is overridden.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
NOW_ISO = datetime.now(timezone.utc).isoformat()

app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="clerk_user_1", org_id=ORG_ID)

client = TestClient(app)


# ── DB mock helpers ─────────────────────────────────────────────────────────────

def _mock_db(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.upsert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


def _slack_row() -> dict:
    return {
        "workspace_id": "T01234567",
        "channel_id": "C01234567",
        "channel_name": "#alerts",
        "created_at": NOW_ISO,
    }


# ── GET /slack/status ───────────────────────────────────────────────────────────

class TestSlackStatus:
    def test_not_connected(self) -> None:
        db = _mock_db([])
        with patch("api.routers.slack._get_supabase", return_value=db):
            resp = client.get("/api/v1/slack/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is False
        assert resp.json()["channel_name"] is None

    def test_connected(self) -> None:
        db = _mock_db([_slack_row()])
        with patch("api.routers.slack._get_supabase", return_value=db):
            resp = client.get("/api/v1/slack/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["workspace_id"] == "T01234567"
        assert data["channel_name"] == "#alerts"
        assert data["channel_id"] == "C01234567"


# ── POST /slack/oauth/callback ──────────────────────────────────────────────────

class TestSlackOAuthCallback:
    def _call(self, code: str = "valid_code", state: str = "csrf_abc") -> MagicMock:
        return client.post(
            "/api/v1/slack/oauth/callback",
            json={"code": code, "state": state},
        )

    def test_successful_connect(self) -> None:
        db = _mock_db()
        # user lookup returns a DB user
        db.execute.side_effect = [
            MagicMock(data=[{"id": "user-uuid-1"}]),  # users lookup
            MagicMock(data=[]),                        # upsert
        ]
        slack_response = {
            "ok": True,
            "access_token": "xoxb-test-token",
            "team": {"id": "T01234567", "name": "Test Workspace"},
            "incoming_webhook": {
                "channel": "#alerts",
                "channel_id": "C01234567",
                "url": "https://hooks.slack.com/services/...",
            },
        }
        mock_cipher = MagicMock()
        mock_cipher.encrypt.return_value = b"\x00" * 28  # fake ciphertext

        with (
            patch("api.routers.slack._get_supabase", return_value=db),
            patch("api.routers.slack.exchange_code", return_value=slack_response),
            patch("api.routers.slack.EncryptionService", return_value=mock_cipher),
            patch("api.routers.slack.settings") as mock_settings,
        ):
            mock_settings.slack_client_id = "test_client_id"
            mock_settings.slack_client_secret = "test_client_secret"
            mock_settings.slack_redirect_uri = "http://localhost:3000/settings/slack/callback"
            mock_settings.encryption_key = "anything"  # bypassed by EncryptionService mock
            resp = self._call()

        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["workspace_id"] == "T01234567"
        assert data["channel_id"] == "C01234567"
        assert data["channel_name"] == "#alerts"

    def test_missing_code_returns_422(self) -> None:
        resp = client.post("/api/v1/slack/oauth/callback", json={"state": "csrf_abc"})
        assert resp.status_code == 422

    def test_slack_error_returns_400(self) -> None:
        """If Slack rejects the code (expired, replayed), return 400."""
        with (
            patch("api.routers.slack.exchange_code", side_effect=ValueError("invalid_code")),
            patch("api.routers.slack.settings") as mock_settings,
        ):
            mock_settings.slack_client_id = "test_client_id"
            mock_settings.slack_client_secret = "test_client_secret"
            mock_settings.slack_redirect_uri = "http://localhost:3000/callback"
            resp = self._call(code="expired_code")
        assert resp.status_code == 400

    def test_no_channel_in_response_returns_400(self) -> None:
        """If user didn't select a channel during OAuth, reject."""
        slack_response = {
            "ok": True,
            "access_token": "xoxb-test",
            "team": {"id": "T01234567", "name": "Workspace"},
            "incoming_webhook": {},  # no channel_id
        }
        with (
            patch("api.routers.slack.exchange_code", return_value=slack_response),
            patch("api.routers.slack.settings") as mock_settings,
        ):
            mock_settings.slack_client_id = "id"
            mock_settings.slack_client_secret = "secret"
            mock_settings.slack_redirect_uri = "http://localhost:3000/callback"
            resp = self._call()
        assert resp.status_code == 400

    def test_unconfigured_server_returns_503(self) -> None:
        with patch("api.routers.slack.settings") as mock_settings:
            mock_settings.slack_client_id = ""
            mock_settings.slack_client_secret = ""
            resp = self._call()
        assert resp.status_code == 503


# ── POST /slack/disconnect ──────────────────────────────────────────────────────

class TestSlackDisconnect:
    def test_disconnect_removes_row(self) -> None:
        db = _mock_db()
        fake_token_enc = "\\x" + "00" * 28  # hex string; won't decrypt but we mock both
        db.execute.side_effect = [
            MagicMock(data=[{"bot_token_enc": fake_token_enc}]),  # select
            MagicMock(data=[]),                                    # delete
        ]
        with (
            patch("api.routers.slack._get_supabase", return_value=db),
            patch("api.routers.slack.revoke_token"),          # skip actual revoke
            patch("api.routers.slack.EncryptionService"),     # skip decrypt
        ):
            resp = client.post("/api/v1/slack/disconnect")
        assert resp.status_code == 204

    def test_disconnect_not_connected_returns_404(self) -> None:
        db = _mock_db([])
        with patch("api.routers.slack._get_supabase", return_value=db):
            resp = client.post("/api/v1/slack/disconnect")
        assert resp.status_code == 404
