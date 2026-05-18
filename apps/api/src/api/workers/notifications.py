"""
Notification workers:
  send_daily_digests  — Slack digest at 09:00 org-local time
  send_anomaly_alert  — real-time Slack alert on new anomaly
  send_budget_alert   — email at 80% / 100% of budget
"""

import structlog
from celery import shared_task

log = structlog.get_logger()


@shared_task
def send_daily_digests() -> None:
    """
    Enqueue send_slack_digest for every org with Slack connected.
    Sent at 09:00 UTC; per-org timezone adjustment is a V1 improvement.
    """
    raise NotImplementedError


@shared_task(bind=True, max_retries=2)
def send_slack_digest(self, org_id: str) -> None:  # type: ignore[misc]
    """
    Build digest payload and call chat.postMessage.
    Payload: yesterday spend, 7d avg, MoM delta, top 3 cost drivers, open anomalies.
    Records sent_at for idempotency.
    """
    raise NotImplementedError


@shared_task(bind=True, max_retries=3)
def send_anomaly_alert(self, anomaly_id: str) -> None:  # type: ignore[misc]
    """Send real-time Slack alert when a new anomaly is inserted."""
    raise NotImplementedError


@shared_task(bind=True, max_retries=3)
def send_budget_alert(self, budget_id: str, pct: int, org_id: str) -> None:  # type: ignore[misc]
    """
    Email via Resend when spend crosses alert_at_pct (default 80%) or 100%.
    Idempotent: checks audit_events before sending.
    """
    raise NotImplementedError
