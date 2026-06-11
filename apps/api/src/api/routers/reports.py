from fastapi import APIRouter, HTTPException

from api.deps import OrgDep

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(org: OrgDep) -> list:
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")


@router.get("/{report_id}/download")
def download_report(report_id: str, org: OrgDep) -> dict:
    """Return a short-lived signed R2 URL for the PDF."""
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")


@router.post("/generate", status_code=202)
def generate_report(org: OrgDep) -> dict:
    """Admin-only: trigger on-demand report generation."""
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")
