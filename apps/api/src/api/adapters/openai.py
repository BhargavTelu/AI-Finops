from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterator

import httpx

from api.adapters.base import NormalizedUsageEvent

# Reference: https://platform.openai.com/docs/api-reference/organization/costs
_BASE_URL = "https://api.openai.com/v1"
# OpenAI per-page limits: 1440 for 1m buckets, 168 for 1h buckets, 31 for 1d buckets.
# We use 1d buckets; 31 covers a full calendar month in one page for both endpoints.
_PAGE_LIMIT = 31


class OpenAIAdapter:
    provider = "openai"

    def validate(self, key: bytes) -> bool:
        """
        Ping /v1/organization/costs with a 1-day window to confirm key works.
        Raises ValueError with a human-readable message if the key is invalid.
        """
        now = datetime.now(timezone.utc)
        yesterday = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # Use a 1-day window ending at midnight today (start of today)
        start_ts = int(yesterday.timestamp()) - 86400
        end_ts = int(yesterday.timestamp())

        try:
            resp = httpx.get(
                f"{_BASE_URL}/organization/costs",
                headers=self._headers(key),
                params={"start_time": start_ts, "end_time": end_ts, "limit": 1},
                timeout=15,
            )
        except httpx.RequestError as exc:
            raise ValueError(f"Network error reaching OpenAI: {exc}") from exc

        if resp.status_code == 200:
            return True
        if resp.status_code in (401, 403):
            raise ValueError("Invalid or unauthorized OpenAI Admin key")
        raise ValueError(f"OpenAI returned unexpected status {resp.status_code}")

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        """
        Paginate GET /v1/organization/costs (cursor-based).
        Enriches with /v1/organization/usage/completions for token breakdown.
        bucket_hour is floored to the UTC hour of each bucket's start_time.
        """
        # OpenAI costs API compares dates, not timestamps. A sub-day window
        # where start and end fall on the same calendar date returns 400
        # "end_date must come after start_date". Floor to day boundaries so
        # we always request complete day buckets (delete-before-insert is idempotent).
        start_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if start_day.tzinfo is None:
            start_day = start_day.replace(tzinfo=timezone.utc)
        end_day = (end + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        if end_day.tzinfo is None:
            end_day = end_day.replace(tzinfo=timezone.utc)

        start_ts = int(start_day.timestamp())
        end_ts = int(end_day.timestamp())

        # Pass 1: build token lookup keyed by (start_time_unix, model)
        token_lookup: dict[tuple[int, str], dict[str, int]] = {}
        usage_params: dict[str, Any] = {
            "start_time": start_ts,
            "end_time": end_ts,
            "bucket_width": "1d",
            "group_by[]": "model",
            "limit": _PAGE_LIMIT,
        }
        # /organization/costs group_by only supports: line_item, project_id, user_id, api_key_id
        cost_params: dict[str, Any] = {
            "start_time": start_ts,
            "end_time": end_ts,
            "bucket_width": "1d",
            "group_by[]": "line_item",
            "limit": _PAGE_LIMIT,
        }

        for bucket in self._paginate(key, "/organization/usage/completions", usage_params):
            for result in bucket.get("results", []):
                model = result.get("model") or "unknown"
                token_lookup[(bucket["start_time"], model)] = {
                    "input_tokens": result.get("input_tokens") or 0,
                    "output_tokens": result.get("output_tokens") or 0,
                    "cached_tokens": result.get("input_cached_tokens") or 0,
                    "request_count": result.get("num_model_requests") or 1,
                }

        # Pass 2: yield NormalizedUsageEvent for each cost bucket result
        for bucket in self._paginate(key, "/organization/costs", cost_params):
            for result in bucket.get("results", []):
                model = result.get("line_item") or "unknown"
                amount = result.get("amount", {})
                cost = Decimal(str(amount.get("value") or 0))

                # Skip zero-cost rows (can appear in paginated results)
                if cost == 0:
                    continue

                tokens = token_lookup.get(
                    (bucket["start_time"], model),
                    {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "request_count": 1},
                )

                yield NormalizedUsageEvent(
                    provider="openai",
                    model=model,
                    api_key_label=None,  # not available from org cost API
                    input_tokens=tokens["input_tokens"],
                    output_tokens=tokens["output_tokens"],
                    cached_tokens=tokens["cached_tokens"],
                    cost_usd=cost,
                    request_count=tokens["request_count"],
                    bucket_hour=datetime.fromtimestamp(bucket["start_time"], tz=timezone.utc).replace(tzinfo=None),
                    raw_meta={
                        "bucket_end": bucket.get("end_time"),
                        "currency": amount.get("currency", "usd"),
                    },
                )

    def _paginate(
        self, key: bytes, path: str, params: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        """Yield each bucket dict from a cursor-paginated OpenAI response."""
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
                raise ValueError(f"Network error during OpenAI pagination: {exc}") from exc

            if resp.status_code != 200:
                raise ValueError(f"OpenAI {path} returned {resp.status_code}: {resp.text[:200]}")

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
            "Authorization": f"Bearer {key.decode()}",
            "Content-Type": "application/json",
        }
