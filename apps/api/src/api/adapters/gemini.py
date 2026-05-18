from datetime import datetime
from typing import Iterator

from api.adapters.base import NormalizedUsageEvent

# NOTE (M2 week 1): Verify Cloud Billing API granularity before building.
# If per-model breakdown is unavailable, defer to V1.
# Reference: Google Cloud Billing API


class GeminiAdapter:
    provider = "gemini"

    def validate(self, key: bytes) -> bool:
        raise NotImplementedError

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        raise NotImplementedError
