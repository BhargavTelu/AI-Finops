from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_cost_usd: Decimal
    total_requests: int
    total_tokens: int
    period_start: date
    period_end: date


class DailyPoint(BaseModel):
    day: date
    cost_usd: Decimal
    requests: int
    group_key: str  # model name, tag value, etc.


class ForecastResult(BaseModel):
    projected_month_end_usd: Decimal
    confidence_low: Decimal
    confidence_high: Decimal
    as_of: datetime
