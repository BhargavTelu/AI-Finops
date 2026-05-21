"""
Additional budget route tests not covered by test_budget_routes.py.
TC-BUD-11 and TC-BUD-12.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
BUDGET_ID = "bbbbbbbb-0000-0000-0000-000000000099"

from datetime import datetime, timezone

NOW_ISO = datetime.now(timezone.utc).isoformat()

app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)

client = TestClient(app)


def _budget_row(
    monthly_limit: str = "1000.00",
    scope_type: str = "global",
    scope_value: str | None = None,
) -> dict:
    return {
        "id": BUDGET_ID,
        "org_id": ORG_ID,
        "scope_type": scope_type,
        "scope_value": scope_value,
        "monthly_limit": monthly_limit,
        "alert_at_pct": 80,
        "hard_cap": False,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }


class TestBudgetSpentPctEdgeCases:
    def test_zero_limit_budget_shows_zero_pct(self) -> None:  # TC-BUD-11
        """When monthly_limit=0 there must be no ZeroDivisionError; spent_pct=0."""
        db = MagicMock()
        result_budget = MagicMock()
        result_budget.data = [_budget_row(monthly_limit="0")]
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.gte.return_value = db
        db.lte.return_value = db
        db.order.return_value = db
        db.limit.return_value = db
        # First execute = budget list, subsequent = MTD spend (returns empty)
        db.execute.side_effect = [
            result_budget,
            MagicMock(data=[{"total_cost_usd": "500.00"}]),  # MTD spend rows
        ]

        with patch("api.routers.budgets._get_supabase", return_value=db):
            resp = client.get("/api/v1/budgets")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["spent_pct"] == 0  # zero limit → always 0%

    def test_over_100pct_spend_reported_as_150(self) -> None:  # TC-BUD-12
        """Spend $1500 vs $1000 limit should report spent_pct=150 (not capped at 100)."""
        db = MagicMock()
        result_budget = MagicMock()
        result_budget.data = [_budget_row(monthly_limit="1000.00")]
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.gte.return_value = db
        db.lte.return_value = db
        db.order.return_value = db
        db.limit.return_value = db
        db.execute.side_effect = [
            result_budget,
            MagicMock(data=[{"total_cost_usd": "1500.00"}]),
        ]

        with patch("api.routers.budgets._get_supabase", return_value=db):
            resp = client.get("/api/v1/budgets")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["spent_pct"] == 150
