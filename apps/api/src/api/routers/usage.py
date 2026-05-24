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
from api.deps import AdminOrgDep, OrgDep
from api.schemas.usage import (
    DailyPoint,
    DashboardSummary,
    ExploreRow,
    ForecastResult,
    PeriodSummary,
    TagOverridePatch,
    UsageEventRead,
    UsageSummary,
)

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
    model: str | None = Query(default=None),
    feature_tag: str | None = Query(default=None),
    team_tag: str | None = Query(default=None),
    customer_tag: str | None = Query(default=None),
    env_tag: str | None = Query(default=None),
) -> list[ExploreRow]:
    """
    Pivot data for Cost Explorer (TanStack Table).
    Groups daily_cost_summaries by a single dimension and returns aggregated totals
    with percentage-of-total. Sorted by cost descending.

    Any of the six dimension params can be used as filters simultaneously.
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

    # Apply any active dimension filters
    _filters = {
        "provider": provider,
        "model": model,
        "feature_tag": feature_tag,
        "team_tag": team_tag,
        "customer_tag": customer_tag,
        "env_tag": env_tag,
    }
    for col, val in _filters.items():
        if val is not None:
            q = q.eq(col, val)

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


@router.get("/dashboard")
async def get_dashboard_summary(org: OrgDep) -> DashboardSummary:
    """
    All four dashboard time-window periods in a single DB query.
    Covers: latest day, 7 days, 30 days, MTD — each with delta vs prior equal window.
    Also returns MoM % change and full prior-month cost for the callout widget.
    Reads from daily_cost_summaries only. Target p95 ≤ 800ms.
    """
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    # Fetch far enough back to cover 30d + prior 30d + current MTD + prior-month MTD.
    # first_of_last_month ensures we always capture the full prior calendar month.
    first_of_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    fetch_from = min(first_of_last_month, yesterday - timedelta(days=60))

    db = _get_supabase()
    result = (
        db.table("daily_cost_summaries")
        .select("day, total_cost_usd, total_requests, total_tokens")
        .eq("org_id", org.org_id)
        .gte("day", fetch_from.isoformat())
        .lte("day", yesterday.isoformat())
        .execute()
    )

    # Multiple tag-dimension rows can exist per day — aggregate them all in Python.
    day_totals: dict[date, dict] = {}
    for row in result.data:
        d = date.fromisoformat(row["day"])
        if d not in day_totals:
            day_totals[d] = {"cost": Decimal("0"), "requests": 0, "tokens": 0}
        day_totals[d]["cost"] += Decimal(str(row["total_cost_usd"]))
        day_totals[d]["requests"] += row["total_requests"]
        day_totals[d]["tokens"] += row["total_tokens"]

    def sum_range(start: date, end: date) -> tuple[Decimal, int, int]:
        """Inclusive [start, end]. Returns zeros for inverted or empty ranges."""
        if start > end:
            return Decimal("0"), 0, 0
        cost, reqs, tokens = Decimal("0"), 0, 0
        for d, v in day_totals.items():
            if start <= d <= end:
                cost += v["cost"]
                reqs += v["requests"]
                tokens += v["tokens"]
        return cost, reqs, tokens

    def _pct(current: Decimal, prev: Decimal) -> float | None:
        if prev == 0:
            return None
        return round(float((current - prev) / prev * 100), 1)

    def make_period(
        start: date, end: date, prev_start: date, prev_end: date, label: str
    ) -> PeriodSummary:
        cost, reqs, tokens = sum_range(start, end)
        prev_cost, _, _ = sum_range(prev_start, prev_end)
        return PeriodSummary(
            total_cost_usd=cost,
            total_requests=reqs,
            total_tokens=tokens,
            period_start=start,
            period_end=end,
            period_label=label,
            prev_period_cost_usd=prev_cost,
            pct_change=_pct(cost, prev_cost),
        )

    # Latest complete day (yesterday) vs the day before
    day_period = make_period(
        yesterday, yesterday,
        yesterday - timedelta(days=1), yesterday - timedelta(days=1),
        "Latest day",
    )

    # Last 7 complete days vs the 7 days before that
    w_end = yesterday
    w_start = yesterday - timedelta(days=6)
    week_period = make_period(
        w_start, w_end,
        w_start - timedelta(days=7), w_end - timedelta(days=7),
        "7 days",
    )

    # Last 30 complete days vs the 30 days before that
    m_end = yesterday
    m_start = yesterday - timedelta(days=29)
    month_period = make_period(
        m_start, m_end,
        m_start - timedelta(days=30), m_end - timedelta(days=30),
        "30 days",
    )

    # Month-to-date: 1st of current month → yesterday
    # Prior period: same number of days into last month (apples-to-apples MoM)
    mtd_start = today.replace(day=1)
    mtd_end = yesterday
    last_month_last = mtd_start - timedelta(days=1)
    last_month_first = last_month_last.replace(day=1)
    # How many complete days are in the current MTD window
    mtd_days = max(0, (mtd_end - mtd_start).days)
    prev_mtd_end = last_month_first + timedelta(days=mtd_days)
    mtd_period = make_period(
        mtd_start, mtd_end,
        last_month_first, prev_mtd_end,
        "Month to date",
    )

    # Full prior calendar month cost (displayed in the MoM callout widget)
    last_month_cost, _, _ = sum_range(last_month_first, last_month_last)

    return DashboardSummary(
        day=day_period,
        week=week_period,
        month=month_period,
        mtd=mtd_period,
        mom_pct_change=mtd_period.pct_change,
        last_month_cost_usd=last_month_cost,
    )


@router.get("/forecast")
async def get_forecast(org: OrgDep) -> ForecastResult:
    """Month-end spend forecast via linear regression on daily_cost_summaries."""
    raise HTTPException(status_code=501, detail="Not yet implemented — available in M4")


@router.get("/export.csv")
async def export_csv(org: OrgDep) -> StreamingResponse:
    """Stream a CSV export of the Cost Explorer result set."""
    raise HTTPException(status_code=501, detail="Not yet implemented — available in M4")


# ── Usage event admin endpoints ────────────────────────────────────────────────

@router.get("/events")
async def list_usage_events(
    org: AdminOrgDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[UsageEventRead]:
    """
    Return the most recent usage_events rows for this org (admin-only).
    Used by the tag override UI to show individual events before patching tags.
    Reads usage_events directly (not aggregated summaries) — do not use on the
    hot dashboard path.
    """
    db = _get_supabase()
    result = (
        db.table("usage_events")
        .select(
            "id, provider, model, api_key_label,"
            " feature_tag, team_tag, customer_tag, env_tag,"
            " cost_usd, request_count, input_tokens, output_tokens,"
            " bucket_hour, manual_override"
        )
        .eq("org_id", org.org_id)
        .order("bucket_hour", desc=True)
        .limit(limit)
        .execute()
    )
    return [UsageEventRead(**row) for row in result.data]


@router.patch("/events/{event_id}/tags")
async def override_event_tags(
    event_id: str,
    body: TagOverridePatch,
    org: AdminOrgDep,
) -> UsageEventRead:
    """
    Manually pin tag values on a single usage_events row (admin-only).

    The patched tags survive re-ingestion: the ingestion worker snapshots
    manual_override=true rows before delete-before-insert and restores them
    afterward. Re-runs aggregate_org so daily_cost_summaries reflect the change.
    """
    from datetime import timezone

    db = _get_supabase()

    # Ownership check — 404 if the event doesn't belong to this org
    existing = (
        db.table("usage_events")
        .select("id")
        .eq("id", event_id)
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Usage event not found")

    now = datetime.now(timezone.utc).isoformat()
    patch: dict = {
        "manual_override": True,
        "manual_override_at": now,
        # manual_override_by stores the Clerk user_id (sub claim); resolved to
        # Supabase UUID at display time to avoid a round-trip here.
        "manual_override_by": None,  # updated below if user lookup succeeds
    }
    # Use model_fields_set so explicit null values (tag clearing) are applied,
    # while omitted fields leave the existing DB value untouched.
    if "feature_tag" in body.model_fields_set:
        patch["feature_tag"] = body.feature_tag
    if "team_tag" in body.model_fields_set:
        patch["team_tag"] = body.team_tag
    if "customer_tag" in body.model_fields_set:
        patch["customer_tag"] = body.customer_tag
    if "env_tag" in body.model_fields_set:
        patch["env_tag"] = body.env_tag

    # Best-effort: resolve Clerk sub → Supabase user UUID for the audit column
    user_lookup = (
        db.table("users")
        .select("id")
        .eq("clerk_id", org.user_id)
        .limit(1)
        .execute()
    )
    if user_lookup.data:
        patch["manual_override_by"] = user_lookup.data[0]["id"]

    result = (
        db.table("usage_events")
        .update(patch)
        .eq("id", event_id)
        .eq("org_id", org.org_id)
        .execute()
    )

    # Trigger re-aggregation so daily_cost_summaries reflect the new tags
    from api.workers.aggregation import aggregate_org  # local import avoids circular dep

    aggregate_org.delay(org.org_id)

    return UsageEventRead(**result.data[0])
