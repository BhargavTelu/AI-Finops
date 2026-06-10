"""
Generate a plain-language explanation for a detected cost anomaly using
Claude Haiku. Respects the platform-wide 3-calls/org/day
Redis rate limit defined in settings.ai_calls_per_org_per_day.

Pure function - no DB access here. Side effects belong in the Celery task.
"""

from datetime import date, timezone
from typing import Any

import anthropic
import redis as redis_lib
import structlog

from api.config import settings

log = structlog.get_logger()

_REDIS_KEY_PREFIX = "ai:calls"
# Cheapest current-generation model. The previous value
# ("claude-3-haiku-20241022") never existed as a model ID, so every call
# 404'd and explanations silently stayed NULL.
_MODEL = "claude-haiku-4-5"


def _redis() -> redis_lib.Redis:  # type: ignore[type-arg]
    return redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)


def _rate_key(org_id: str) -> str:
    today = date.today().isoformat()
    return f"{_REDIS_KEY_PREFIX}:{org_id}:{today}"


def is_rate_limited(org_id: str) -> bool:
    """Return True when the org has exhausted its daily AI call budget."""
    r = _redis()
    raw = r.get(_rate_key(org_id))
    if raw is None:
        return False
    return int(raw) >= settings.ai_calls_per_org_per_day


def _consume_quota(org_id: str) -> None:
    """Increment counter; set 25 h TTL on first write (covers midnight rollover)."""
    r = _redis()
    key = _rate_key(org_id)
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, 90_000)  # 25 hours
    pipe.execute()


def generate_explanation(anomaly: dict[str, Any], org_id: str) -> str | None:
    """
    Call Claude Haiku and return a 2-3 sentence explanation for the anomaly.
    Returns None if:
      - ANTHROPIC_API_KEY is not configured
      - the org has exceeded 3 AI calls today
      - the Anthropic API request fails
    """
    if not settings.anthropic_api_key:
        log.debug("anomaly_explainer_no_key", org_id=org_id)
        return None

    if is_rate_limited(org_id):
        log.info(
            "anomaly_explainer_rate_limited",
            org_id=org_id,
            limit=settings.ai_calls_per_org_per_day,
        )
        return None

    scope = anomaly.get("scope_value") or anomaly.get("scope_kind", "unknown")
    spike_pct = anomaly.get("spike_pct", 0)
    baseline = anomaly.get("baseline_usd", "0")
    actual = anomaly.get("actual_usd", "0")
    severity = anomaly.get("severity", "low")

    context = anomaly.get("context") or {}
    tag_parts = [
        f"{k.replace('_tag', '')}: {v}"
        for k, v in context.items()
        if v and k.endswith("_tag")
    ]
    context_str = ", ".join(tag_parts) if tag_parts else "none"

    prompt = (
        f"A cost anomaly was detected for an AI API workload.\n"
        f"Scope: {scope}\n"
        f"Severity: {severity}\n"
        f"Spike: +{spike_pct}% above 7-day rolling baseline\n"
        f"Baseline: ${baseline}/day  →  Actual: ${actual}\n"
        f"Context tags: {context_str}\n\n"
        f"In 2-3 sentences, explain what likely caused this spike and what the team "
        f"should investigate. Be specific and actionable. Do not repeat the numbers."
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        _consume_quota(org_id)
        text: str = message.content[0].text  # type: ignore[union-attr]
        return text.strip()
    except Exception as exc:
        log.error("anomaly_explainer_api_failed", org_id=org_id, error=str(exc))
        return None
