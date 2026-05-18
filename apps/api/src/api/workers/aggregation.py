"""
Nightly aggregation: usage_events → daily_cost_summaries.
Runs at 00:30 UTC via Celery beat.

Uses UPSERT so it's idempotent — safe to re-run on failure.
"""

import structlog
from celery import shared_task

log = structlog.get_logger()


@shared_task
def aggregate_all_orgs() -> None:
    """Enqueue aggregate_org for every org with active integrations."""
    raise NotImplementedError


@shared_task
def aggregate_org(org_id: str) -> None:
    """
    GROUP BY (day, provider, model, *_tag) → UPSERT daily_cost_summaries.
    Only processes yesterday's data to avoid partial-day noise.
    """
    raise NotImplementedError
