"""
GET  /recommendations?status=new|applied|dismissed  - list for the org, ordered by savings
PATCH /recommendations/:id                          - mark applied or dismissed
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from supabase import create_client

from api.config import settings
from api.deps import OrgDep
from api.schemas.recommendations import RecommendationRead, RecommendationUpdate

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.get("", response_model=list[RecommendationRead])
async def list_recommendations(
    org: OrgDep,
    status: Literal["new", "applied", "dismissed"] = Query(default="new"),
) -> list[RecommendationRead]:
    db = _get_supabase()
    result = (
        db.table("recommendations")
        .select(
            "id, org_id, type, title, description, projected_savings_usd, "
            "confidence, evidence, status, scope_value, generated_at, resolved_at"
        )
        .eq("org_id", org.org_id)
        .eq("status", status)
        .order("projected_savings_usd", desc=True, nullsfirst=False)
        .execute()
    )
    return [RecommendationRead.model_validate(row) for row in result.data]


@router.patch("/{recommendation_id}", response_model=RecommendationRead)
async def update_recommendation(
    recommendation_id: str,
    body: RecommendationUpdate,
    org: OrgDep,
) -> RecommendationRead:
    db = _get_supabase()

    # Ownership check - 404 if rec doesn't belong to this org.
    existing = (
        db.table("recommendations")
        .select("id")
        .eq("id", recommendation_id)
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        )

    updated = (
        db.table("recommendations")
        .update(
            {
                "status": body.status,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", recommendation_id)
        .eq("org_id", org.org_id)
        .execute()
    )

    if not updated.data:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update failed",
        )

    return RecommendationRead.model_validate(updated.data[0])
