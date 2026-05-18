from fastapi import APIRouter, Query

from api.deps import OrgDep

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
async def list_recommendations(
    org: OrgDep,
    status: str = Query(default="new"),
) -> list:
    raise NotImplementedError


@router.patch("/{recommendation_id}")
async def update_recommendation(recommendation_id: str, org: OrgDep) -> dict:
    """Mark a recommendation as applied or dismissed."""
    raise NotImplementedError
