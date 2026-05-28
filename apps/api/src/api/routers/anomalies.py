from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status
from supabase import create_client

from api.config import settings
from api.deps import OrgDep
from api.schemas.anomalies import AnomalyRead, AnomalyUpdate

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.get("", response_model=list[AnomalyRead])
async def list_anomalies(
    org: OrgDep,
    status: Literal["open", "acked", "dismissed"] = Query(default="open"),
) -> list[AnomalyRead]:
    db = _get_supabase()
    result = (
        db.table("anomalies")
        .select(
            "id, org_id, detected_at, scope_kind, scope_value, "
            "baseline_usd, actual_usd, spike_pct, severity, status, context, explanation"
        )
        .eq("org_id", org.org_id)
        .eq("status", status)
        .order("detected_at", desc=True)
        .execute()
    )
    return [AnomalyRead.model_validate(row) for row in result.data]


@router.patch("/{anomaly_id}", response_model=AnomalyRead)
async def update_anomaly(
    anomaly_id: str,
    body: AnomalyUpdate,
    org: OrgDep,
) -> AnomalyRead:
    db = _get_supabase()

    # Ownership check - 404 if anomaly doesn't belong to this org.
    existing = (
        db.table("anomalies")
        .select("id")
        .eq("id", anomaly_id)
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Anomaly not found",
        )

    updated = (
        db.table("anomalies")
        .update({"status": body.status})
        .eq("id", anomaly_id)
        .eq("org_id", org.org_id)
        .execute()
    )

    if not updated.data:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update failed",
        )

    return AnomalyRead.model_validate(updated.data[0])
