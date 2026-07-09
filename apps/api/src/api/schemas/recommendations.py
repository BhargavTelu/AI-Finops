from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel


class RecommendationRead(BaseModel):
    id: str
    org_id: str
    type: Literal["model_swap", "caching", "batch", "other"]
    title: str
    description: str
    projected_savings_usd: Decimal | None
    confidence: Decimal | None
    evidence: dict[str, Any] | None
    status: Literal["new", "applied", "dismissed"]
    scope_value: str | None
    generated_at: datetime
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


class RecommendationUpdate(BaseModel):
    status: Literal["applied", "dismissed"]
