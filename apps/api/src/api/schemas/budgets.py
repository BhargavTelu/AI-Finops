from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class BudgetCreate(BaseModel):
    scope_type: Literal["global", "tag", "model"]
    scope_value: str | None = None  # tag name or model name; None for global
    monthly_limit: Decimal = Field(gt=0)
    alert_at_pct: int = Field(default=80, ge=1, le=100)
    hard_cap: bool = False


class BudgetRead(BaseModel):
    id: str
    org_id: str
    scope_type: Literal["global", "tag", "model"]
    scope_value: str | None
    monthly_limit: Decimal
    alert_at_pct: int
    hard_cap: bool

    model_config = {"from_attributes": True}
