"""
Additional Slack route tests not covered by test_slack_routes.py.
TC-SLACK-08 and TC-SLACK-09.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"

app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="clerk_user_1", org_id=ORG_ID)

client = TestClient(app)


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


class TestSlackDisconnectExtended:
    def test_revoke_failure_is_non_fatal(self) -> None:  # TC-SLACK-08
        """If revoke_token raises, disconnect still returns 204 and deletes DB row."""
        db = _mock_db()
        fake_token_enc = "\\x" + "aa" * 28
        db.execute.side_effect = [
            MagicMock(data=[{"bot_token_enc": fake_token_enc}]),  # select
            MagicMock(data=[]),                                    # delete
        ]
        with (
            patch("api.routers.slack._get_supabase", return_value=db),
            patch("api.routers.slack.revoke_token", side_effect=Exception("Slack unreachable")),
            patch("api.routers.slack.EncryptionService") as mock_cipher_cls,
        ):
            mock_cipher_cls.return_value.decrypt.return_value = b"xoxb-test-token"
            resp = client.post("/api/v1/slack/disconnect")
        assert resp.status_code == 204
        # Verify the DB delete was still called despite revoke failure
        delete_calls = [str(c) for c in db.table.call_args_list]
        assert any("slack_integrations" in s for s in delete_calls)

    def test_bot_token_encrypted_at_rest(self) -> None:  # TC-SLACK-09
        """Bot token stored in DB must not be the plaintext token."""
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[{"id": "user-uuid-1"}]),  # users lookup
            MagicMock(data=[]),                        # upsert
        ]
        slack_response = {
            "ok": True,
            "access_token": "xoxb-plaintext-token-do-not-store",
            "team": {"id": "T01234567", "name": "Test Workspace"},
            "incoming_webhook": {
                "channel": "#alerts",
                "channel_id": "C01234567",
                "url": "https://hooks.slack.com/services/...",
            },
        }

        upsert_payload: dict = {}

        def capture_upsert(data: dict, **kwargs: object) -> MagicMock:
            upsert_payload.update(data)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[])
            return m

        db.upsert.side_effect = capture_upsert

        # Use a real EncryptionService with a known key so we can verify encryption
        import base64
        from api.services.encryption import EncryptionService

        test_key = base64.b64encode(b"\xbb" * 32).decode()
        real_cipher = EncryptionService(test_key)

        with (
            patch("api.routers.slack._get_supabase", return_value=db),
            patch("api.routers.slack.exchange_code", return_value=slack_response),
            patch("api.routers.slack.EncryptionService", return_value=real_cipher),
            patch("api.routers.slack.settings") as mock_settings,
        ):
            mock_settings.slack_client_id = "test_client_id"
            mock_settings.slack_client_secret = "test_client_secret"
            mock_settings.slack_redirect_uri = "http://localhost:3000/callback"
            mock_settings.encryption_key = test_key
            resp = client.post("/api/v1/slack/oauth/callback", json={"code": "valid_code", "state": ORG_ID})

        assert resp.status_code == 200
        # The captured upsert must have bot_token_enc that is NOT the plaintext
        stored_token = upsert_payload.get("bot_token_enc", "")
        assert "xoxb-plaintext-token-do-not-store" not in stored_token
        assert stored_token.startswith("\\x"), "Encrypted token should start with \\x hex prefix"
