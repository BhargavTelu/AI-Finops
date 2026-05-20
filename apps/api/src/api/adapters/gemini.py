from datetime import datetime
from typing import Iterator

import httpx
import structlog

from api.adapters.base import NormalizedUsageEvent

# Gemini AI Studio API (generativelanguage.googleapis.com) accepts simple API keys
# for model inference but has no usage-reporting or billing endpoint.
# Cloud Billing API requires OAuth2/service account credentials — a different auth model.
# Cost data collection is deferred to V1. Keys can be connected and validated today.
_BASE_URL = "https://generativelanguage.googleapis.com"

log = structlog.get_logger()


class GeminiAdapter:
    provider = "gemini"

    def validate(self, key: bytes) -> bool:
        """
        Confirm the API key is valid by listing available models.
        Raises ValueError with a user-readable message on auth failure or network error.
        """
        api_key = key.decode()
        try:
            resp = httpx.get(
                f"{_BASE_URL}/v1beta/models",
                params={"key": api_key},
                timeout=10,
            )
        except httpx.RequestError as exc:
            raise ValueError(f"Could not reach Gemini API: {exc}") from exc

        if resp.status_code == 200:
            return True

        raise ValueError(
            f"Gemini API key is invalid or lacks required permissions "
            f"(status {resp.status_code})"
        )

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        # Gemini AI Studio API keys have no usage-reporting endpoint.
        # Returning zero events — integration stays active and keys are preserved.
        # Billing data collection requires Cloud Billing API (OAuth2), deferred to V1.
        log.info(
            "gemini_billing_not_available",
            reason="AI Studio API has no usage reporting endpoint; deferred to V1",
        )
        return
        yield  # makes this a generator so the return type is Iterator
