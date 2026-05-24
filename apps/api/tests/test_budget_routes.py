"""
Unit tests for GET/POST/PATCH/DELETE /budgets.
Supabase calls are mocked. Auth dependency is overridden.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000002"
BUDGET_ID = "bbbbbbbb-0000-0000-0000-000000000001"

# Override auth for all tests
app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)

client = TestClient(app)

NOW_ISO = datetime.now(timezone.utc).isoformat()


# ── DB mock helper ─────────────────────────────────────────────────────────────

def _mock_db(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.lte.return_value = db
    db.is_.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


def _budget_row(
    budget_id: str = BUDGET_ID,
    scope_type: str = "global",
    scope_value: str | None = None,
    monthly_limit: str = "1000.00",
    alert_at_pct: int = 80,
) -> dict:
    return {
        "id": budget_id,
        "org_id": ORG_ID,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "monthly_limit": monthly_limit,
        "alert_at_pct": alert_at_pct,
        "hard_cap": False,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }


# ── GET /budgets ───────────────────────────────────────────────────────────────

class TestListBudgets:
    def test_empty_list(self) -> None:
        db = _mock_db([])
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("0")),
        ):
            resp = client.get("/api/v1/budgets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_budget_with_computed_spend(self) -> None:
        db = _mock_db([_budget_row()])
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("750")),
        ):
            resp = client.get("/api/v1/budgets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == BUDGET_ID
        assert data[0]["spent_pct"] == 75
        assert float(data[0]["current_spend_mtd"]) == pytest.approx(750.0)

    def test_100pct_spend_reported_correctly(self) -> None:
        db = _mock_db([_budget_row()])
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("1000")),
        ):
            resp = client.get("/api/v1/budgets")
        assert resp.status_code == 200
        assert resp.json()[0]["spent_pct"] == 100


# ── POST /budgets ──────────────────────────────────────────────────────────────

class TestCreateBudget:
    def _post(self, payload: dict, db: MagicMock) -> tuple:
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("0")),
        ):
            return client.post("/api/v1/budgets", json=payload)

    def test_create_global_budget(self) -> None:
        db = _mock_db()
        # First call (dupe check) returns empty; second call (insert) returns the row
        db.execute.side_effect = [
            MagicMock(data=[]),          # dupe check → none found
            MagicMock(data=[_budget_row()]),  # insert result
        ]
        resp = self._post(
            {"scope_type": "global", "monthly_limit": 1000, "alert_at_pct": 80},
            db,
        )
        assert resp.status_code == 201
        assert resp.json()["scope_type"] == "global"

    def test_create_model_budget_requires_scope_value(self) -> None:
        db = _mock_db()
        resp = self._post(
            {"scope_type": "model", "monthly_limit": 500},
            db,
        )
        assert resp.status_code == 422

    def test_create_model_budget_with_scope_value(self) -> None:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[]),  # dupe check
            MagicMock(data=[_budget_row(scope_type="model", scope_value="gpt-4o")]),  # insert
        ]
        resp = self._post(
            {"scope_type": "model", "scope_value": "gpt-4o", "monthly_limit": 500},
            db,
        )
        assert resp.status_code == 201
        assert resp.json()["scope_value"] == "gpt-4o"

    def test_duplicate_budget_returns_409(self) -> None:
        db = _mock_db()
        # Dupe check finds an existing row
        db.execute.return_value = MagicMock(data=[_budget_row()])
        resp = self._post(
            {"scope_type": "global", "monthly_limit": 999},
            db,
        )
        assert resp.status_code == 409

    def test_negative_limit_rejected(self) -> None:
        db = _mock_db()
        resp = self._post(
            {"scope_type": "global", "monthly_limit": -100},
            db,
        )
        assert resp.status_code == 422

    def test_zero_limit_rejected(self) -> None:
        db = _mock_db()
        resp = self._post(
            {"scope_type": "global", "monthly_limit": 0},
            db,
        )
        assert resp.status_code == 422

    def test_alert_at_pct_defaults_to_80(self) -> None:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[]),
            MagicMock(data=[_budget_row()]),
        ]
        resp = self._post({"scope_type": "global", "monthly_limit": 1000}, db)
        # If no alert_at_pct provided, the budget row has 80
        assert resp.status_code == 201
        assert resp.json()["alert_at_pct"] == 80

    def test_all_scope_types_accepted(self) -> None:
        scope_types = [
            "provider", "model", "feature_tag", "team_tag", "customer_tag", "env_tag"
        ]
        for st in scope_types:
            db = _mock_db()
            db.execute.side_effect = [
                MagicMock(data=[]),
                MagicMock(data=[_budget_row(scope_type=st, scope_value="test")]),
            ]
            resp = self._post(
                {"scope_type": st, "scope_value": "test", "monthly_limit": 100},
                db,
            )
            assert resp.status_code == 201, f"Failed for scope_type={st}: {resp.json()}"


# ── PATCH /budgets/:id ──────────────────────────────────────────────────────────

class TestUpdateBudget:
    def test_update_monthly_limit(self) -> None:
        updated = _budget_row(monthly_limit="2000.00")
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[{"id": BUDGET_ID}]),  # ownership check
            MagicMock(data=[updated]),             # update result
        ]
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("0")),
        ):
            resp = client.patch(f"/api/v1/budgets/{BUDGET_ID}", json={"monthly_limit": 2000})
        assert resp.status_code == 200
        assert float(resp.json()["monthly_limit"]) == pytest.approx(2000.0)

    def test_update_wrong_org_returns_404(self) -> None:
        db = _mock_db([])  # ownership check returns nothing
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("0")),
        ):
            resp = client.patch(f"/api/v1/budgets/{BUDGET_ID}", json={"monthly_limit": 999})
        assert resp.status_code == 404

    def test_empty_patch_body_returns_422(self) -> None:
        db = _mock_db()
        db.execute.return_value = MagicMock(data=[{"id": BUDGET_ID}])
        with (
            patch("api.routers.budgets._get_supabase", return_value=db),
            patch("api.routers.budgets._compute_mtd_spend", return_value=Decimal("0")),
        ):
            resp = client.patch(f"/api/v1/budgets/{BUDGET_ID}", json={})
        assert resp.status_code == 422


# ── DELETE /budgets/:id ──────────────────────────────────────────────────────────

class TestDeleteBudget:
    def test_delete_own_budget_returns_204(self) -> None:
        db = _mock_db()
        db.execute.side_effect = [
            MagicMock(data=[{"id": BUDGET_ID}]),  # ownership check
            MagicMock(data=[]),                   # delete
        ]
        with patch("api.routers.budgets._get_supabase", return_value=db):
            resp = client.delete(f"/api/v1/budgets/{BUDGET_ID}")
        assert resp.status_code == 204

    def test_delete_wrong_org_returns_404(self) -> None:
        db = _mock_db([])  # ownership check returns nothing
        with patch("api.routers.budgets._get_supabase", return_value=db):
            resp = client.delete(f"/api/v1/budgets/{BUDGET_ID}")
        assert resp.status_code == 404


# ── TC-BUD-20: PATCH /budgets/:id with hard_cap only ─────────────────────────

class TestBudgetPatchHardCapNotPatchable:
    """TC-BUD-20 — PATCH with only hard_cap (not in patchable set) → 422."""

    def test_patch_with_hard_cap_only_returns_422(self) -> None:
        """
        BudgetUpdate schema only allows monthly_limit and alert_at_pct.
        Sending only hard_cap (which is not patchable) must trigger the
        empty-patch guard and return 422 'No fields to update'.
        """
        # DB mock must return an existing budget for the ownership check
        existing = _budget_row()
        db = _mock_db([existing])
        with patch("api.routers.budgets._get_supabase", return_value=db):
            resp = client.patch(
                f"/api/v1/budgets/{BUDGET_ID}",
                json={"hard_cap": True},
            )
        # hard_cap is not in BudgetUpdate → Pydantic 422 (extra field ignored)
        # or the empty-patch guard fires → 422 "No fields to update"
        assert resp.status_code == 422, (
            f"Expected 422 when only non-patchable field hard_cap is sent, "
            f"got {resp.status_code}. "
            "BudgetUpdate only allows monthly_limit and alert_at_pct."
        )


# ── TC-BUD-21: _compute_mtd_spend with env_tag scope ─────────────────────────

class TestComputeMtdSpendEnvTagScope:
    """TC-BUD-21 — _compute_mtd_spend filters by env_tag when scope_type='env_tag'."""

    def test_env_tag_scope_filters_by_env_tag(self) -> None:
        from api.routers.budgets import _compute_mtd_spend

        db = _mock_db([{"total_cost_usd": "150.00"}, {"total_cost_usd": "50.00"}])
        eq_calls: list = []

        original_eq = db.eq.side_effect

        def track_eq(col, val):
            eq_calls.append((col, val))
            return db

        db.eq.side_effect = track_eq

        result = _compute_mtd_spend(db, "org-111", "env_tag", "production")

        assert ("env_tag", "production") in eq_calls, (
            f"Expected .eq('env_tag', 'production') filter, got eq calls: {eq_calls}"
        )
        from decimal import Decimal
        assert result == Decimal("200.00"), f"Expected 200.00, got {result}"


# ── TC-BUD-22: _to_budget_read with zero monthly_limit ───────────────────────

class TestToBudgetReadZeroMonthlyLimit:
    """TC-BUD-22 — _to_budget_read with monthly_limit=0.00 must not raise ZeroDivisionError."""

    def test_zero_monthly_limit_returns_zero_spent_pct(self) -> None:
        from decimal import Decimal
        from api.routers.budgets import _to_budget_read

        row = _budget_row(monthly_limit="0.00")
        row["hard_cap"] = False
        row["created_at"] = NOW_ISO
        row["updated_at"] = NOW_ISO

        result = _to_budget_read(row, mtd_spend=Decimal("0"))

        assert result.spent_pct == 0, (
            f"Expected spent_pct=0 for zero monthly_limit (div-by-zero guard), "
            f"got {result.spent_pct}"
        )
