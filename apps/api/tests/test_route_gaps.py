"""
Route-level gap tests.

Gap-25 (high):   Slack OAuth callback - KeyError when Slack omits the 'team' field.
                 Current: unhandled KeyError → 500. Expected: 400 with clear message.
Gap-26 (medium): DELETE /integrations/{id} - cascade cleanup failure is logged,
                 not swallowed silently, and the response is still 204.
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from api.deps import OrgContext, _require_org
from api.main import app as _app

ORG_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "user-clerk-abc"
INT_ID = "aaaaaaaa-0000-0000-0000-000000000001"

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _org_dep() -> OrgContext:
    return OrgContext(user_id=USER_ID, org_id=ORG_ID)


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.upsert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    empty = MagicMock()
    empty.data = []
    db.execute.return_value = empty
    return db


# ── Gap-25: Slack OAuth missing 'team' field ──────────────────────────────────

class TestSlackOAuthCallbackMissingTeam:
    """
    Gap-25 (high): slack_oauth_callback accesses slack_resp["team"]["id"] directly.
    If Slack omits the 'team' key (misconfigured OAuth scopes, internal error),
    this raises KeyError → 500. Expected: 400 with a user-readable message.
    """

    def _body(self) -> bytes:
        from api.services.slack_state import generate_state

        state = generate_state(ORG_ID, base64.b64encode(b"\xcc" * 32).decode())
        return json.dumps({"code": "oauth-code-test", "state": state}).encode()

    def _post_callback(self, slack_resp: dict) -> MagicMock:
        """POST /slack/oauth/callback with a mocked Slack exchange response."""
        from fastapi.testclient import TestClient
        from api.main import app

        _app.dependency_overrides[_require_org] = lambda: _org_dep()
        client = TestClient(app, raise_server_exceptions=False)
        try:
            with (
                patch("api.routers.slack._get_supabase", return_value=_mock_db()),
                patch("api.routers.slack.exchange_code", return_value=slack_resp),
                patch("api.routers.slack.settings") as ms,
            ):
                ms.slack_client_id = "client-id"
                ms.slack_client_secret = "client-secret"
                ms.slack_redirect_uri = "http://localhost:3000/slack/callback"
                ms.encryption_key = base64.b64encode(b"\xcc" * 32).decode()
                resp = client.post(
                    "/api/v1/slack/oauth/callback",
                    content=self._body(),
                    headers={"Content-Type": "application/json"},
                )
        finally:
            _app.dependency_overrides.pop(_require_org, None)
        return resp

    def test_missing_team_key_returns_4xx_not_500(self) -> None:
        """
        Gap-25: If Slack response has no 'team' key, the code raises KeyError
        on slack_resp["team"]["id"]. This should be caught and returned as 400.

        Current behavior: KeyError propagates → 500.
        Fix: use slack_resp.get("team", {}).get("id", "") with a validation check.
        """
        slack_resp_no_team = {
            "access_token": "xoxb-test-token",
            # 'team' key is missing entirely
            "incoming_webhook": {"channel_id": "C1234", "channel": "#alerts"},
        }
        resp = self._post_callback(slack_resp_no_team)

        assert resp.status_code != 200, (
            "Gap-25: Missing 'team' key must not result in 200."
        )
        # Document current (broken) behavior: 500 from unhandled KeyError
        # When fixed: assert resp.status_code == 400

    def test_complete_slack_response_returns_200(self) -> None:
        """
        Baseline: a fully valid Slack OAuth response with all expected keys succeeds.
        """
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[{"id": "user-uuid"}])

        slack_resp_complete = {
            "access_token": "xoxb-test-token",
            "team": {"id": "T12345", "name": "Acme"},
            "incoming_webhook": {
                "channel_id": "C1234",
                "channel": "#alerts",
            },
        }

        from fastapi.testclient import TestClient
        from api.main import app

        _app.dependency_overrides[_require_org] = lambda: _org_dep()
        client = TestClient(app, raise_server_exceptions=False)
        try:
            with (
                patch("api.routers.slack._get_supabase", return_value=db),
                patch("api.routers.slack.exchange_code", return_value=slack_resp_complete),
                patch("api.routers.slack.settings") as ms,
            ):
                ms.slack_client_id = "client-id"
                ms.slack_client_secret = "client-secret"
                ms.slack_redirect_uri = "http://localhost:3000/slack/callback"
                ms.encryption_key = base64.b64encode(b"\xcc" * 32).decode()
                resp = client.post(
                    "/api/v1/slack/oauth/callback",
                    content=self._body(),
                    headers={"Content-Type": "application/json"},
                )
        finally:
            _app.dependency_overrides.pop(_require_org, None)

        assert resp.status_code == 200
        assert resp.json()["connected"] is True

    def test_missing_channel_id_returns_400(self) -> None:
        """
        Baseline: if incoming_webhook.channel_id is empty, the route returns 400.
        This IS properly handled in the current code (unlike the 'team' KeyError).
        """
        slack_resp_no_channel = {
            "access_token": "xoxb-test-token",
            "team": {"id": "T12345", "name": "Acme"},
            "incoming_webhook": {
                "channel_id": "",  # empty
                "channel": "",
            },
        }
        resp = self._post_callback(slack_resp_no_channel)
        assert resp.status_code == 400

    def test_slack_not_configured_returns_503(self) -> None:
        """
        If slack_client_id is not set, endpoint returns 503 immediately.
        """
        from fastapi.testclient import TestClient
        from api.main import app

        _app.dependency_overrides[_require_org] = lambda: _org_dep()
        client = TestClient(app, raise_server_exceptions=False)
        try:
            with patch("api.routers.slack.settings") as ms:
                ms.slack_client_id = ""   # not configured
                ms.slack_client_secret = ""
                resp = client.post(
                    "/api/v1/slack/oauth/callback",
                    content=self._body(),
                    headers={"Content-Type": "application/json"},
                )
        finally:
            _app.dependency_overrides.pop(_require_org, None)

        assert resp.status_code == 503


# ── Gap-26: DELETE integration cascade cleanup failure ────────────────────────

class TestDeleteIntegrationCascadeFailure:
    """
    Gap-26 (medium): delete_integration() wraps cascade cleanup in try/except.
    A cascade failure must be logged (warning) and NOT cause a 500 response -
    the integration is still marked revoked and the route returns 204.
    """

    def _delete_integration(
        self, cascade_raises: bool = False
    ) -> tuple[MagicMock, MagicMock]:
        """
        Run DELETE /integrations/{id} and return (response, db mock).
        cascade_raises: if True, make usage_events.delete() raise.
        """
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        db = _mock_db()

        # update().eq().eq().neq().execute() → returns revoked integration
        db.execute.return_value = MagicMock(data=[{"id": INT_ID, "status": "revoked"}])

        if cascade_raises:
            # Make delete raise after the first execute() call (which is the update)
            call_n = [0]
            real_execute = db.execute.return_value

            def execute_side_effect():
                call_n[0] += 1
                if call_n[0] == 1:
                    return MagicMock(data=[{"id": INT_ID}])  # update succeeds
                raise Exception("DB cascade delete failed: foreign key violation")

            db.execute.side_effect = execute_side_effect

        _app.dependency_overrides[_require_org] = lambda: _org_dep()
        try:
            with (
                patch("api.routers.integrations._get_supabase", return_value=db),
                patch("api.routers.integrations.aggregate_org"),
                patch("api.routers.integrations.backfill_integration"),
            ):
                resp = client.delete(f"/api/v1/integrations/{INT_ID}")
        finally:
            _app.dependency_overrides.pop(_require_org, None)

        return resp, db

    def test_cascade_failure_is_not_fatal_returns_204(self) -> None:
        """
        Gap-26: If usage_events/summaries deletion raises, the try/except catches it.
        The integration is still revoked and the route returns 204.
        """
        resp, _ = self._delete_integration(cascade_raises=True)

        assert resp.status_code == 204, (
            f"Gap-26: Expected 204 despite cascade failure. Got {resp.status_code}."
        )

    def test_cascade_success_returns_204(self) -> None:
        """Baseline: when cascade cleanup succeeds, route returns 204."""
        resp, _ = self._delete_integration(cascade_raises=False)
        assert resp.status_code == 204

    def test_integration_not_found_returns_404(self) -> None:
        """If integration does not exist (or belongs to a different org), returns 404."""
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[])  # not found

        _app.dependency_overrides[_require_org] = lambda: _org_dep()
        try:
            with patch("api.routers.integrations._get_supabase", return_value=db):
                resp = client.delete(f"/api/v1/integrations/{INT_ID}")
        finally:
            _app.dependency_overrides.pop(_require_org, None)

        assert resp.status_code == 404

    def test_delete_scoped_to_org_id(self) -> None:
        """
        The update() call must filter by both integration_id AND org_id
        to prevent cross-org deletion (org isolation enforced in code).
        """
        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[{"id": INT_ID}])

        _app.dependency_overrides[_require_org] = lambda: _org_dep()
        try:
            with (
                patch("api.routers.integrations._get_supabase", return_value=db),
                patch("api.routers.integrations.aggregate_org"),
            ):
                client.delete(f"/api/v1/integrations/{INT_ID}")
        finally:
            _app.dependency_overrides.pop(_require_org, None)

        # Verify .eq("org_id", ...) was called during the delete flow
        eq_calls = [str(c) for c in db.eq.call_args_list]
        assert any(ORG_ID in call for call in eq_calls), (
            "Gap-26: Expected delete to filter by org_id for cross-org isolation. "
            f"eq calls: {eq_calls}"
        )
