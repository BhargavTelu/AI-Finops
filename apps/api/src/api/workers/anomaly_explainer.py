"""
Celery task: generate and persist a plain-language explanation for a cost anomaly.

Dispatched by anomaly_detection.detect_org for anomalies with severity ≥ medium,
immediately after the anomaly row is inserted. Skips if an explanation was
already generated within the last 24 hours (cache TTL).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from celery import shared_task
import structlog
from supabase import create_client

from api.config import settings
from api.services.anomaly_explainer import generate_explanation

log = structlog.get_logger()

_CACHE_TTL_HOURS = 24


def _get_supabase() -> Any:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@shared_task
def explain_anomaly(anomaly_id: str) -> None:
    """
    Generate and persist an explanation for the given anomaly.
    Skips if an explanation already exists and is less than 24 hours old.
    """
    db = _get_supabase()

    result = (
        db.table("anomalies")
        .select(
            "id, org_id, scope_kind, scope_value, baseline_usd, actual_usd, "
            "spike_pct, severity, context, explanation_generated_at"
        )
        .eq("id", anomaly_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        log.warning("explain_anomaly_not_found", anomaly_id=anomaly_id)
        return

    anomaly = result.data[0]
    org_id: str = anomaly["org_id"]

    # Skip if explanation is still fresh (24 h cache TTL).
    gen_at_raw: str | None = anomaly.get("explanation_generated_at")
    if gen_at_raw:
        gen_at = datetime.fromisoformat(gen_at_raw.replace("Z", "+00:00"))
        if datetime.now(UTC) - gen_at < timedelta(hours=_CACHE_TTL_HOURS):
            log.debug("explain_anomaly_cached", anomaly_id=anomaly_id)
            return

    explanation = generate_explanation(anomaly, org_id)
    if explanation is None:
        return

    db.table("anomalies").update(
        {
            "explanation": explanation,
            "explanation_generated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("id", anomaly_id).execute()

    log.info("explain_anomaly_done", anomaly_id=anomaly_id, org_id=org_id)
