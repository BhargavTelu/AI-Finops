from datetime import datetime
from typing import Iterator

from api.adapters.base import NormalizedUsageEvent

# Reference:
#   GET /v1/organizations/usage_report/messages
#   GET /v1/organizations/cost_report
_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter:
    provider = "anthropic"

    def validate(self, key: bytes) -> bool:
        """Ping usage_report with a 1-day window to confirm key works."""
        raise NotImplementedError

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        """
        Paginate /v1/organizations/usage_report/messages and /cost_report.
        Header: x-api-key, anthropic-version.
        """
        raise NotImplementedError

    def _headers(self, key: bytes) -> dict[str, str]:
        return {
            "x-api-key": key.decode(),
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
