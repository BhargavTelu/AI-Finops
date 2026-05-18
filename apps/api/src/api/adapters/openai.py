from datetime import datetime
from typing import Iterator

import httpx

from api.adapters.base import NormalizedUsageEvent

# Reference: https://platform.openai.com/docs/api-reference/organization/costs
_BASE_URL = "https://api.openai.com/v1"


class OpenAIAdapter:
    provider = "openai"

    def validate(self, key: bytes) -> bool:
        """Ping /v1/organization/costs with a 1-day window to confirm key works."""
        raise NotImplementedError

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        """
        Paginate GET /v1/organization/costs (cursor-based).
        Also enriches with /v1/organization/usage/completions for token breakdown.
        Refresh cadence: every 4 hours (enforced by Celery beat).
        """
        raise NotImplementedError

    def _headers(self, key: bytes) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {key.decode()}",
            "Content-Type": "application/json",
        }
