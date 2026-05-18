from typing import Literal

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    type: Literal["feature", "team", "customer", "env"]
    name: str = Field(min_length=1, max_length=64)
    color: str | None = None


class TagRead(BaseModel):
    id: str
    org_id: str
    type: Literal["feature", "team", "customer", "env"]
    name: str
    color: str | None

    model_config = {"from_attributes": True}


class TagRuleCreate(BaseModel):
    tag_id: str
    match_type: Literal["regex", "substring", "exact"]
    match_pattern: str = Field(min_length=1)
    priority: int = 100
    enabled: bool = True


class TagRuleRead(BaseModel):
    id: str
    org_id: str
    tag_id: str
    match_type: Literal["regex", "substring", "exact"]
    match_pattern: str
    priority: int
    enabled: bool

    model_config = {"from_attributes": True}
