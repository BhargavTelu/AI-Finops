"""
Server-side PostHog capture for funnel events that don't have a reliable
client-side moment: signup and org_created fire from the Clerk webhook,
checkout_completed from the Stripe webhook.

httpx straight to /capture - no PostHog SDK (~no new deps). Fail-soft by
design: analytics must never break a webhook handler, and a missing key
just disables capture. Properties carry ids only - no emails, no names
(hard rule #4 extends to analytics).
"""

import httpx
import structlog

from api.config import settings

log = structlog.get_logger()


def capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    if not settings.posthog_api_key:
        return
    try:
        httpx.post(
            f"{settings.posthog_host}/capture/",
            json={
                "api_key": settings.posthog_api_key,
                "event": event,
                "distinct_id": distinct_id,
                "properties": properties or {},
            },
            timeout=5.0,
        )
    except Exception as exc:  # fail-soft: never let analytics break a webhook
        log.warning("posthog_capture_failed", event=event, error=str(exc))
