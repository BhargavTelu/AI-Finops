"""
Unit tests for the Gemini adapter.
Mocks httpx to avoid real network calls.
fetch_costs() is intentionally a no-op (billing API deferred to V1).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from api.adapters.gemini import GeminiAdapter

KEY = b"AIzaSyTestKey1234567890abcdefghijkl"
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 2, tzinfo=UTC)


def _mock_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


# ── validate() ────────────────────────────────────────────────────────────────


class TestValidate:
    def test_returns_true_on_200(self) -> None:
        adapter = GeminiAdapter()
        with patch("api.adapters.gemini.httpx.get", return_value=_mock_response(200)):
            result = adapter.validate(KEY)
        assert result is True

    def test_raises_on_400(self) -> None:
        adapter = GeminiAdapter()
        with patch("api.adapters.gemini.httpx.get", return_value=_mock_response(400)):
            with pytest.raises(ValueError, match="invalid or lacks required permissions"):
                adapter.validate(KEY)

    def test_raises_on_403(self) -> None:
        adapter = GeminiAdapter()
        with patch("api.adapters.gemini.httpx.get", return_value=_mock_response(403)):
            with pytest.raises(ValueError, match="invalid or lacks required permissions"):
                adapter.validate(KEY)

    def test_raises_on_401(self) -> None:
        adapter = GeminiAdapter()
        with patch("api.adapters.gemini.httpx.get", return_value=_mock_response(401)):
            with pytest.raises(ValueError, match="invalid or lacks required permissions"):
                adapter.validate(KEY)

    def test_raises_on_network_error(self) -> None:
        adapter = GeminiAdapter()
        with patch(
            "api.adapters.gemini.httpx.get",
            side_effect=httpx.RequestError("timeout"),
        ):
            with pytest.raises(ValueError, match="Could not reach Gemini API"):
                adapter.validate(KEY)

    def test_validate_sends_key_as_query_param(self) -> None:
        """Key must be sent as ?key= query param, not as Authorization header."""
        adapter = GeminiAdapter()
        mock_get = MagicMock(return_value=_mock_response(200))
        with patch("api.adapters.gemini.httpx.get", mock_get):
            adapter.validate(KEY)
        call_kwargs = mock_get.call_args
        params = call_kwargs[1].get("params", {}) or (
            call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {}
        )
        assert "key" in params


# ── fetch_costs() ─────────────────────────────────────────────────────────────


class TestFetchCosts:
    def test_returns_empty_iterator(self) -> None:
        adapter = GeminiAdapter()
        events = list(adapter.fetch_costs(KEY, START, END))
        assert events == []

    def test_does_not_call_api(self) -> None:
        """fetch_costs must not make any HTTP calls (no billing endpoint available)."""
        adapter = GeminiAdapter()
        with patch("api.adapters.gemini.httpx.get") as mock_get:
            list(adapter.fetch_costs(KEY, START, END))
        mock_get.assert_not_called()
