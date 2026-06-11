"""
Unit tests for the Phase 2 access rule (services/billing_access.py) and the
gating dependency (deps._require_active_org). Supabase mocked - the rule is
pure, the dependency is exercised directly, not over HTTP (route tests bypass
the gate via conftest).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import pytest

from api.deps import OrgContext, _require_active_org
from api.services.billing_access import evaluate_access

NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
FUTURE = (NOW + timedelta(days=10)).isoformat()
PAST = (NOW - timedelta(days=3)).isoformat()


class TestEvaluateAccess:
    def test_trial_active_no_subscription_allows(self) -> None:
        state = evaluate_access({"trial_ends_at": FUTURE}, None, now=NOW)
        assert state.access_blocked is False
        assert state.status == "trialing"
        assert state.plan == "trial"
        assert state.trial_days_left == 10
        assert state.has_subscription is False

    def test_trial_expired_no_subscription_blocks(self) -> None:
        state = evaluate_access({"trial_ends_at": PAST}, None, now=NOW)
        assert state.access_blocked is True
        assert state.status == "expired"
        assert state.trial_days_left is None

    def test_active_subscription_allows(self) -> None:
        state = evaluate_access(
            {"trial_ends_at": PAST},
            {"status": "active", "stripe_subscription_id": "sub_1", "plan": "growth"},
            now=NOW,
        )
        assert state.access_blocked is False
        assert state.plan == "growth"
        assert state.has_subscription is True

    def test_stripe_trialing_subscription_allows(self) -> None:
        state = evaluate_access(
            {"trial_ends_at": PAST},
            {"status": "trialing", "stripe_subscription_id": "sub_1", "plan": "starter"},
            now=NOW,
        )
        assert state.access_blocked is False

    def test_canceled_subscription_with_expired_trial_blocks(self) -> None:
        state = evaluate_access(
            {"trial_ends_at": PAST},
            {"status": "canceled", "stripe_subscription_id": "sub_1", "plan": "growth"},
            now=NOW,
        )
        assert state.access_blocked is True
        assert state.status == "canceled"

    def test_past_due_subscription_blocks(self) -> None:
        # Deliberate: the paywall is the nudge that fixes the card.
        state = evaluate_access(
            {"trial_ends_at": PAST},
            {"status": "past_due", "stripe_subscription_id": "sub_1", "plan": "growth"},
            now=NOW,
        )
        assert state.access_blocked is True

    def test_canceled_subscription_inside_trial_window_allows(self) -> None:
        # Subscribed early, canceled, but the built-in trial hasn't lapsed.
        state = evaluate_access(
            {"trial_ends_at": FUTURE},
            {"status": "canceled", "stripe_subscription_id": "sub_1", "plan": "starter"},
            now=NOW,
        )
        assert state.access_blocked is False
        assert state.status == "trialing"

    def test_missing_org_row_blocks(self) -> None:
        state = evaluate_access(None, None, now=NOW)
        assert state.access_blocked is True

    def test_null_trial_ends_at_blocks(self) -> None:
        # Orgs created before the trial bootstrap existed have NULL - treat
        # as expired rather than infinite free access.
        state = evaluate_access({"trial_ends_at": None}, None, now=NOW)
        assert state.access_blocked is True

    def test_malformed_trial_timestamp_blocks(self) -> None:
        state = evaluate_access({"trial_ends_at": "not-a-date"}, None, now=NOW)
        assert state.access_blocked is True

    def test_z_suffix_timestamp_parses(self) -> None:
        z_future = (NOW + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = evaluate_access({"trial_ends_at": z_future}, None, now=NOW)
        assert state.access_blocked is False


def _dep_db(org_rows: list[dict], billing_rows: list[dict]) -> MagicMock:
    db = MagicMock()

    def table(name: str) -> MagicMock:
        chain = MagicMock()
        for method in ("select", "eq", "limit"):
            getattr(chain, method).return_value = chain
        result = MagicMock()
        result.data = org_rows if name == "organizations" else billing_rows
        chain.execute.return_value = result
        return chain

    db.table.side_effect = table
    return db


ORG = OrgContext(user_id="user_x", org_id="00000000-0000-0000-0000-000000000001")


class TestRequireActiveOrgDependency:
    def test_allows_trialing_org(self) -> None:
        db = _dep_db([{"trial_ends_at": FUTURE, "plan": "trial"}], [])
        with patch("api.deps.create_client", return_value=db):
            assert _require_active_org(ORG) is ORG

    def test_blocks_expired_org_with_402(self) -> None:
        db = _dep_db([{"trial_ends_at": PAST, "plan": "trial"}], [])
        with patch("api.deps.create_client", return_value=db):
            with pytest.raises(HTTPException) as exc_info:
                _require_active_org(ORG)
        assert exc_info.value.status_code == 402

    def test_allows_subscribed_org(self) -> None:
        db = _dep_db(
            [{"trial_ends_at": PAST, "plan": "growth"}],
            [{"status": "active", "stripe_subscription_id": "sub_1", "plan": "growth"}],
        )
        with patch("api.deps.create_client", return_value=db):
            assert _require_active_org(ORG) is ORG
