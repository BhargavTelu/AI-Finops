from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class ReportRead(BaseModel):
    id: str
    org_id: str
    type: str
    period_start: date
    period_end: date
    # True when the PDF is uploaded and downloadable. The R2 object key itself
    # is never exposed - downloads go through the presigned-URL endpoint.
    has_file: bool
    generated_at: datetime


class ReportDownloadResponse(BaseModel):
    url: str
    expires_in_seconds: int


class ReportGenerateAccepted(BaseModel):
    status: Literal["queued"] = "queued"
    period_start: date
    period_end: date
