from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.deps import OrgDep

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary")
async def get_summary(
    org: OrgDep,
    range: str = Query(default="30d", pattern=r"^\d+d$"),
) -> dict:
    """
    Headline numbers for the dashboard.
    Reads from daily_cost_summaries — never raw usage_events.
    Target: p95 ≤ 800ms.
    """
    raise NotImplementedError


@router.get("/timeseries")
async def get_timeseries(
    org: OrgDep,
    range: str = Query(default="30d", pattern=r"^\d+d$"),
    group_by: str = Query(default="model"),
) -> list:
    """Daily time-series for line/bar charts."""
    raise NotImplementedError


@router.get("/explore")
async def get_explore(org: OrgDep) -> dict:
    """
    Pivot data for Cost Explorer (TanStack Table).
    Supports grouping by provider, model, feature_tag, team_tag, customer_tag, date.
    """
    raise NotImplementedError


@router.get("/forecast")
async def get_forecast(org: OrgDep) -> dict:
    """Month-end spend forecast via linear regression on daily_cost_summaries."""
    raise NotImplementedError


@router.get("/export.csv")
async def export_csv(org: OrgDep) -> StreamingResponse:
    """Stream a CSV export of the Cost Explorer result set."""
    raise NotImplementedError
