"""
Usage data endpoints — read from daily_cost_summaries (never raw usage_events).
All queries scoped to the requesting org. Target p95 ≤ 800ms.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from supabase import create_client

from api.config import settings
from api.deps import OrgDep
from api.schemas.usage import DailyPoint, ExploreRow, ForecastResult, UsageSummary

router = APIRouter(prefix="/usage", tags=["usage"])


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _parse_range(range_param: str) -> tuple[date, date]:
    """Convert "30d" → (period_start, period_end) using complete days only.

    period_end is always yesterday UTC — the last day guaranteed to be fully
    aggregated. period_start is period_end - (days - 1) so the window is
    exactly `days` calendar days inclusive.
    """
    days = int(range_param[:-1])
    today = datetime.now(timezone.utc).date()
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=days - 1)
    return period_start, period_end


@router.get("/summary")
async def get_summary(
    org: OrgDep,
    range: str = Query(default="30d", pattern=r"^\d+d$"),
) -> UsageSummary:
    """
    Headline numbers for the dashboard.
    Reads from daily_cost_summaries — never raw usage_events.
    Target: p95 ≤ 800ms.
    """
    period_start, period_end = _parse_range(range)
    db = _get_supabase()

    result = (
        db.table("daily_cost_summaries")
        .select("total_cost_usd, total_requests, total_tokens")
        .eq("org_id", org.org_id)
        .gte("day", period_start.isoformat())
        .lte("day", period_end.isoformat())
        .execute()
    )

    total_cost = sum((Decimal(str(r["total_cost_usd"])) for r in result.data), Decimal("0"))
    total_requests = sum(r["total_requests"] for r in result.data)
    total_tokens = sum(r["total_tokens"] for r in result.data)

    return UsageSummary(
        total_cost_usd=total_cost,
        total_requests=total_requests,
        total_tokens=total_tokens,
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/timeseries")
async def get_timeseries(
    org: OrgDep,
    range: str = Query(default="30d", pattern=r"^\d+d$"),
    group_by: str = Query(default="model"),
) -> list[DailyPoint]:
    """Daily time-series for line/bar charts."""
    # Only "model" is supported in M1. Tags grouping comes in M2 with the tag engine.
    if group_by != "model":
        raise HTTPException(status_code=400, detail=f"Unsupported group_by: {group_by}. Use 'model'.")

    period_start, period_end = _parse_range(range)
    db = _get_supabase()

    result = (
        db.table("daily_cost_summaries")
        .select("day, model, total_cost_usd, total_requests")
        .eq("org_id", org.org_id)
        .gte("day", period_start.isoformat())
        .lte("day", period_end.isoformat())
        .order("day", desc=False)
        .execute()
    )

    # Group by (day, model) — multiple tag combinations can produce separate rows
    # for the same day+model pair, so we aggregate in Python.
    GroupKey = tuple[date, str]
    groups: dict[GroupKey, dict] = defaultdict(lambda: {"cost": Decimal("0"), "reqs": 0})
    for r in result.data:
        k: GroupKey = (date.fromisoformat(r["day"]), r["model"])
        groups[k]["cost"] += Decimal(str(r["total_cost_usd"]))
        groups[k]["reqs"] += r["total_requests"]

    points = [
        DailyPoint(
            day=k[0],
            cost_usd=v["cost"],
            requests=v["reqs"],
            group_key=k[1],
        )
        for k, v in groups.items()
    ]
    points.sort(key=lambda p: (p.day, p.group_key))
    return points


_EXPLORE_DIMENSIONS = frozenset(
    {"provider", "model", "feature_tag", "team_tag", "customer_tag", "env_tag"}
)


@router.get("/explore")
async def get_explore(
    org: OrgDep,
    range: str = Query(default="30d", pattern=r"^\d+d$"),
    group_by: str = Query(default="model"),
    provider: str | None = Query(default=None),
) -> list[ExploreRow]:
    """
    Pivot data for Cost Explorer (TanStack Table).
    Groups daily_cost_summaries by a single dimension and returns aggregated totals
    with percentage-of-total. Sorted by cost descending.
    """
    if group_by not in _EXPLORE_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid group_by '{group_by}'. Must be one of: {', '.join(sorted(_EXPLORE_DIMENSIONS))}",
        )

    period_start, period_end = _parse_range(range)
    db = _get_supabase()

    q = (
        db.table("daily_cost_summaries")
        .select(f"{group_by}, total_cost_usd, total_requests, total_tokens")
        .eq("org_id", org.org_id)
        .gte("day", period_start.isoformat())
        .lte("day", period_end.isoformat())
    )
    if provider:
        q = q.eq("provider", provider)

    result = q.execute()

    # Group in Python — multiple rows per dimension value when other tag columns differ
    groups: dict[str, dict] = defaultdict(
        lambda: {"cost": Decimal("0"), "reqs": 0, "tokens": 0}
    )
    for r in result.data:
        key: str = r[group_by] or ""  # tags default to "" in DB; guard against None
        groups[key]["cost"] += Decimal(str(r["total_cost_usd"]))
        groups[key]["reqs"] += r["total_requests"]
        groups[key]["tokens"] += r["total_tokens"]

    grand_total = sum(v["cost"] for v in groups.values())

    rows = [
        ExploreRow(
            group_key=k,
            total_cost_usd=v["cost"],
            total_requests=v["reqs"],
            total_tokens=v["tokens"],
            pct_of_total=float(v["cost"] / grand_total * 100) if grand_total else 0.0,
        )
        for k, v in groups.items()
    ]
    rows.sort(key=lambda r: r.total_cost_usd, reverse=True)
    return rows


@router.get("/forecast")
async def get_forecast(org: OrgDep) -> ForecastResult:
    """Month-end spend forecast via linear regression on daily_cost_summaries."""
    raise NotImplementedError


@router.get("/export.csv")
async def export_csv(org: OrgDep) -> StreamingResponse:
    """Stream a CSV export of the Cost Explorer result set."""
    raise NotImplementedError
