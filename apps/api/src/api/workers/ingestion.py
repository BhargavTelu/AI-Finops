"""
Ingestion workers.
  backfill_integration — triggered on key connect (30d historical data)
  refresh_all_integrations — Celery beat every 4h
"""

import structlog
from celery import shared_task

log = structlog.get_logger()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def backfill_integration(self, integration_id: str, org_id: str) -> None:  # type: ignore[misc]
    """
    Pull 30 days of historical data from the provider.
    Triggered immediately after a new integration is created.
    Target: completes in < 5 min for a $20K/mo org.
    """
    raise NotImplementedError


@shared_task
def refresh_all_integrations() -> None:
    """
    Enqueue a refresh job for every active integration.
    Runs every 4 hours via Celery beat.
    """
    raise NotImplementedError


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_integration(self, integration_id: str, org_id: str) -> None:  # type: ignore[misc]
    """Fetch incremental data (since last_synced_at) for a single integration."""
    raise NotImplementedError
