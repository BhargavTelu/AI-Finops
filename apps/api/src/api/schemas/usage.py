from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_cost_usd: Decimal
    total_requests: int
    total_tokens: int
    period_start: date
    period_end: date


class PeriodSummary(BaseModel):
    """Aggregated spend for one time window plus delta vs the equal prior window."""

    total_cost_usd: Decimal
    total_requests: int
    total_tokens: int
    period_start: date
    period_end: date
    period_label: str
    prev_period_cost_usd: Decimal
    pct_change: float | None  # None when prev_period = 0 (no baseline to compare)


class DashboardSummary(BaseModel):
    """All M1 dashboard periods returned in one query."""

    day: PeriodSummary  # latest complete day (yesterday UTC)
    week: PeriodSummary  # last 7 complete days
    month: PeriodSummary  # last 30 complete days
    mtd: PeriodSummary  # 1st of current calendar month → yesterday
    mom_pct_change: float | None  # current MTD vs same-length window in prior month
    last_month_cost_usd: Decimal  # full prior calendar month spend (for MoM callout)


class DailyPoint(BaseModel):
    day: date
    cost_usd: Decimal
    requests: int
    group_key: str  # model name, tag value, etc.


class ExploreRow(BaseModel):
    group_key: str      # dimension value (e.g. "openai", "gpt-4o", "rag-pipeline")
    total_cost_usd: Decimal
    total_requests: int
    total_tokens: int
    pct_of_total: float  # 0–100; 0.0 when grand total is zero


class ForecastResult(BaseModel):
    projected_month_end_usd: Decimal
    confidence_low: Decimal
    confidence_high: Decimal
    as_of: datetime
