from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IntegrationCreate(BaseModel):
    provider: Literal["openai", "anthropic", "gemini"]
    display_name: str = Field(min_length=1, max_length=100)
    api_key: str = Field(min_length=10, description="Raw Admin API key — encrypted immediately")


class IntegrationRead(BaseModel):
    id: str
    org_id: str
    provider: Literal["openai", "anthropic", "gemini"]
    display_name: str
    status: Literal["active", "error", "revoked"]
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
