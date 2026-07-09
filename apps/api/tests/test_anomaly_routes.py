"""
Route tests for GET/PATCH /anomalies.
TC-ANOM-01 to TC-ANOM-07.
Supabase is mocked. Auth dependency is overridden.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000002"
ANOMALY_ID = "cccccccc-0000-0000-0000-000000000001"
NOW_ISO = datetime.now(UTC).isoformat()

_AUTH_OVERRIDE = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)  # noqa: E731
app.dependency_overrides[_require_org] = _AUTH_OVERRIDE


@pytest.fixture(autouse=True)
def _apply_module_auth_override():
    """Re-apply this module's auth override before each test.

    Import-time assignment alone is unreliable: every test module is imported
    at collection, so whichever module imports LAST owns the override for the
    whole run unless each module re-applies its own before its tests.
    """
    app.dependency_overrides[_require_org] = _AUTH_OVERRIDE
    yield


client = TestClient(app)


# ── Mock helpers ───────────────────────────────────────────────────────────────


def _mock_db(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    db.select.return_value = db
    db.update.return_value = db
    db.eq.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


def _anomaly_row(
    anomaly_id: str = ANOMALY_ID,
    status: str = "open",
    severity: str = "high",
    explanation: str | None = None,
) -> dict:
    return {
        "id": anomaly_id,
        "org_id": ORG_ID,
        "detected_at": NOW_ISO,
        "scope_kind": "model",
        "scope_value": "gpt-4o",
        "baseline_usd": "10.00",
        "actual_usd": "50.00",
        "spike_pct": 400,
        "severity": severity,
        "status": status,
        "context": None,
        "explanation": explanation,
    }


# ── GET /anomalies ─────────────────────────────────────────────────────────────


class TestListAnomalies:
    def test_list_all_returns_three(self) -> None:  # TC-ANOM-01
        rows = [
            _anomaly_row("cccc-0001"),
            _anomaly_row("cccc-0002"),
            _anomaly_row("cccc-0003"),
        ]
        db = _mock_db(rows)
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_list_filtered_by_status_open(self) -> None:  # TC-ANOM-02
        rows = [_anomaly_row("cccc-0001", "open"), _anomaly_row("cccc-0002", "open")]
        db = _mock_db(rows)
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.get("/api/v1/anomalies?status=open")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(a["status"] == "open" for a in data)

    def test_list_includes_explanation_when_populated(self) -> None:  # TC-M3-D04
        text = "Traffic spike from new chat feature rollout."
        rows = [_anomaly_row(explanation=text)]
        db = _mock_db(rows)
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data[0]
        assert data[0]["explanation"] == text

    def test_list_includes_explanation_null_when_absent(self) -> None:  # TC-M3-D05
        rows = [_anomaly_row()]  # explanation defaults to None
        db = _mock_db(rows)
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.get("/api/v1/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data[0]
        assert data[0]["explanation"] is None


# ── PATCH /anomalies/{id} ──────────────────────────────────────────────────────


class TestUpdateAnomaly:
    def _db_for_update(self, new_status: str) -> MagicMock:
        """Ownership check returns row; update returns row with new status."""
        updated_row = _anomaly_row(ANOMALY_ID, new_status)
        db = MagicMock()
        # Both select (ownership) and update calls return non-empty data
        result = MagicMock()
        result.data = [updated_row]
        db.table.return_value = db
        db.select.return_value = db
        db.update.return_value = db
        db.eq.return_value = db
        db.limit.return_value = db
        db.execute.return_value = result
        return db

    def test_patch_status_to_acked(self) -> None:  # TC-ANOM-03
        db = self._db_for_update("acked")
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.patch(f"/api/v1/anomalies/{ANOMALY_ID}", json={"status": "acked"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "acked"

    def test_patch_status_to_dismissed(self) -> None:  # TC-ANOM-04
        db = self._db_for_update("dismissed")
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.patch(f"/api/v1/anomalies/{ANOMALY_ID}", json={"status": "dismissed"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_org_isolation_returns_404(self) -> None:  # TC-ANOM-05
        db = _mock_db([])  # ownership check returns empty → 404
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.patch(f"/api/v1/anomalies/{ANOMALY_ID}", json={"status": "acked"})
        assert resp.status_code == 404

    def test_invalid_status_returns_422(self) -> None:  # TC-ANOM-06
        resp = client.patch(f"/api/v1/anomalies/{ANOMALY_ID}", json={"status": "deleted"})
        assert resp.status_code == 422

    def test_nonexistent_anomaly_returns_404(self) -> None:  # TC-ANOM-07
        db = _mock_db([])
        with patch("api.routers.anomalies._get_supabase", return_value=db):
            resp = client.patch("/api/v1/anomalies/nonexistent-id", json={"status": "acked"})
        assert resp.status_code == 404
