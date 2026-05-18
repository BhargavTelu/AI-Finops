from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class RecommendationRead(BaseModel):
    id: str
    org_id: str
    type: Literal["model_swap", "caching", "batch", "other"]
    title: str
    description: str
    projected_savings_usd: Decimal | None
    confidence: Decimal | None
    evidence: dict | None
    status: Literal["new", "applied", "dismissed"]
    generated_at: datetime

    model_config = {"from_attributes": True}


class RecommendationUpdate(BaseModel):
    status: Literal["applied", "dismissed"]
