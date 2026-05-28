from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

BudgetScopeType = Literal[
    "global",
    "provider",
    "model",
    "feature_tag",
    "team_tag",
    "customer_tag",
    "env_tag",
]


class BudgetCreate(BaseModel):
    scope_type: BudgetScopeType
    # Required for every scope_type except 'global'
    scope_value: str | None = None
    monthly_limit: Decimal = Field(gt=0)
    alert_at_pct: int = Field(default=80, ge=1, le=100)
    hard_cap: bool = False


class BudgetUpdate(BaseModel):
    monthly_limit: Decimal | None = Field(default=None, gt=0)
    alert_at_pct: int | None = Field(default=None, ge=1, le=100)


class BudgetRead(BaseModel):
    id: str
    org_id: str
    scope_type: BudgetScopeType
    scope_value: str | None
    monthly_limit: Decimal
    alert_at_pct: int
    hard_cap: bool
    created_at: datetime
    updated_at: datetime
    # Computed at read time by the route handler - not stored in DB
    current_spend_mtd: Decimal = Decimal("0")
    spent_pct: int = 0

    model_config = {"from_attributes": True}
