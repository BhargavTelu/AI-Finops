"""
Nightly anomaly detection — runs at 01:00 UTC (after aggregation).
Algorithm: rolling mean + 2σ over 7 days; $10 floor; ≥14 days of data required.
See architecture.md § Anomaly Algorithm and services/anomaly.py.
"""

import structlog
from celery import shared_task

log = structlog.get_logger()


@shared_task
def detect_all_orgs() -> None:
    """Enqueue detect_org for every org with ≥14 days of data."""
    raise NotImplementedError


@shared_task
def detect_org(org_id: str) -> None:
    """
    For each (model, feature_tag, team_tag, customer_tag) group:
      1. Load last 15 days of daily_cost_summaries
      2. Call services.anomaly.detect_anomalies
      3. INSERT anomaly row if threshold crossed
      4. Enqueue notification if new anomaly
    """
    raise NotImplementedError
