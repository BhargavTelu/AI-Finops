"""
Integration route tests for POST/GET/DELETE /integrations.
TC-INT-01 to TC-INT-10.
Supabase and adapters are mocked. Auth dependency is overridden.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
INT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
NOW_ISO = datetime.now(timezone.utc).isoformat()

app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)

client = TestClient(app)


# ── Mock helpers ───────────────────────────────────────────────────────────────

def _mock_db(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.upsert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


def _integration_row(
    integration_id: str = INT_ID,
    status: str = "active",
) -> dict:
    return {
        "id": integration_id,
        "org_id": ORG_ID,
        "provider": "openai",
        "display_name": "My OpenAI",
        "status": status,
        "last_synced_at": None,
        "last_error": None,
        "created_at": NOW_ISO,
    }


VALID_BODY = {
    "provider": "openai",
    "display_name": "My OpenAI",
    "api_key": "sk-admin-test-key-1234567890",
}

MOCK_ADAPTER = MagicMock()
MOCK_ADAPTER.validate.return_value = True


# ── POST /integrations ─────────────────────────────────────────────────────────

class TestCreateIntegration:
    def test_happy_path_returns_201(self) -> None:  # TC-INT-01
        db = _mock_db([_integration_row()])
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations._ADAPTERS", {"openai": MOCK_ADAPTER}),
            patch("api.routers.integrations.backfill_integration") as mock_bf,
        ):
            mock_bf.delay = MagicMock()
            resp = client.post("/api/v1/integrations", json=VALID_BODY)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["status"] == "active"

    def test_api_key_never_returned(self) -> None:  # TC-INT-02
        db = _mock_db([_integration_row()])
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations._ADAPTERS", {"openai": MOCK_ADAPTER}),
            patch("api.routers.integrations.backfill_integration") as mock_bf,
        ):
            mock_bf.delay = MagicMock()
            resp = client.post("/api/v1/integrations", json=VALID_BODY)
        assert resp.status_code == 201
        data = resp.json()
        assert "api_key" not in data
        assert "api_key_enc" not in data

    def test_backfill_task_enqueued(self) -> None:  # TC-INT-03
        db = _mock_db([_integration_row()])
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations._ADAPTERS", {"openai": MOCK_ADAPTER}),
            patch("api.routers.integrations.backfill_integration") as mock_bf,
        ):
            mock_bf.delay = MagicMock()
            resp = client.post("/api/v1/integrations", json=VALID_BODY)
        assert resp.status_code == 201
        mock_bf.delay.assert_called_once()
        call_args = mock_bf.delay.call_args[0]
        assert call_args[1] == ORG_ID  # org_id passed correctly

    def test_invalid_provider_returns_422(self) -> None:  # TC-INT-04
        resp = client.post(
            "/api/v1/integrations",
            json={
                "provider": "cohere",
                "display_name": "My Cohere",
                "api_key": "sk-test-key-1234567890",
            },
        )
        assert resp.status_code == 422

    def test_invalid_key_returns_422(self) -> None:  # TC-INT-05
        bad_adapter = MagicMock()
        bad_adapter.validate.side_effect = ValueError("Invalid or unauthorized key")
        with patch("api.routers.integrations._ADAPTERS", {"openai": bad_adapter}):
            resp = client.post("/api/v1/integrations", json=VALID_BODY)
        assert resp.status_code == 422
        assert "Invalid" in resp.json()["detail"]

    def test_duplicate_name_returns_409(self) -> None:  # TC-INT-09
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.insert.return_value = db
        db.eq.return_value = db
        db.execute.side_effect = Exception(
            "duplicate key value violates unique constraint"
        )
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations._ADAPTERS", {"openai": MOCK_ADAPTER}),
        ):
            resp = client.post("/api/v1/integrations", json=VALID_BODY)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    def test_audit_event_written(self) -> None:  # TC-INT-10
        db = _mock_db([_integration_row()])
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations._ADAPTERS", {"openai": MOCK_ADAPTER}),
            patch("api.routers.integrations.backfill_integration") as mock_bf,
        ):
            mock_bf.delay = MagicMock()
            resp = client.post("/api/v1/integrations", json=VALID_BODY)
        assert resp.status_code == 201
        table_calls = [str(c) for c in db.table.call_args_list]
        assert any("audit_events" in s for s in table_calls)


# ── GET /integrations ──────────────────────────────────────────────────────────

class TestListIntegrations:
    def test_returns_non_revoked_only(self) -> None:  # TC-INT-06
        rows = [_integration_row("aaaaaaaa-0001", "active"), _integration_row("aaaaaaaa-0002", "active")]
        db = _mock_db(rows)
        with patch("api.routers.integrations._get_supabase", return_value=db):
            resp = client.get("/api/v1/integrations")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── DELETE /integrations/{id} ─────────────────────────────────────────────────

class TestDeleteIntegration:
    def test_soft_revoke_returns_204(self) -> None:  # TC-INT-07
        db = _mock_db([_integration_row()])
        with (
            patch("api.routers.integrations._get_supabase", return_value=db),
            patch("api.routers.integrations.aggregate_org") as mock_agg,
        ):
            mock_agg.delay = MagicMock()
            resp = client.delete(f"/api/v1/integrations/{INT_ID}")
        assert resp.status_code == 204

    def test_other_org_integration_returns_404(self) -> None:  # TC-INT-08
        db = _mock_db([])  # update returns no rows → 404
        with patch("api.routers.integrations._get_supabase", return_value=db):
            resp = client.delete(f"/api/v1/integrations/{INT_ID}")
        assert resp.status_code == 404
