from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import httpx
import yaml

from api.adapters.base import NormalizedUsageEvent

# Reference:
#   GET /v1/organizations/usage_report/messages  - token counts per model per day bucket
#   Costs computed from pricing.yaml (Anthropic does not expose a per-org cost API with model granularity)
_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"
_PAGE_LIMIT = 30  # days per page; 30 covers a full month backfill in one request

# Load pricing at import time - file is small, parsing is cheap
_PRICING_PATH = Path(__file__).parents[5] / "packages" / "pricing" / "pricing.yaml"

def _load_anthropic_pricing() -> dict[str, dict[str, float]]:
    """Return {model_name: {input_per_mtok, output_per_mtok, cached_per_mtok}}."""
    with open(_PRICING_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("providers", {}).get("anthropic", {}).get("models", {})


_ANTHROPIC_PRICING: dict[str, dict[str, float]] = _load_anthropic_pricing()


def _compute_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int) -> Decimal:
    """
    Calculate USD cost from token counts using pricing.yaml rates.
    Returns Decimal("0") for unknown models - token counts are still captured.
    """
    rates = _ANTHROPIC_PRICING.get(model)
    if not rates:
        return Decimal("0")

    cost = (
        input_tokens * rates["input_per_mtok"]
        + output_tokens * rates["output_per_mtok"]
        + cached_tokens * rates["cached_per_mtok"]
    ) / 1_000_000

    return Decimal(str(round(cost, 10)))


class AnthropicAdapter:
    provider = "anthropic"

    def validate(self, key: bytes) -> bool:
        """
        Ping /v1/organizations/usage_report/messages with a 1-day window to confirm key works.
        Raises ValueError with a human-readable message if the key is invalid.
        """
        now = datetime.now(timezone.utc)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_iso = (today_midnight - timedelta(days=1)).replace(tzinfo=None).isoformat() + "Z"
        end_iso = today_midnight.replace(tzinfo=None).isoformat() + "Z"

        try:
            resp = httpx.get(
                f"{_BASE_URL}/v1/organizations/usage_report/messages",
                headers=self._headers(key),
                params={
                    "starting_at": start_iso,
                    "ending_at": end_iso,
                    "bucket_width": "1d",
                    "limit": 1,
                },
                timeout=15,
            )
        except httpx.RequestError as exc:
            raise ValueError(f"Network error reaching Anthropic: {exc}") from exc

        if resp.status_code == 200:
            return True
        if resp.status_code in (401, 403):
            raise ValueError("Invalid or unauthorized Anthropic Admin key")
        raise ValueError(f"Anthropic returned unexpected status {resp.status_code}")

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        """
        Paginate /v1/organizations/usage_report/messages and yield normalized events.
        Costs are computed from pricing.yaml because Anthropic's usage API returns
        token counts without a direct dollar amount at per-model granularity.
        bucket_hour is the UTC start of each day bucket.
        """
        start_iso = start.replace(tzinfo=None).isoformat() + "Z"
        end_iso = end.replace(tzinfo=None).isoformat() + "Z"

        params: dict[str, Any] = {
            "starting_at": start_iso,
            "ending_at": end_iso,
            "bucket_width": "1d",
            "group_by[]": "model",
            "limit": _PAGE_LIMIT,
        }

        for bucket in self._paginate(key, "/v1/organizations/usage_report/messages", params):
            bucket_start_str: str = bucket.get("starting_at", "")
            # Parse ISO 8601 bucket start → naive UTC datetime for bucket_hour
            try:
                bucket_dt = datetime.fromisoformat(bucket_start_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, AttributeError):
                continue

            for result in bucket.get("results", []):
                model: str = result.get("model") or "unknown"
                input_tokens: int = result.get("input_tokens") or 0
                output_tokens: int = result.get("output_tokens") or 0
                # Anthropic calls prompt-cache reads "cache_read_input_tokens"
                cached_tokens: int = result.get("cache_read_input_tokens") or 0
                request_count: int = result.get("request_count") or 1

                cost = _compute_cost(model, input_tokens, output_tokens, cached_tokens)

                # Skip rows with no tokens and no cost - identical to OpenAI zero-cost skip
                if cost == 0 and input_tokens == 0 and output_tokens == 0:
                    continue

                yield NormalizedUsageEvent(
                    provider="anthropic",
                    model=model,
                    api_key_label=None,  # not available from org-level usage API
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    cost_usd=cost,
                    request_count=request_count,
                    bucket_hour=bucket_dt,
                    raw_meta={
                        "bucket_end": bucket.get("ending_at"),
                        "cache_creation_input_tokens": result.get("cache_creation_input_tokens") or 0,
                    },
                )

    def _paginate(
        self, key: bytes, path: str, params: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        """Yield each bucket dict from a cursor-paginated Anthropic response."""
        cursor: str | None = None
        while True:
            page_params = dict(params)
            if cursor:
                page_params["page"] = cursor

            try:
                resp = httpx.get(
                    f"{_BASE_URL}{path}",
                    headers=self._headers(key),
                    params=page_params,
                    timeout=30,
                )
            except httpx.RequestError as exc:
                raise ValueError(f"Network error during Anthropic pagination: {exc}") from exc

            if resp.status_code != 200:
                raise ValueError(f"Anthropic {path} returned {resp.status_code}: {resp.text[:200]}")

            body = resp.json()
            for bucket in body.get("data", []):
                yield bucket

            if not body.get("has_more"):
                break
            cursor = body.get("next_page")
            if not cursor:
                break

    def _headers(self, key: bytes) -> dict[str, str]:
        return {
            "x-api-key": key.decode(),
            "anthropic-version": _ANTHROPIC_VERSION,
            # Required by Anthropic usage-report API (BUG-01 fix)
            "anthropic-beta": "usage-report-2024-07-01",
            "Content-Type": "application/json",
        }
