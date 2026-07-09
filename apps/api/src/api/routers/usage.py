"""
Usage data endpoints - read from daily_cost_summaries (never raw usage_events).
All queries scoped to the requesting org. Target p95 ≤ 800ms.
"""

import calendar
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query

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
from api.services.db import fetch_all_pages, get_supabase
from api.services.forecast import forecast_month_end

router = APIRouter(prefix="/usage", tags=["usage"])

# (day, model) grouping key for the timeseries endpoint
_DayModelKey = tuple[date, str]


def _get_supabase() -> Any:
    return get_supabase()


def _parse_range(range_param: str) -> tuple[date, date]:
    """Convert "30d" → (period_start, period_end) using complete days only.

    period_end is always yesterday UTC - the last day guaranteed to be fully
    aggregated. period_start is period_end - (days - 1) so the window is
    exactly `days` calendar days inclusive.
    """
    days = int(range_param[:-1])
    today = datetime.now(UTC).date()
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=days - 1)
    return period_start, period_end


@router.get("/summary")
def get_summary(
    org: OrgDep,
    range_: str = Query(default="30d", alias="range", pattern=r"^\d+d$"),
) -> UsageSummary:
    """
    Headline numbers for the dashboard.
    Reads from daily_cost_summaries - never raw usage_events.
    Target: p95 ≤ 800ms.
    """
    period_start, period_end = _parse_range(range_)
    db = _get_supabase()

    # Paged past the PostgREST max-rows cap so totals stay correct for orgs
    # whose range covers more than one page of summary rows.
    rows = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("total_cost_usd, total_requests, total_tokens")
        .eq("org_id", org.org_id)
        .gte("day", period_start.isoformat())
        .lte("day", period_end.isoformat())
    )

    total_cost = sum((Decimal(str(r["total_cost_usd"])) for r in rows), Decimal("0"))
    total_requests = sum(r["total_requests"] for r in rows)
    total_tokens = sum(r["total_tokens"] for r in rows)

    return UsageSummary(
        total_cost_usd=total_cost,
        total_requests=total_requests,
        total_tokens=total_tokens,
        period_start=period_start,
        period_end=period_end,
    )


