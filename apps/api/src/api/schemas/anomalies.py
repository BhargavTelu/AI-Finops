from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel


class AnomalyRead(BaseModel):
    id: str
    org_id: str
    detected_at: datetime
    scope_kind: str
    scope_value: str | None
    baseline_usd: Decimal
    actual_usd: Decimal
    spike_pct: int
    severity: Literal["low", "medium", "high"]
    status: Literal["open", "acked", "dismissed"]
    context: dict[str, Any] | None
    explanation: str | None = None

    model_config = {"from_attributes": True}


class AnomalyUpdate(BaseModel):
    status: Literal["acked", "dismissed"]
