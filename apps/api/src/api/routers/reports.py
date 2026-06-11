"""
CFO PDF report endpoints (Phase 1 / FR-22).

- GET  /reports                 list this org's reports, newest period first
- GET  /reports/:id/download    short-lived presigned R2 URL (key never exposed)
- POST /reports/generate        on-demand month-to-date report (sales-demo path);
                                Redis-capped at 3 generations/org/day, fail-open
                                if Redis is unreachable.
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
import redis as redis_lib
import structlog

from api.config import settings
from api.deps import OrgDep
from api.schemas.reports import ReportDownloadResponse, ReportGenerateAccepted, ReportRead
from api.services.db import get_supabase
from api.services.storage import presign_download

log = structlog.get_logger()

router = APIRouter(prefix="/reports", tags=["reports"])

_DOWNLOAD_TTL_SECONDS = 600
_GENERATE_LIMIT_PER_DAY = 3


def _get_supabase():
    return get_supabase()


def _to_read(row: dict) -> ReportRead:
    return ReportRead(
        id=row["id"],
        org_id=row["org_id"],
        type=row["type"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        has_file=bool(row.get("r2_object_key")),
        generated_at=row["generated_at"],
    )


@router.get("")
def list_reports(org: OrgDep) -> list[ReportRead]:
    db = _get_supabase()
    result = (
        db.table("reports")
        .select("id, org_id, type, period_start, period_end, r2_object_key, generated_at")
        .eq("org_id", org.org_id)
        .order("period_start", desc=True)
        .execute()
    )
    return [_to_read(row) for row in result.data]


@router.get("/{report_id}/download")
def download_report(report_id: str, org: OrgDep) -> ReportDownloadResponse:
    """Return a short-lived signed R2 URL for the PDF."""
    db = _get_supabase()
    result = (
        db.table("reports")
        .select("id, r2_object_key")
        .eq("id", report_id)
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Report not found")

    object_key = result.data[0].get("r2_object_key")
    if not object_key:
        raise HTTPException(
            status_code=404,
            detail="Report file is not available. Regenerate the report to create one.",
        )
    return ReportDownloadResponse(
        url=presign_download(object_key, _DOWNLOAD_TTL_SECONDS),
        expires_in_seconds=_DOWNLOAD_TTL_SECONDS,
    )


def _generate_rate_limited(org_id: str) -> bool:
    """
    Allow 3 on-demand generations per org per UTC day. Fail-open: a Redis
    outage should never block a sales demo over a nice-to-have limit.
    """
    key = f"reports:generate:{org_id}:{date.today().isoformat()}"
    try:
        r = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 90_000)  # 25h - covers midnight rollover
        count, _ = pipe.execute()
        return int(count) > _GENERATE_LIMIT_PER_DAY
    except Exception as exc:
        log.warning("report_rate_limit_unavailable", error=str(exc))
        return False


@router.post("/generate", status_code=202)
def generate_report(org: OrgDep) -> ReportGenerateAccepted:
    """Queue an on-demand month-to-date report for the current month."""
    if _generate_rate_limited(org.org_id):
        raise HTTPException(
            status_code=429,
            detail=f"Limit of {_GENERATE_LIMIT_PER_DAY} on-demand reports per day reached.",
        )

    today = datetime.now(UTC).date()
    period_start = today.replace(day=1)

    # Local import: keeps router import-time free of Celery task registration
    # order concerns (celery_app must be imported first in api.main).
    from api.workers.reports import generate_org_report

    generate_org_report.delay(
        org.org_id,
        period_start.isoformat(),
        today.isoformat(),
        force=True,
        send_email=False,
    )
    log.info("report_generate_queued", org_id=org.org_id, period_start=period_start.isoformat())
    return ReportGenerateAccepted(period_start=period_start, period_end=today)
