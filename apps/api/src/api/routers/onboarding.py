"""
Activation checklist status (Phase 3) - four existence checks driving the
dashboard onboarding card. Existence queries only, no new tables.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import OrgDep
from api.services.db import get_supabase

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStatus(BaseModel):
    provider_connected: bool
    tag_rule_created: bool
    slack_connected: bool
    budget_created: bool


def _get_supabase() -> Any:
    return get_supabase()


def _exists(db: Any, table: str, org_id: str, **filters: str) -> bool:
    query = db.table(table).select("id").eq("org_id", org_id)
    for column, value in filters.items():
        query = query.eq(column, value)
    result = query.limit(1).execute()
    return bool(result.data)


@router.get("/status")
def get_status(org: OrgDep) -> OnboardingStatus:
    db = _get_supabase()
    return OnboardingStatus(
        provider_connected=_exists(db, "integrations", org.org_id, status="active"),
        tag_rule_created=_exists(db, "tag_rules", org.org_id),
        slack_connected=_exists(db, "slack_integrations", org.org_id),
        budget_created=_exists(db, "budgets", org.org_id),
    )
