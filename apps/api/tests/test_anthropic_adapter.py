"""
Unit tests for the Anthropic adapter.
Mocks httpx to avoid real network calls.
Cost values are computed from packages/pricing/pricing.yaml rates.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from api.adapters.anthropic import AnthropicAdapter, _compute_cost


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = str(json_body)
    return resp


def _usage_page(
    buckets: list[dict],
    has_more: bool = False,
    next_page: str | None = None,
) -> dict:
    return {"data": buckets, "has_more": has_more, "next_page": next_page}


def _bucket(
    start: str,
    end: str,
    results: list[dict],
) -> dict:
    # Real Anthropic API uses "starting_at" / "ending_at" (not "start_time")
    return {"starting_at": start, "ending_at": end, "results": results}


def _result(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    request_count: int = 1,
) -> dict:
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "request_count": request_count,
    }


START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 2, tzinfo=timezone.utc)
KEY = b"sk-ant-admin-testkey1234567890"

START_ISO = "2025-01-01T00:00:00Z"
END_ISO = "2025-01-02T00:00:00Z"


# ── _compute_cost() ───────────────────────────────────────────────────────────

class TestComputeCost:
    def test_known_model_returns_nonzero_cost(self) -> None:
        # claude-sonnet-4-5: input=3.00, output=15.00, cached=0.30 per Mtok
        cost = _compute_cost("claude-sonnet-4-5", 1_000_000, 0, 0)
        assert cost == Decimal("3.0")

    def test_output_tokens_rated_correctly(self) -> None:
        cost = _compute_cost("claude-sonnet-4-5", 0, 1_000_000, 0)
        assert cost == Decimal("15.0")

    def test_cached_tokens_rated_correctly(self) -> None:
        cost = _compute_cost("claude-sonnet-4-5", 0, 0, 1_000_000)
        assert cost == Decimal("0.3")

    def test_unknown_model_returns_zero(self) -> None:
        cost = _compute_cost("claude-unknown-99", 1_000, 500, 0)
        assert cost == Decimal("0")

    def test_all_zero_tokens_returns_zero(self) -> None:
        cost = _compute_cost("claude-sonnet-4-5", 0, 0, 0)
        assert cost == Decimal("0")


# ── validate() ────────────────────────────────────────────────────────────────

class TestValidate:
    def test_returns_true_on_200(self) -> None:
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, {})):
            assert adapter.validate(KEY) is True

    def test_raises_on_401(self) -> None:
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(401, {"error": "unauthorized"})):
            with pytest.raises(ValueError, match="Invalid or unauthorized"):
                adapter.validate(KEY)

    def test_raises_on_403(self) -> None:
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(403, {})):
            with pytest.raises(ValueError, match="Invalid or unauthorized"):
                adapter.validate(KEY)

    def test_raises_on_unexpected_status(self) -> None:
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(500, {})):
            with pytest.raises(ValueError, match="500"):
                adapter.validate(KEY)

    def test_raises_on_network_error(self) -> None:
        import httpx as _httpx
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", side_effect=_httpx.RequestError("timeout")):
            with pytest.raises(ValueError, match="Network error"):
                adapter.validate(KEY)


# ── fetch_costs() ─────────────────────────────────────────────────────────────

class TestFetchCosts:
    def test_yields_normalized_event_with_correct_fields(self) -> None:
        """Happy path: 1 bucket, 1 model, all fields populated correctly."""
        page = _usage_page([
            _bucket(
                START_ISO,
                END_ISO,
                [_result("claude-sonnet-4-5", input_tokens=1000, output_tokens=200, cache_read_input_tokens=50, request_count=3)],
            )
        ])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 1
        e = events[0]
        assert e.provider == "anthropic"
        assert e.model == "claude-sonnet-4-5"
        assert e.input_tokens == 1000
        assert e.output_tokens == 200
        assert e.cached_tokens == 50
        assert e.request_count == 3
        assert e.api_key_label is None
        assert e.bucket_hour == datetime(2025, 1, 1, 0, 0, 0)  # naive UTC
        # Cost: (1000*3.00 + 200*15.00 + 50*0.30) / 1_000_000 = (3 + 3 + 0.015) / 1000 = 0.006015
        expected_cost = _compute_cost("claude-sonnet-4-5", 1000, 200, 50)
        assert e.cost_usd == expected_cost

    def test_skips_rows_with_zero_tokens_and_zero_cost(self) -> None:
        """Rows with all-zero tokens produce zero cost and should be skipped."""
        page = _usage_page([
            _bucket(
                START_ISO,
                END_ISO,
                [_result("claude-sonnet-4-5", input_tokens=0, output_tokens=0)],
            )
        ])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert events == []

    def test_unknown_model_yields_event_with_zero_cost(self) -> None:
        """Unknown model: token counts are preserved, cost is Decimal('0')."""
        page = _usage_page([
            _bucket(
                START_ISO,
                END_ISO,
                [_result("claude-unknown-future", input_tokens=500, output_tokens=100)],
            )
        ])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        # Should still yield - token data is valuable even without pricing
        assert len(events) == 1
        e = events[0]
        assert e.cost_usd == Decimal("0")
        assert e.input_tokens == 500
        assert e.output_tokens == 100

    def test_cached_tokens_mapped_from_cache_read_input_tokens(self) -> None:
        """Anthropic field cache_read_input_tokens → NormalizedUsageEvent.cached_tokens."""
        page = _usage_page([
            _bucket(
                START_ISO,
                END_ISO,
                [_result("claude-haiku-4-5", input_tokens=100, cache_read_input_tokens=400)],
            )
        ])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 1
        assert events[0].cached_tokens == 400

    def test_cache_creation_tokens_stored_in_raw_meta(self) -> None:
        """cache_creation_input_tokens is preserved in raw_meta for future use."""
        page = _usage_page([
            _bucket(
                START_ISO,
                END_ISO,
                [_result("claude-haiku-4-5", input_tokens=100, output_tokens=50, cache_creation_input_tokens=200)],
            )
        ])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 1
        assert events[0].raw_meta["cache_creation_input_tokens"] == 200

    def test_pagination_follows_cursor(self) -> None:
        """Verifies that _paginate keeps fetching when has_more=True."""
        page1 = _usage_page(
            [_bucket(START_ISO, END_ISO, [_result("claude-opus-4-5", input_tokens=1000, output_tokens=100)])],
            has_more=True,
            next_page="cursor_xyz",
        )
        page2 = _usage_page(
            [_bucket(START_ISO, END_ISO, [_result("claude-haiku-4-5", input_tokens=500, output_tokens=50)])],
            has_more=False,
        )

        adapter = AnthropicAdapter()
        with patch(
            "api.adapters.anthropic.httpx.get",
            side_effect=[_mock_response(200, page1), _mock_response(200, page2)],
        ):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 2
        models = {e.model for e in events}
        assert models == {"claude-opus-4-5", "claude-haiku-4-5"}

    def test_raises_on_non_200_during_pagination(self) -> None:
        """Non-200 status during pagination raises ValueError with status code."""
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(429, {})):
            with pytest.raises(ValueError, match="429"):
                list(adapter.fetch_costs(KEY, START, END))

    def test_multiple_models_in_same_bucket(self) -> None:
        """Multiple results in a single bucket each yield a separate event."""
        page = _usage_page([
            _bucket(
                START_ISO,
                END_ISO,
                [
                    _result("claude-opus-4-5", input_tokens=200, output_tokens=50),
                    _result("claude-haiku-4-5", input_tokens=1000, output_tokens=200),
                ],
            )
        ])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 2
        models = {e.model for e in events}
        assert models == {"claude-opus-4-5", "claude-haiku-4-5"}

    def test_empty_data_yields_no_events(self) -> None:
        """Empty data array → no events yielded, no crash."""
        page = _usage_page([])
        adapter = AnthropicAdapter()
        with patch("api.adapters.anthropic.httpx.get", return_value=_mock_response(200, page)):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert events == []
