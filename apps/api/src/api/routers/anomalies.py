from fastapi import APIRouter, Query

from api.deps import OrgDep

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("")
async def list_anomalies(
    org: OrgDep,
    status: str = Query(default="open"),
) -> list:
    raise NotImplementedError


@router.patch("/{anomaly_id}")
async def update_anomaly(anomaly_id: str, org: OrgDep) -> dict:
    """Acknowledge or dismiss an anomaly."""
    raise NotImplementedError
