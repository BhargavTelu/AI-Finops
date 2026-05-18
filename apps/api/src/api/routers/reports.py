from fastapi import APIRouter

from api.deps import OrgDep

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
async def list_reports(org: OrgDep) -> list:
    raise NotImplementedError


@router.get("/{report_id}/download")
async def download_report(report_id: str, org: OrgDep) -> dict:
    """Return a short-lived signed R2 URL for the PDF."""
    raise NotImplementedError


@router.post("/generate", status_code=202)
async def generate_report(org: OrgDep) -> dict:
    """Admin-only: trigger on-demand report generation."""
    raise NotImplementedError
