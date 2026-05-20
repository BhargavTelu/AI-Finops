"""
Unit tests for the OpenAI adapter.
Mocks httpx to avoid real network calls.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from api.adapters.openai import OpenAIAdapter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = str(json_body)
    return resp


def _costs_page(buckets: list[dict], has_more: bool = False, next_page: str | None = None) -> dict:
    return {"object": "page", "data": buckets, "has_more": has_more, "next_page": next_page}


def _completions_page(buckets: list[dict], has_more: bool = False) -> dict:
    return {"object": "page", "data": buckets, "has_more": has_more, "next_page": None}


START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 2, tzinfo=timezone.utc)
KEY = b"sk-admin-testkey1234567890"


# ── validate() ────────────────────────────────────────────────────────────────

class TestValidate:
    def test_returns_true_on_200(self) -> None:
        adapter = OpenAIAdapter()
        with patch("api.adapters.openai.httpx.get", return_value=_mock_response(200, {})):
            assert adapter.validate(KEY) is True

    def test_raises_on_401(self) -> None:
        adapter = OpenAIAdapter()
        with patch("api.adapters.openai.httpx.get", return_value=_mock_response(401, {"error": "unauthorized"})):
            with pytest.raises(ValueError, match="Invalid or unauthorized"):
                adapter.validate(KEY)

    def test_raises_on_403(self) -> None:
        adapter = OpenAIAdapter()
        with patch("api.adapters.openai.httpx.get", return_value=_mock_response(403, {})):
            with pytest.raises(ValueError, match="Invalid or unauthorized"):
                adapter.validate(KEY)

    def test_raises_on_unexpected_status(self) -> None:
        adapter = OpenAIAdapter()
        with patch("api.adapters.openai.httpx.get", return_value=_mock_response(500, {})):
            with pytest.raises(ValueError, match="500"):
                adapter.validate(KEY)

    def test_raises_on_network_error(self) -> None:
        import httpx as _httpx
        adapter = OpenAIAdapter()
        with patch("api.adapters.openai.httpx.get", side_effect=_httpx.RequestError("timeout")):
            with pytest.raises(ValueError, match="Network error"):
                adapter.validate(KEY)


# ── fetch_costs() ─────────────────────────────────────────────────────────────

class TestFetchCosts:
    def _make_adapter_and_pages(self, cost_buckets: list[dict], completion_buckets: list[dict]):
        """
        Returns adapter + a side_effect list for httpx.get that serves
        completions first (pass 1) then costs (pass 2), each single-page.
        """
        adapter = OpenAIAdapter()
        completions_resp = _mock_response(200, _completions_page(completion_buckets))
        costs_resp = _mock_response(200, _costs_page(cost_buckets))
        return adapter, [completions_resp, costs_resp]

    def test_yields_normalized_event_per_cost_result(self) -> None:
        ts = int(START.timestamp())
        cost_buckets = [
            {
                "start_time": ts,
                "end_time": ts + 3600,
                "results": [
                    # Costs API groups by line_item — adapter reads result.get("line_item")
                    {"line_item": "gpt-4o", "amount": {"value": 0.50, "currency": "usd"}}
                ],
            }
        ]
        completion_buckets = [
            {
                "start_time": ts,
                "end_time": ts + 3600,
                "results": [
                    {
                        "model": "gpt-4o",
                        "input_tokens": 1000,
                        "output_tokens": 200,
                        "input_cached_tokens": 50,
                        "num_model_requests": 3,
                    }
                ],
            }
        ]
        adapter, side_effects = self._make_adapter_and_pages(cost_buckets, completion_buckets)
        with patch("api.adapters.openai.httpx.get", side_effect=side_effects):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 1
        e = events[0]
        assert e.provider == "openai"
        assert e.model == "gpt-4o"
        assert e.cost_usd == Decimal("0.50")
        assert e.input_tokens == 1000
        assert e.output_tokens == 200
        assert e.cached_tokens == 50
        assert e.request_count == 3
        assert e.bucket_hour == datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        assert e.raw_meta["currency"] == "usd"

    def test_zero_cost_results_are_skipped(self) -> None:
        ts = int(START.timestamp())
        cost_buckets = [
            {
                "start_time": ts,
                "end_time": ts + 3600,
                "results": [
                    {"model": "gpt-4o-mini", "amount": {"value": 0, "currency": "usd"}}
                ],
            }
        ]
        adapter, side_effects = self._make_adapter_and_pages(cost_buckets, [])
        with patch("api.adapters.openai.httpx.get", side_effect=side_effects):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert events == []

    def test_missing_token_data_uses_zero_defaults(self) -> None:
        """Cost event without a matching completions entry yields 0-token event."""
        ts = int(START.timestamp())
        cost_buckets = [
            {
                "start_time": ts,
                "end_time": ts + 3600,
                "results": [
                    {"model": "gpt-4o", "amount": {"value": 1.00, "currency": "usd"}}
                ],
            }
        ]
        # No completion data for this bucket
        adapter, side_effects = self._make_adapter_and_pages(cost_buckets, [])
        with patch("api.adapters.openai.httpx.get", side_effect=side_effects):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 1
        e = events[0]
        assert e.input_tokens == 0
        assert e.output_tokens == 0
        assert e.cached_tokens == 0
        assert e.request_count == 1  # default

    def test_pagination_follows_cursor(self) -> None:
        """Verifies that _paginate keeps fetching when has_more=True."""
        ts = int(START.timestamp())

        def bucket(model: str, cost: float) -> dict:
            return {
                "start_time": ts,
                "end_time": ts + 3600,
                # Costs API groups by line_item — adapter reads result.get("line_item")
                "results": [{"line_item": model, "amount": {"value": cost, "currency": "usd"}}],
            }

        # completions: single empty page
        completions_resp = _mock_response(200, _completions_page([]))
        # costs: page 1 has_more=True, page 2 has_more=False
        costs_page1 = _mock_response(
            200,
            _costs_page([bucket("gpt-4o", 1.0)], has_more=True, next_page="cursor_abc"),
        )
        costs_page2 = _mock_response(
            200,
            _costs_page([bucket("gpt-4o-mini", 0.5)], has_more=False),
        )

        adapter = OpenAIAdapter()
        with patch(
            "api.adapters.openai.httpx.get",
            side_effect=[completions_resp, costs_page1, costs_page2],
        ):
            events = list(adapter.fetch_costs(KEY, START, END))

        assert len(events) == 2
        models = {e.model for e in events}
        assert models == {"gpt-4o", "gpt-4o-mini"}

    def test_raises_on_non_200_during_pagination(self) -> None:
        completions_resp = _mock_response(200, _completions_page([]))
        error_resp = _mock_response(429, {})

        adapter = OpenAIAdapter()
        with patch("api.adapters.openai.httpx.get", side_effect=[completions_resp, error_resp]):
            with pytest.raises(ValueError, match="429"):
                list(adapter.fetch_costs(KEY, START, END))
