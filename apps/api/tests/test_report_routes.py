"""
Unit tests for GET/POST /reports routes.
Supabase + Redis + Celery dispatch mocked. Auth dependency overridden.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
REPORT_ID = "rrrrrrrr-0000-0000-0000-000000000001"

_AUTH_OVERRIDE = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)  # noqa: E731
app.dependency_overrides[_require_org] = _AUTH_OVERRIDE


@pytest.fixture(autouse=True)
def _apply_module_auth_override():
    """Re-apply this module's auth override before each test (see test_budget_routes)."""
    app.dependency_overrides[_require_org] = _AUTH_OVERRIDE
    yield


client = TestClient(app)


def _mock_db(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    for method in ("select", "eq", "order", "limit", "insert", "update"):
        getattr(db, method).return_value = db
    db.execute.return_value = result
    return db


def _report_row(report_id: str = REPORT_ID, r2_object_key: str | None = "reports/x.pdf") -> dict:
    return {
        "id": report_id,
        "org_id": ORG_ID,
        "type": "cfo_pdf",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "r2_object_key": r2_object_key,
        "generated_at": "2026-06-01T06:00:00+00:00",
    }


class TestListReports:
    def test_empty_list(self) -> None:
        with patch("api.routers.reports._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_reports_with_has_file_flag(self) -> None:
        rows = [_report_row(), _report_row("r2", r2_object_key=None)]
        with patch("api.routers.reports._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/reports")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["has_file"] is True
        assert body[1]["has_file"] is False
        # The R2 object key itself must never be exposed.
        assert "r2_object_key" not in body[0]


class TestDownloadReport:
    def test_returns_presigned_url(self) -> None:
        with (
            patch("api.routers.reports._get_supabase", return_value=_mock_db([_report_row()])),
            patch(
                "api.routers.reports.presign_download",
                return_value="https://signed.example/x.pdf",
            ) as mock_presign,
        ):
            resp = client.get(f"/api/v1/reports/{REPORT_ID}/download")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://signed.example/x.pdf"
        assert resp.json()["expires_in_seconds"] == 600
        mock_presign.assert_called_once_with("reports/x.pdf", 600)

    def test_404_when_not_found_or_wrong_org(self) -> None:
        with patch("api.routers.reports._get_supabase", return_value=_mock_db([])):
            resp = client.get(f"/api/v1/reports/{REPORT_ID}/download")
        assert resp.status_code == 404

    def test_404_when_file_missing(self) -> None:
        rows = [_report_row(r2_object_key=None)]
        with patch("api.routers.reports._get_supabase", return_value=_mock_db(rows)):
            resp = client.get(f"/api/v1/reports/{REPORT_ID}/download")
        assert resp.status_code == 404
        assert "not available" in resp.json()["detail"]


class TestGenerateReport:
    def test_queues_month_to_date_generation(self) -> None:
        # Patch the module attribute (not task.delay): the route imports the
        # task locally at call time, and Celery's shared_task Proxy does not
        # reliably hold an instance-level patched .delay across app contexts.
        with (
            patch("api.routers.reports._generate_rate_limited", return_value=False),
            patch("api.workers.reports.generate_org_report") as mock_task,
        ):
            resp = client.post("/api/v1/reports/generate")
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        args, kwargs = mock_task.delay.call_args
        assert args[0] == ORG_ID
        assert kwargs["force"] is True
        assert kwargs["send_email"] is False

    def test_rate_limited_returns_429(self) -> None:
        with patch("api.routers.reports._generate_rate_limited", return_value=True):
            resp = client.post("/api/v1/reports/generate")
        assert resp.status_code == 429

    def test_rate_limit_fails_open_on_redis_error(self) -> None:
        from api.routers.reports import _generate_rate_limited

        with patch(
            "api.routers.reports.redis_lib.Redis.from_url",
            side_effect=ConnectionError("redis down"),
        ):
            assert _generate_rate_limited(ORG_ID) is False

    def test_rate_limit_blocks_fourth_call(self) -> None:
        from api.routers.reports import _generate_rate_limited

        redis_mock = MagicMock()
        pipe = MagicMock()
        redis_mock.pipeline.return_value = pipe
        pipe.execute.return_value = [4, True]  # INCR returned 4 -> over the limit of 3
        with patch(
            "api.routers.reports.redis_lib.Redis.from_url", return_value=redis_mock
        ):
            assert _generate_rate_limited(ORG_ID) is True