@router.get("/timeseries")
def get_timeseries(
    org: OrgDep,
    range_: str = Query(default="30d", alias="range", pattern=r"^\d+d$"),
    group_by: str = Query(default="model"),
) -> list[DailyPoint]:
    """Daily time-series for line/bar charts."""
    # Only "model" is supported in M1. Tags grouping comes in M2 with the tag engine.
    if group_by != "model":
        raise HTTPException(
            status_code=400, detail=f"Unsupported group_by: {group_by}. Use 'model'."
        )

    period_start, period_end = _parse_range(range_)
    db = _get_supabase()

    # Paged read; output order comes from the points.sort() below, not SQL.
    rows = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("day, model, total_cost_usd, total_requests")
        .eq("org_id", org.org_id)
        .gte("day", period_start.isoformat())
        .lte("day", period_end.isoformat())
    )

    # Group by (day, model) - multiple tag combinations can produce separate rows
    # for the same day+model pair, so we aggregate in Python.
    groups: dict[_DayModelKey, dict[str, Any]] = defaultdict(
        lambda: {"cost": Decimal("0"), "reqs": 0}
    )
    for r in rows:
        k: _DayModelKey = (date.fromisoformat(r["day"]), r["model"])
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
def get_explore(
    org: OrgDep,
    range_: str = Query(default="30d", alias="range", pattern=r"^\d+d$"),
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
            detail=(
                f"Invalid group_by '{group_by}'. "
                f"Must be one of: {', '.join(sorted(_EXPLORE_DIMENSIONS))}"
            ),
        )

    period_start, period_end = _parse_range(range_)
    db = _get_supabase()

    # Apply any active dimension filters
    _filters = {
        "provider": provider,
        "model": model,
        "feature_tag": feature_tag,
        "team_tag": team_tag,
        "customer_tag": customer_tag,
        "env_tag": env_tag,
    }

    def build_query() -> Any:
        q = (
            db.table("daily_cost_summaries")
            .select(f"{group_by}, total_cost_usd, total_requests, total_tokens")
            .eq("org_id", org.org_id)
            .gte("day", period_start.isoformat())
            .lte("day", period_end.isoformat())
        )
        for col, val in _filters.items():
            if val is not None:
                q = q.eq(col, val)
        return q

    rows_data = fetch_all_pages(build_query)

    # Group in Python - multiple rows per dimension value when other tag columns differ
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cost": Decimal("0"), "reqs": 0, "tokens": 0}
    )
    for r in rows_data:
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
def get_dashboard_summary(org: OrgDep) -> DashboardSummary:
    """
    All four dashboard time-window periods in a single DB query.
    Covers: latest day, 7 days, 30 days, MTD - each with delta vs prior equal window.
    Also returns MoM % change and full prior-month cost for the callout widget.
    Reads from daily_cost_summaries only. Target p95 ≤ 800ms.
    """
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    # Fetch far enough back to cover 30d + prior 30d + current MTD + prior-month MTD.
    # first_of_last_month ensures we always capture the full prior calendar month.
    first_of_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    fetch_from = min(first_of_last_month, yesterday - timedelta(days=60))

    db = _get_supabase()
    summary_rows = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("day, total_cost_usd, total_requests, total_tokens")
        .eq("org_id", org.org_id)
        .gte("day", fetch_from.isoformat())
        .lte("day", yesterday.isoformat())
    )

    # Multiple tag-dimension rows can exist per day - aggregate them all in Python.
    day_totals: dict[date, dict[str, Any]] = {}
    for row in summary_rows:
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
        yesterday,
        yesterday,
        yesterday - timedelta(days=1),
        yesterday - timedelta(days=1),
        "Latest day",
    )

    # Last 7 complete days vs the 7 days before that
    w_end = yesterday
    w_start = yesterday - timedelta(days=6)
    week_period = make_period(
        w_start,
        w_end,
        w_start - timedelta(days=7),
        w_end - timedelta(days=7),
        "7 days",
    )

    # Last 30 complete days vs the 30 days before that
    m_end = yesterday
    m_start = yesterday - timedelta(days=29)
    month_period = make_period(
        m_start,
        m_end,
        m_start - timedelta(days=30),
        m_end - timedelta(days=30),
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
        mtd_start,
        mtd_end,
        last_month_first,
        prev_mtd_end,
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


def _fetch_daily_totals(db: Any, org_id: str, start: date, end: date) -> dict[date, Decimal]:
    """Sum daily_cost_summaries per day over [start, end]. Paged."""
    if start > end:
        return {}
    rows = fetch_all_pages(
        lambda: db.table("daily_cost_summaries")
        .select("day, total_cost_usd")
        .eq("org_id", org_id)
        .gte("day", start.isoformat())
        .lte("day", end.isoformat())
    )
    totals: dict[date, Decimal] = {}
    for row in rows:
        day = date.fromisoformat(row["day"])
        totals[day] = totals.get(day, Decimal("0")) + Decimal(str(row["total_cost_usd"]))
    return totals


def _fill_gaps(totals: dict[date, Decimal], start: date, end: date) -> list[Decimal]:
    """Dense daily series over [start, end]; days without rows count as $0."""
    if start > end:
        return []
    return [
        totals.get(start + timedelta(days=offset), Decimal("0"))
        for offset in range((end - start).days + 1)
    ]


@router.get("/forecast")
def get_forecast(org: OrgDep) -> ForecastResult:
    """Month-end spend forecast (FR-24). Linear regression over this month's
    complete days; trailing-30d average when fewer than 5 days have elapsed."""
    db = _get_supabase()
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    mtd_totals = _fetch_daily_totals(db, org.org_id, month_start, yesterday)
    mtd_daily = _fill_gaps(mtd_totals, month_start, yesterday)

    trailing_totals = _fetch_daily_totals(db, org.org_id, yesterday - timedelta(days=29), yesterday)
    trailing_daily = _fill_gaps(trailing_totals, yesterday - timedelta(days=29), yesterday)
    # Gap-filling turns "no rows at all" into an all-zeros series, which the
    # regression would dutifully forecast as $0.00 - distinguish real zero
    # history from no history before forecasting.
    if not any(trailing_daily):
        trailing_daily = []
    if not any(mtd_daily) and not trailing_daily:
        raise HTTPException(status_code=404, detail="Not enough spend data to forecast.")

    result = forecast_month_end(mtd_daily, trailing_daily, days_in_month)
    if result is None:
        raise HTTPException(status_code=404, detail="Not enough spend data to forecast.")

    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    last_month_total = sum(
        _fetch_daily_totals(db, org.org_id, prev_month_start, prev_month_end).values(),
        Decimal("0"),
    )
    delta_pct = (
        float((result.projected_month_end_usd - last_month_total) / last_month_total * 100)
        if last_month_total > 0
        else None
    )

    return ForecastResult(
        projected_month_end_usd=result.projected_month_end_usd,
        confidence_low=result.confidence_low,
        confidence_high=result.confidence_high,
        as_of=datetime.now(UTC),
        method=result.method,
        last_month_cost_usd=last_month_total,
        delta_vs_last_month_pct=delta_pct,
    )


# ── Usage event admin endpoints ────────────────────────────────────────────────


@router.get("/events")
def list_usage_events(
    org: AdminOrgDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[UsageEventRead]:
    """
    Return the most recent usage_events rows for this org (admin-only).
    Used by the tag override UI to show individual events before patching tags.
    Reads usage_events directly (not aggregated summaries) - do not use on the
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
def override_event_tags(
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

    db = _get_supabase()

    # Ownership check - 404 if the event doesn't belong to this org
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

    now = datetime.now(UTC).isoformat()
    patch: dict[str, Any] = {
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
    user_lookup = db.table("users").select("id").eq("clerk_id", org.user_id).limit(1).execute()
    if user_lookup.data:
        patch["manual_override_by"] = user_lookup.data[0]["id"]

    result = (
        db.table("usage_events").update(patch).eq("id", event_id).eq("org_id", org.org_id).execute()
    )

    # Trigger re-aggregation so daily_cost_summaries reflect the new tags
    from api.workers.aggregation import aggregate_org  # local import avoids circular dep

    aggregate_org.delay(org.org_id)

    return UsageEventRead(**result.data[0])
