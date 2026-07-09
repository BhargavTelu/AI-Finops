import sys

from celery import Celery
from celery.schedules import crontab

from api.config import settings

celery_app = Celery(
    "spendops-ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "api.workers.ingestion",
        "api.workers.aggregation",
        "api.workers.anomaly_detection",
        "api.workers.budget_checks",
        "api.workers.notifications",
        "api.workers.recommendations",
        "api.workers.anomaly_explainer",
        "api.workers.reports",
    ],
)

# Windows (local dev) does not support fork-based multiprocessing or SIGUSR1.
# Use the 'solo' pool so tasks run in the main process without spawning children.
# On Linux (Railway production), prefork is used with a hard time limit.
_is_windows = sys.platform == "win32"

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_pool="solo" if _is_windows else "prefork",
    worker_concurrency=1 if _is_windows else None,
    # Soft time limit uses SIGUSR1 - not available on Windows.
    task_soft_time_limit=None if _is_windows else 300,
    task_time_limit=600,  # 10 min hard kill (SIGKILL, works everywhere)
    worker_max_tasks_per_child=None if _is_windows else 100,
)

celery_app.conf.beat_schedule = {
    # Nightly pipeline at 00:30 UTC (after midnight boundary)
    "nightly-aggregation": {
        "task": "api.workers.aggregation.aggregate_all_orgs",
        "schedule": crontab(hour=0, minute=30),
    },
    # Provider data refresh every 4 hours
    "refresh-integrations": {
        "task": "api.workers.ingestion.refresh_all_integrations",
        "schedule": crontab(minute=0, hour="*/4"),
    },
    # Slack daily digest ~09:00 UTC (per-org timezone adjustment in task)
    "slack-digest": {
        "task": "api.workers.notifications.send_daily_digests",
        "schedule": crontab(hour=9, minute=0),
    },
    # Nightly anomaly detection (after aggregation at 00:30)
    "detect-anomalies": {
        "task": "api.workers.anomaly_detection.detect_all_orgs",
        "schedule": crontab(hour=1, minute=0),
    },
    # Nightly budget checks (after anomaly detection at 01:00)
    "check-budgets": {
        "task": "api.workers.budget_checks.check_all_orgs",
        "schedule": crontab(hour=2, minute=0),
    },
    # Nightly recommendations (after budget checks at 02:00)
    "generate-recommendations": {
        "task": "api.workers.recommendations.generate_all_org_recommendations",
        "schedule": crontab(hour=2, minute=30),
    },
    # Monthly CFO PDF on the 1st at 06:00 UTC (after the night's aggregation
    # has finalized the last day of the previous month)
    "generate-monthly-reports": {
        "task": "api.workers.reports.generate_monthly_reports",
        "schedule": crontab(day_of_month="1", hour=6, minute=0),
    },
    # Weekly email digest for orgs without Slack (Mondays 09:00 UTC,
    # same hour as the Slack digest so numbers line up)
    "weekly-email-digest": {
        "task": "api.workers.notifications.send_weekly_email_digests",
        "schedule": crontab(hour=9, minute=0, day_of_week="mon"),
    },
}
