"""
Provider adapter gap tests.

Gap-18 (critical): OpenAI two-pass fetch - Pass 1 failure raises before Pass 2 runs.
Gap-19 (high):     Provider 429 raises ValueError with status code in message.
Gap-20 (high):     Anthropic adapter validate() / fetch_costs() basic coverage.
Gap-21 (high):     Anthropic pagination stops when has_more is absent/False.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

START = datetime(2026, 5, 1, tzinfo=UTC)
END = datetime(2026, 5, 31, tzinfo=UTC)


# ── helpers ────────────────────────────────────────────────────────────────────


def _mock_httpx_response(status_code: int, body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = str(body)
    return resp


def _usage_page(model: str = "gpt-4o", start_ts: int = 1_746_057_600) -> dict:
    return {
        "data": [
            {
                "start_time": start_ts,
                "results": [
                    {
                        "model": model,
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "input_cached_tokens": 100,
                        "num_model_requests": 5,
                    }
                ],
            }
        ],
        "has_more": False,
        "next_page": None,
    }


def _cost_page(model: str = "gpt-4o", start_ts: int = 1_746_057_600, cost: float = 0.05) -> dict:
    return {
        "data": [
            {
                "start_time": start_ts,
                "end_time": start_ts + 86400,
                "results": [
                    {
                        "line_item": model,
                        "amount": {"value": cost, "currency": "usd"},
                    }
                ],
            }
        ],
        "has_more": False,
        "next_page": None,
    }


# ── Gap-18: OpenAI two-pass fetch failure ─────────────────────────────────────


class TestOpenAITwoPassFetch:
    """Gap-18 (critical): If Pass 1 (usage/completions) fails, Pass 2 (costs) never runs."""

    def test_pass1_http_error_raises_before_pass2(self) -> None:
        """
        Pass 1 (/organization/usage/completions) returning non-200 must raise ValueError.
        Pass 2 (/organization/costs) must NOT be called - no partial token_lookup.
        """
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        call_log: list[str] = []

        def mock_get(url: str, **kwargs):
            call_log.append(url)
            if "usage/completions" in url:
                return _mock_httpx_response(500, {"error": "internal"})
            return _mock_httpx_response(200, _cost_page())

        with patch("api.adapters.openai.httpx.get", side_effect=mock_get):
            with pytest.raises(ValueError) as exc_info:
                list(adapter.fetch_costs(b"sk-test", START, END))

        assert "500" in str(exc_info.value)
        # Pass 2 must not have been called
        assert not any("organization/costs" in url for url in call_log), (
            "Gap-18: Pass 2 (/costs) was called even though Pass 1 failed. "
            "It should not run - token_lookup would be empty and events mis-attributed."
        )

    def test_pass1_success_pass2_failure_raises(self) -> None:
        """
        Pass 1 succeeds but Pass 2 (/organization/costs) fails → ValueError from Pass 2.
        """
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()

        def mock_get(url: str, **kwargs):
            if "usage/completions" in url:
                return _mock_httpx_response(200, _usage_page())
            # costs endpoint fails
            return _mock_httpx_response(429, {"error": "rate limited"})

        with patch("api.adapters.openai.httpx.get", side_effect=mock_get):
            with pytest.raises(ValueError) as exc_info:
                list(adapter.fetch_costs(b"sk-test", START, END))

        assert "429" in str(exc_info.value)

    def test_pass1_partial_token_data_still_yields_events(self) -> None:
        """
        If a model appears in Pass 2 (costs) but NOT in Pass 1 (token_lookup),
        the event is still yielded with zero tokens (default from token_lookup.get).
        """
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        start_ts = int(START.timestamp())

        def mock_get(url: str, **kwargs):
            if "usage/completions" in url:
                # Pass 1 returns data for 'gpt-4o-mini', not for 'gpt-4o'
                return _mock_httpx_response(200, _usage_page("gpt-4o-mini", start_ts))
            # Pass 2 returns data for 'gpt-4o' (not in token_lookup)
            return _mock_httpx_response(200, _cost_page("gpt-4o", start_ts, 0.10))

        with patch("api.adapters.openai.httpx.get", side_effect=mock_get):
            events = list(adapter.fetch_costs(b"sk-test", START, END))

        assert len(events) == 1
        event = events[0]
        assert event.model == "gpt-4o"
        assert event.cost_usd == Decimal("0.10")
        # Token counts default to 0 when not in lookup
        assert event.input_tokens == 0
        assert event.output_tokens == 0

    def test_zero_cost_results_are_skipped(self) -> None:
        """Pass 2 results with cost == 0 must be skipped."""
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()
        start_ts = int(START.timestamp())
        zero_cost_page = {
            "data": [
                {
                    "start_time": start_ts,
                    "results": [
                        {"line_item": "gpt-4o", "amount": {"value": 0.0, "currency": "usd"}}
                    ],
                }
            ],
            "has_more": False,
        }

        def mock_get(url: str, **kwargs):
            if "usage/completions" in url:
                return _mock_httpx_response(200, _usage_page(start_ts=start_ts))
            return _mock_httpx_response(200, zero_cost_page)

        with patch("api.adapters.openai.httpx.get", side_effect=mock_get):
            events = list(adapter.fetch_costs(b"sk-test", START, END))

        assert len(events) == 0, "Zero-cost results must be skipped"


# ── Gap-19: Provider 429 rate limiting ────────────────────────────────────────


class TestProviderRateLimiting:
    """Gap-19 (high): 429 from provider must raise ValueError (not propagate silently)."""

    def test_openai_429_raises_value_error_with_status(self) -> None:
        """OpenAI 429 → ValueError containing '429' in message."""
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()

        with patch(
            "api.adapters.openai.httpx.get",
            return_value=_mock_httpx_response(429, {"error": "rate_limit_exceeded"}),
        ):
            with pytest.raises(ValueError) as exc_info:
                list(adapter.fetch_costs(b"sk-test", START, END))

        assert "429" in str(exc_info.value)

    def test_openai_429_on_validate_raises_value_error(self) -> None:
        """OpenAI 429 on validate() → ValueError with status code."""
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()

        with patch(
            "api.adapters.openai.httpx.get",
            return_value=_mock_httpx_response(429, {"error": "rate_limit_exceeded"}),
        ):
            with pytest.raises(ValueError) as exc_info:
                adapter.validate(b"sk-test")

        assert "429" in str(exc_info.value)

    def test_anthropic_429_raises_value_error_with_status(self) -> None:
        """Anthropic 429 → ValueError containing '429'."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()

        with patch(
            "api.adapters.anthropic.httpx.get",
            return_value=_mock_httpx_response(429, {"error": "rate_limit"}),
        ):
            with pytest.raises(ValueError) as exc_info:
                list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert "429" in str(exc_info.value)

    def test_openai_network_error_raises_value_error(self) -> None:
        """httpx.RequestError during pagination → ValueError wrapping the network error."""
        from api.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter()

        with patch(
            "api.adapters.openai.httpx.get",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(ValueError) as exc_info:
                list(adapter.fetch_costs(b"sk-test", START, END))

        assert "network" in str(exc_info.value).lower()


# ── Gap-20: Anthropic adapter basic coverage ─────────────────────────────────


class TestAnthropicAdapterCoverage:
    """Gap-20 (high): Anthropic adapter validate() and fetch_costs() have 0% direct coverage."""

    def test_validate_returns_true_on_200(self) -> None:
        """validate() returns True when the API responds 200."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()

        with patch(
            "api.adapters.anthropic.httpx.get",
            return_value=_mock_httpx_response(200, {"data": []}),
        ):
            result = adapter.validate(b"sk-ant-test")

        assert result is True

    def test_validate_raises_on_401(self) -> None:
        """validate() raises ValueError on 401 Unauthorized."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()

        with patch(
            "api.adapters.anthropic.httpx.get",
            return_value=_mock_httpx_response(401, {"error": "Unauthorized"}),
        ):
            with pytest.raises(ValueError) as exc_info:
                adapter.validate(b"invalid-key")

        assert "anthropic" in str(exc_info.value).lower()

    def test_fetch_costs_yields_normalized_event(self) -> None:
        """fetch_costs() yields at least one NormalizedUsageEvent for valid data."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()

        anthropic_page = {
            "data": [
                {
                    "starting_at": "2026-05-01T00:00:00Z",
                    "ending_at": "2026-05-02T00:00:00Z",
                    "results": [
                        {
                            "model": "claude-3-5-sonnet-20241022",
                            "input_tokens": 10000,
                            "output_tokens": 5000,
                            "cache_read_input_tokens": 2000,
                            "cache_creation_input_tokens": 0,
                            "request_count": 10,
                        }
                    ],
                }
            ],
            "has_more": False,
        }

        with patch(
            "api.adapters.anthropic.httpx.get",
            return_value=_mock_httpx_response(200, anthropic_page),
        ):
            events = list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert len(events) >= 1
        event = events[0]
        assert event.provider == "anthropic"
        assert event.model == "claude-3-5-sonnet-20241022"
        assert event.input_tokens == 10000
        assert event.output_tokens == 5000
        assert event.cached_tokens == 2000
        assert event.cost_usd > Decimal("0")  # pricing.yaml must have this model

    def test_fetch_costs_skips_zero_token_zero_cost_rows(self) -> None:
        """Rows with 0 input, 0 output tokens AND 0 cost must be skipped."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()

        zero_page = {
            "data": [
                {
                    "starting_at": "2026-05-01T00:00:00Z",
                    "results": [
                        {
                            "model": "claude-3-haiku-20240307",
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "request_count": 0,
                        }
                    ],
                }
            ],
            "has_more": False,
        }

        with patch(
            "api.adapters.anthropic.httpx.get",
            return_value=_mock_httpx_response(200, zero_page),
        ):
            events = list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert len(events) == 0, "Zero token/cost rows must be skipped"

    def test_fetch_costs_includes_anthropic_beta_header(self) -> None:
        """
        BUG-01 (fixed): fetch_costs() must include 'anthropic-beta' header.
        Verify the header is sent on every paginated request.
        """
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()
        captured_headers: list[dict] = []

        def capture_get(url: str, headers: dict, **kwargs):
            captured_headers.append(headers)
            return _mock_httpx_response(200, {"data": [], "has_more": False})

        with patch("api.adapters.anthropic.httpx.get", side_effect=capture_get):
            list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert captured_headers, "No HTTP calls were made"
        for hdrs in captured_headers:
            assert (
                "anthropic-beta" in hdrs
            ), "BUG-01 regression: anthropic-beta header missing from request"


# ── Gap-21: Anthropic pagination terminates on has_more=False ────────────────


class TestAnthropicPaginationTermination:
    """Gap-21 (high): Pagination must stop when has_more is absent or False."""

    def test_pagination_stops_when_has_more_false(self) -> None:
        """First page has_more=False → single HTTP call, no second page."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()
        call_count = [0]

        def mock_get(url: str, **kwargs):
            call_count[0] += 1
            return _mock_httpx_response(
                200,
                {
                    "data": [
                        {
                            "starting_at": "2026-05-01T00:00:00Z",
                            "results": [
                                {
                                    "model": "claude-3-5-sonnet-20241022",
                                    "input_tokens": 100,
                                    "output_tokens": 50,
                                    "cache_read_input_tokens": 0,
                                    "request_count": 1,
                                }
                            ],
                        }
                    ],
                    "has_more": False,
                    "next_page": None,
                },
            )

        with patch("api.adapters.anthropic.httpx.get", side_effect=mock_get):
            list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert (
            call_count[0] == 1
        ), f"Gap-21: Expected 1 pagination call when has_more=False. Got {call_count[0]}."

    def test_pagination_continues_when_has_more_true(self) -> None:
        """Two pages (has_more=True on first, False on second) → two HTTP calls."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()
        responses = [
            _mock_httpx_response(
                200,
                {
                    "data": [
                        {
                            "starting_at": "2026-05-01T00:00:00Z",
                            "results": [
                                {
                                    "model": "claude-3-5-sonnet-20241022",
                                    "input_tokens": 100,
                                    "output_tokens": 50,
                                    "cache_read_input_tokens": 0,
                                    "request_count": 1,
                                }
                            ],
                        }
                    ],
                    "has_more": True,
                    "next_page": "cursor_page_2",
                },
            ),
            _mock_httpx_response(
                200,
                {
                    "data": [
                        {
                            "starting_at": "2026-05-15T00:00:00Z",
                            "results": [
                                {
                                    "model": "claude-3-5-sonnet-20241022",
                                    "input_tokens": 200,
                                    "output_tokens": 100,
                                    "cache_read_input_tokens": 0,
                                    "request_count": 2,
                                }
                            ],
                        }
                    ],
                    "has_more": False,
                    "next_page": None,
                },
            ),
        ]
        call_n = [0]

        def mock_get(url: str, **kwargs):
            resp = responses[call_n[0]]
            call_n[0] += 1
            return resp

        with patch("api.adapters.anthropic.httpx.get", side_effect=mock_get):
            events = list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert call_n[0] == 2, f"Expected 2 pages. Got {call_n[0]}."
        assert len(events) == 2

    def test_pagination_stops_when_next_page_is_none(self) -> None:
        """has_more=True but next_page=None (malformed response) → pagination stops."""
        from api.adapters.anthropic import AnthropicAdapter

        adapter = AnthropicAdapter()
        call_count = [0]

        def mock_get(url: str, **kwargs):
            call_count[0] += 1
            return _mock_httpx_response(
                200,
                {
                    "data": [],
                    "has_more": True,
                    "next_page": None,  # missing cursor despite has_more=True
                },
            )

        with patch("api.adapters.anthropic.httpx.get", side_effect=mock_get):
            list(adapter.fetch_costs(b"sk-ant-test", START, END))

        assert call_count[0] == 1, (
            f"Gap-21: Pagination must stop when next_page is None even if has_more=True. "
            f"Got {call_count[0]} calls (infinite loop risk)."
        )
