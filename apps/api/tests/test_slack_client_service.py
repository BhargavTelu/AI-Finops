"""
Unit tests for Slack client service (services/slack_client.py).
TC-SLK-01 to TC-SLK-09 - no real HTTP calls, all mocked via httpx.Client patch.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from api.services.slack_client import exchange_code, post_message, revoke_token


def _mock_http_resp(status: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a fake httpx response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {}
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _patch_client(resp: MagicMock):
    """Context manager that patches httpx.Client so .post() returns resp."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = resp
    return patch("httpx.Client", return_value=mock_client)


# ── exchange_code ──────────────────────────────────────────────────────────────

class TestExchangeCode:
    def test_success_returns_full_dict(self) -> None:  # TC-SLK-01
        resp = _mock_http_resp(200, {"ok": True, "access_token": "xoxb-123"})
        with _patch_client(resp):
            result = exchange_code("code", "client_id", "client_secret", "https://redirect")
        assert result["ok"] is True
        assert result["access_token"] == "xoxb-123"

    def test_slack_api_error_raises_valueerror(self) -> None:  # TC-SLK-02
        resp = _mock_http_resp(200, {"ok": False, "error": "invalid_code"})
        with _patch_client(resp):
            with pytest.raises(ValueError, match="invalid_code"):
                exchange_code("code", "client_id", "client_secret", "https://redirect")

    def test_http_503_raises_valueerror(self) -> None:  # TC-SLK-03
        resp = _mock_http_resp(503, {})
        with _patch_client(resp):
            with pytest.raises(ValueError, match="503"):
                exchange_code("code", "client_id", "client_secret", "https://redirect")

    def test_network_timeout_raises_valueerror(self) -> None:  # TC-SLK-04
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.RequestError("timeout", request=MagicMock())
        with patch("httpx.Client", return_value=mock_client):
            with pytest.raises(ValueError):
                exchange_code("code", "client_id", "client_secret", "https://redirect")


# ── revoke_token ───────────────────────────────────────────────────────────────

class TestRevokeToken:
    def test_api_error_logs_warning_does_not_raise(self) -> None:  # TC-SLK-05
        resp = _mock_http_resp(200, {"ok": False, "error": "token_revoked"})
        with _patch_client(resp):
            revoke_token("xoxb-test")  # must not raise

    def test_network_error_does_not_raise(self) -> None:  # TC-SLK-06
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.RequestError("network error", request=MagicMock())
        with patch("httpx.Client", return_value=mock_client):
            revoke_token("xoxb-test")  # must not raise


# ── post_message ───────────────────────────────────────────────────────────────

class TestPostMessage:
    def test_success_does_not_raise(self) -> None:  # TC-SLK-07
        resp = _mock_http_resp(200, {"ok": True})
        with _patch_client(resp):
            post_message("xoxb-test", "C123", [], "fallback text")  # must not raise

    def test_slack_error_raises_valueerror(self) -> None:  # TC-SLK-08
        resp = _mock_http_resp(200, {"ok": False, "error": "channel_not_found"})
        with _patch_client(resp):
            with pytest.raises(ValueError, match="channel_not_found"):
                post_message("xoxb-test", "C123", [], "fallback text")

    def test_http_500_raises_valueerror(self) -> None:  # TC-SLK-09
        resp = _mock_http_resp(500, {})
        with _patch_client(resp):
            with pytest.raises(ValueError, match="500"):
                post_message("xoxb-test", "C123", [], "fallback text")
