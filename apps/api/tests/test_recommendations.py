"""
Unit tests for the recommendations engine.
Covers:
  - _check_model_swap: triggers, savings math, confidence thresholds
  - _check_caching_opportunity: triggers, savings math, scope_value key
  - _check_batch_opportunity: triggers, avg_tokens threshold, savings math
  - generate_recommendations: sorted by savings, empty input no-ops
  - dedup logic in generate_org_recommendations worker
All Supabase calls are mocked - no network, no DB.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from api.services.recommendations import (
    ModelStats,
    Recommendation,
    _check_batch_opportunity,
    _check_caching_opportunity,
    _check_model_swap,
    generate_recommendations,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _stats(
    model: str,
    provider: str = "openai",
    feature_tag: str | None = None,
    total_cost_usd: str = "100.00",
    total_requests: int = 500,
    total_tokens: int = 500_000,
) -> ModelStats:
    return ModelStats(
        provider=provider,
        model=model,
        feature_tag=feature_tag,
        total_cost_usd=Decimal(total_cost_usd),
        total_requests=total_requests,
        total_tokens=total_tokens,
    )


# ── model_swap ────────────────────────────────────────────────────────────────

class TestCheckModelSwap:
    def test_triggers_on_expensive_model_with_alternative(self):
        recs = _check_model_swap([_stats("gpt-4o", total_requests=200, total_cost_usd="50.00")])
        assert len(recs) == 1
        rec = recs[0]
        assert rec.type == "model_swap"
        assert "gpt-4o-mini" in rec.title
        assert rec.scope_value == "gpt-4o"

    def test_savings_math_uses_price_ratio(self):
        # gpt-4o input: $2.50/MTok, gpt-4o-mini: $0.15/MTok → ratio = 0.06
        # savings ≈ 100 * (1 - 0.06) = $94
        recs = _check_model_swap([_stats("gpt-4o", total_cost_usd="100.00", total_requests=500)])
        assert len(recs) == 1
        savings = recs[0].projected_savings_usd
        assert savings is not None
        # ratio = 0.15 / 2.50 = 0.06; savings = 100 * 0.94 = 94.00
        assert savings == Decimal("94.00")

    def test_high_confidence_above_500_requests(self):
        recs = _check_model_swap([_stats("gpt-4o", total_requests=501, total_cost_usd="50.00")])
        assert recs[0].confidence == Decimal("0.85")

    def test_medium_confidence_at_100_to_500_requests(self):
        recs = _check_model_swap([_stats("gpt-4o", total_requests=100, total_cost_usd="50.00")])
        assert recs[0].confidence == Decimal("0.60")

    def test_skipped_below_100_requests(self):
        recs = _check_model_swap([_stats("gpt-4o", total_requests=99, total_cost_usd="50.00")])
        assert recs == []

    def test_skipped_when_avg_cost_per_req_at_or_below_threshold(self):
        # avg_cost = 10.00 / 1000 = $0.01 → exactly at threshold → skip
        recs = _check_model_swap([_stats("gpt-4o", total_cost_usd="10.00", total_requests=1000)])
        assert recs == []

    def test_skipped_when_no_cheaper_alternative(self):
        # gpt-4o-mini has no cheaper_model in _MODEL_DOWNGRADE
        recs = _check_model_swap([_stats("gpt-4o-mini", total_cost_usd="50.00", total_requests=500)])
        assert recs == []

    def test_skipped_when_projected_savings_below_minimum(self):
        # Very low cost → savings < $1 threshold
        recs = _check_model_swap([_stats("gpt-4o", total_cost_usd="1.00", total_requests=200)])
        assert recs == []

    def test_aggregates_across_feature_tags(self):
        # Two rows for same model, different tags - should produce one rec with combined cost
        stats = [
            _stats("gpt-4o", feature_tag="chat", total_cost_usd="60.00", total_requests=300),
            _stats("gpt-4o", feature_tag="search", total_cost_usd="40.00", total_requests=200),
        ]
        recs = _check_model_swap(stats)
        assert len(recs) == 1
        assert recs[0].evidence["total_requests"] == 500
        # Combined cost = 100.00, savings ≈ 94.00
        assert recs[0].projected_savings_usd == Decimal("94.00")

    def test_anthropic_model_swap(self):
        recs = _check_model_swap([
            _stats("claude-opus-4-5", provider="anthropic", total_cost_usd="200.00", total_requests=300)
        ])
        assert len(recs) == 1
        assert "claude-sonnet-4-5" in recs[0].title

    def test_evidence_contains_required_keys(self):
        recs = _check_model_swap([_stats("gpt-4o", total_cost_usd="100.00", total_requests=500)])
        ev = recs[0].evidence
        assert "model" in ev
        assert "cheaper_model" in ev
        assert "total_requests" in ev
        assert "price_ratio" in ev


# ── caching ───────────────────────────────────────────────────────────────────

class TestCheckCachingOpportunity:
    def test_triggers_on_cache_eligible_model_with_enough_requests(self):
        # gpt-4o, 500 requests; need enough tokens so savings > $1 min threshold.
        # 5M tokens: est_input=3_500_000, cacheable=1_050_000,
        # savings = 1_050_000 * 1.25 / 1_000_000 = 1.3125 → $1.31
        recs = _check_caching_opportunity([
            _stats("gpt-4o", total_requests=500, total_tokens=5_000_000, total_cost_usd="50.00")
        ])
        assert len(recs) == 1
        assert recs[0].type == "caching"

    def test_savings_math(self):
        # 10M tokens: est_input = 7_000_000, cacheable = 2_100_000
        # savings = 2_100_000 * 1.25 / 1_000_000 = 2.625
        # ROUND_HALF_EVEN: 2.625 → 2.62 (2 is even)
        recs = _check_caching_opportunity([
            _stats("gpt-4o", total_requests=500, total_tokens=10_000_000, total_cost_usd="100.00")
        ])
        assert len(recs) == 1
        savings = recs[0].projected_savings_usd
        assert savings is not None
        assert savings == Decimal("2.62")

    def test_skipped_below_200_requests(self):
        recs = _check_caching_opportunity([
            _stats("gpt-4o", total_requests=199, total_tokens=5_000_000)
        ])
        assert recs == []

    def test_skipped_for_non_cache_eligible_model(self):
        # gpt-4-turbo is not in _CACHE_SAVINGS_PER_MTOK
        recs = _check_caching_opportunity([
            _stats("gpt-4-turbo", total_requests=500, total_tokens=5_000_000)
        ])
        assert recs == []

    def test_scope_value_includes_feature_tag(self):
        recs = _check_caching_opportunity([
            _stats("gpt-4o", feature_tag="chat", total_requests=500, total_tokens=10_000_000)
        ])
        assert recs[0].scope_value == "gpt-4o:chat"

    def test_scope_value_uses_all_when_no_tag(self):
        recs = _check_caching_opportunity([
            _stats("gpt-4o", feature_tag=None, total_requests=500, total_tokens=10_000_000)
        ])
        assert recs[0].scope_value == "gpt-4o:all"

    def test_confidence_is_always_medium(self):
        recs = _check_caching_opportunity([
            _stats("gpt-4o", total_requests=1000, total_tokens=10_000_000)
        ])
        assert recs[0].confidence == Decimal("0.60")

    def test_skipped_when_projected_savings_below_minimum(self):
        # Very few tokens → savings < $1
        recs = _check_caching_opportunity([
            _stats("gpt-4o", total_requests=200, total_tokens=10_000)
        ])
        assert recs == []

    def test_anthropic_claude_caching(self):
        recs = _check_caching_opportunity([
            _stats(
                "claude-3-5-sonnet-20241022",
                provider="anthropic",
                total_requests=300,
                total_tokens=5_000_000,
                total_cost_usd="50.00",
            )
        ])
        assert len(recs) == 1


# ── batch ─────────────────────────────────────────────────────────────────────

class TestCheckBatchOpportunity:
    def test_triggers_on_eligible_model(self):
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=1000, total_tokens=500_000, total_cost_usd="50.00")
        ])
        assert len(recs) == 1
        rec = recs[0]
        assert rec.type == "batch"
        assert rec.scope_value == "gpt-4o"

    def test_savings_is_50_percent_of_cost(self):
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=1000, total_tokens=500_000, total_cost_usd="100.00")
        ])
        assert recs[0].projected_savings_usd == Decimal("50.00")

    def test_confidence_is_high(self):
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=1000, total_tokens=500_000, total_cost_usd="50.00")
        ])
        assert recs[0].confidence == Decimal("0.80")

    def test_skipped_below_500_requests(self):
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=499, total_tokens=500_000, total_cost_usd="50.00")
        ])
        assert recs == []

    def test_skipped_when_avg_tokens_too_high(self):
        # avg = 2_000_000 / 500 = 4000 >= 2000 → skip
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=500, total_tokens=2_000_000, total_cost_usd="50.00")
        ])
        assert recs == []

    def test_skipped_for_non_batch_eligible_model(self):
        # claude is not in _BATCH_ELIGIBLE
        recs = _check_batch_opportunity([
            _stats("claude-3-5-sonnet-20241022", provider="anthropic", total_requests=1000)
        ])
        assert recs == []

    def test_aggregates_across_feature_tags(self):
        stats = [
            _stats("gpt-4o-mini", feature_tag="chat", total_requests=300, total_tokens=150_000, total_cost_usd="30.00"),
            _stats("gpt-4o-mini", feature_tag="search", total_requests=300, total_tokens=150_000, total_cost_usd="30.00"),
        ]
        recs = _check_batch_opportunity(stats)
        assert len(recs) == 1
        assert recs[0].evidence["total_requests"] == 600
        assert recs[0].projected_savings_usd == Decimal("30.00")

    def test_avg_tokens_boundary_at_1999(self):
        # avg = 999_500 / 500 = 1999 < 2000 → triggers
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=500, total_tokens=999_500, total_cost_usd="50.00")
        ])
        assert len(recs) == 1

    def test_skipped_when_projected_savings_below_minimum(self):
        # Very low cost
        recs = _check_batch_opportunity([
            _stats("gpt-4o", total_requests=500, total_tokens=500_000, total_cost_usd="1.50")
        ])
        # 1.50 * 0.50 = 0.75 < $1.00 → skip
        assert recs == []


# ── generate_recommendations (integration) ───────────────────────────────────

class TestGenerateRecommendations:
    def test_empty_stats_returns_empty_list(self):
        assert generate_recommendations([]) == []

    def test_results_sorted_by_savings_descending(self):
        stats = [
            # batch: $50 savings
            _stats("gpt-4o", total_requests=1000, total_tokens=500_000, total_cost_usd="100.00"),
            # model_swap: gpt-4-turbo → gpt-4o savings ≈ $60 (60% of $100 from ratio 10→2.50)
            _stats("gpt-4-turbo", total_requests=500, total_cost_usd="100.00"),
        ]
        recs = generate_recommendations(stats)
        assert len(recs) >= 2
        # Verify descending order
        for i in range(len(recs) - 1):
            a = recs[i].projected_savings_usd or Decimal(0)
            b = recs[i + 1].projected_savings_usd or Decimal(0)
            assert a >= b

    def test_multiple_rules_can_fire_for_same_stats(self):
        # gpt-4o with enough tokens/requests can trigger both model_swap AND batch
        stats = [
            _stats("gpt-4o", total_requests=1000, total_tokens=500_000, total_cost_usd="100.00")
        ]
        recs = generate_recommendations(stats)
        types = {r.type for r in recs}
        assert "model_swap" in types
        assert "batch" in types

    def test_no_recs_when_all_thresholds_not_met(self):
        # Low cost, few requests
        stats = [_stats("gpt-4o", total_requests=50, total_cost_usd="0.50", total_tokens=1000)]
        assert generate_recommendations(stats) == []


# ── worker deduplication ──────────────────────────────────────────────────────

class TestWorkerDedup:
    """Test that generate_org_recommendations skips existing open recommendations."""

    def _mock_db(self, summaries: list[dict], existing_recs: list[dict]) -> MagicMock:
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.insert.return_value = db
        db.eq.return_value = db
        db.gte.return_value = db
        db.order.return_value = db
        db.execute.side_effect = [
            MagicMock(data=summaries),   # first call: summaries query
            MagicMock(data=existing_recs),  # second call: existing open recs
            MagicMock(data=[{"id": "new-id"}]),  # third+ calls: inserts
        ]
        return db

    def test_skips_rec_when_same_type_and_scope_already_open(self):
        from api.workers.recommendations import generate_org_recommendations

        summaries = [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "feature_tag": None,
                "total_cost_usd": "100.00",
                "total_requests": 1000,
                "total_tokens": 500_000,
            }
        ]
        # A model_swap rec for gpt-4o is already open
        existing_recs = [{"type": "model_swap", "scope_value": "gpt-4o"}]

        with patch("api.workers.recommendations._get_supabase") as mock_sup:
            db = MagicMock()
            db.table.return_value = db
            db.select.return_value = db
            db.insert.return_value = db
            db.eq.return_value = db
            db.gte.return_value = db
            db.order.return_value = db

            # Use list side_effect (unittest.mock handles StopIteration correctly)
            db.execute.side_effect = [
                MagicMock(data=summaries),
                MagicMock(data=existing_recs),
                MagicMock(data=[{"id": "new-1"}]),
                MagicMock(data=[{"id": "new-2"}]),
            ]
            mock_sup.return_value = db

            generate_org_recommendations("org-1")

        # insert should NOT have been called for the model_swap rec
        insert_calls = db.insert.call_args_list
        for c in insert_calls:
            row = c[0][0]
            assert not (row["type"] == "model_swap" and row["scope_value"] == "gpt-4o")

    def test_inserts_new_rec_when_no_existing_open(self):
        from api.workers.recommendations import generate_org_recommendations

        summaries = [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "feature_tag": None,
                "total_cost_usd": "100.00",
                "total_requests": 1000,
                "total_tokens": 500_000,
            }
        ]

        with patch("api.workers.recommendations._get_supabase") as mock_sup:
            db = MagicMock()
            db.table.return_value = db
            db.select.return_value = db
            db.insert.return_value = db
            db.eq.return_value = db
            db.gte.return_value = db
            db.order.return_value = db

            execute_results = iter([
                MagicMock(data=summaries),
                MagicMock(data=[]),  # no existing open recs
                MagicMock(data=[{"id": "new-1"}]),
                MagicMock(data=[{"id": "new-2"}]),
                MagicMock(data=[{"id": "new-3"}]),
            ])
            db.execute.side_effect = lambda: next(execute_results)
            mock_sup.return_value = db

            generate_org_recommendations("org-1")

        assert db.insert.called

    def test_no_data_returns_early(self):
        from api.workers.recommendations import generate_org_recommendations

        with patch("api.workers.recommendations._get_supabase") as mock_sup:
            db = MagicMock()
            db.table.return_value = db
            db.select.return_value = db
            db.eq.return_value = db
            db.gte.return_value = db
            db.execute.return_value = MagicMock(data=[])
            mock_sup.return_value = db

            generate_org_recommendations("org-1")

        db.insert.assert_not_called()


# ── router tests ──────────────────────────────────────────────────────────────

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000002"
REC_ID = "rrrrrrrr-0000-0000-0000-000000000001"

app.dependency_overrides[_require_org] = lambda: OrgContext(user_id="user_test", org_id=ORG_ID)
client = TestClient(app)

NOW_ISO = datetime.now(timezone.utc).isoformat()


def _rec_row(
    rec_id: str = REC_ID,
    rec_type: str = "model_swap",
    status: str = "new",
    savings: str = "94.00",
    scope_value: str = "gpt-4o",
) -> dict:
    return {
        "id": rec_id,
        "org_id": ORG_ID,
        "type": rec_type,
        "title": f"Switch gpt-4o → gpt-4o-mini",
        "description": "You can save money by switching models.",
        "projected_savings_usd": savings,
        "confidence": "0.85",
        "evidence": {"model": "gpt-4o"},
        "status": status,
        "scope_value": scope_value,
        "generated_at": NOW_ISO,
        "resolved_at": None,
    }


def _mock_db_router(rows: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows if rows is not None else []
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


class TestRecommendationsRouter:
    def test_list_returns_recommendations(self):
        rows = [_rec_row()]
        with patch("api.routers.recommendations._get_supabase", return_value=_mock_db_router(rows)):
            resp = client.get("/api/v1/recommendations?status=new")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "model_swap"
        assert data[0]["projected_savings_usd"] == "94.00"

    def test_list_returns_empty_when_no_recs(self):
        with patch("api.routers.recommendations._get_supabase", return_value=_mock_db_router([])):
            resp = client.get("/api/v1/recommendations?status=new")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_defaults_to_new_status(self):
        db = _mock_db_router([])
        with patch("api.routers.recommendations._get_supabase", return_value=db):
            client.get("/api/v1/recommendations")
        # Verify the eq call included status=new
        eq_calls = [str(c) for c in db.eq.call_args_list]
        assert any("new" in c for c in eq_calls)

    def test_patch_marks_applied(self):
        existing_row = _rec_row(status="new")
        updated_row = _rec_row(status="applied")

        db = _mock_db_router()
        # First call (ownership check) returns existing row; second call (update) returns updated
        db.execute.side_effect = [
            MagicMock(data=[existing_row]),
            MagicMock(data=[updated_row]),
        ]

        with patch("api.routers.recommendations._get_supabase", return_value=db):
            resp = client.patch(f"/api/v1/recommendations/{REC_ID}", json={"status": "applied"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    def test_patch_marks_dismissed(self):
        updated_row = _rec_row(status="dismissed")
        db = _mock_db_router()
        db.execute.side_effect = [
            MagicMock(data=[_rec_row()]),
            MagicMock(data=[updated_row]),
        ]
        with patch("api.routers.recommendations._get_supabase", return_value=db):
            resp = client.patch(f"/api/v1/recommendations/{REC_ID}", json={"status": "dismissed"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    def test_patch_404_on_wrong_org(self):
        db = _mock_db_router([])  # ownership check returns nothing
        with patch("api.routers.recommendations._get_supabase", return_value=db):
            resp = client.patch(f"/api/v1/recommendations/{REC_ID}", json={"status": "applied"})
        assert resp.status_code == 404

    def test_patch_rejects_invalid_status(self):
        with patch("api.routers.recommendations._get_supabase", return_value=_mock_db_router()):
            resp = client.patch(f"/api/v1/recommendations/{REC_ID}", json={"status": "new"})
        assert resp.status_code == 422  # Pydantic rejects 'new' - only applied/dismissed allowed

    def test_list_accepts_applied_status_filter(self):
        rows = [_rec_row(status="applied")]
        with patch("api.routers.recommendations._get_supabase", return_value=_mock_db_router(rows)):
            resp = client.get("/api/v1/recommendations?status=applied")
        assert resp.status_code == 200

    def test_list_accepts_dismissed_status_filter(self):
        rows = [_rec_row(status="dismissed")]
        with patch("api.routers.recommendations._get_supabase", return_value=_mock_db_router(rows)):
            resp = client.get("/api/v1/recommendations?status=dismissed")
        assert resp.status_code == 200


# ── TC-M3-A01, TC-M3-A02: fan-out task ───────────────────────────────────────


class TestGenerateAllOrgRecommendations:
    """TC-M3-A01 and TC-M3-A02: generate_all_org_recommendations dispatch behaviour."""

    def _mock_db_with_orgs(self, org_ids: list[str]) -> MagicMock:
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.execute.return_value = MagicMock(
            data=[{"org_id": oid} for oid in org_ids]
        )
        return db

    def test_dispatches_one_task_per_active_org(self) -> None:  # TC-M3-A01
        from api.workers.recommendations import generate_all_org_recommendations

        mock_worker = MagicMock()
        mock_worker.delay = MagicMock()

        with (
            patch("api.workers.recommendations._get_supabase") as mock_sup,
            patch("api.workers.recommendations.generate_org_recommendations", mock_worker),
        ):
            mock_sup.return_value = self._mock_db_with_orgs(["org-1", "org-2", "org-3"])
            generate_all_org_recommendations()

        assert mock_worker.delay.call_count == 3
        dispatched_org_ids = {c[0][0] for c in mock_worker.delay.call_args_list}
        assert dispatched_org_ids == {"org-1", "org-2", "org-3"}

    def test_no_dispatch_when_no_active_integrations(self) -> None:  # TC-M3-A02
        from api.workers.recommendations import generate_all_org_recommendations

        mock_worker = MagicMock()
        mock_worker.delay = MagicMock()

        with (
            patch("api.workers.recommendations._get_supabase") as mock_sup,
            patch("api.workers.recommendations.generate_org_recommendations", mock_worker),
        ):
            mock_sup.return_value = self._mock_db_with_orgs([])
            generate_all_org_recommendations()

        mock_worker.delay.assert_not_called()


# ── TC-M3-A03, TC-M3-A04, TC-M3-A05: worker payload + aggregation ────────────


class TestWorkerInsertionAndAggregation:
    """TC-M3-A03, A04, A05: payload completeness, grouping, within-run dedup."""

    def _db_for_org(self, summaries: list[dict], existing_recs: list[dict] | None = None) -> MagicMock:
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.insert.return_value = db
        db.eq.return_value = db
        db.gte.return_value = db
        db.order.return_value = db

        side = [
            MagicMock(data=summaries),
            MagicMock(data=existing_recs or []),
        ]
        # Allow any number of subsequent insert .execute() calls
        db.execute.side_effect = side + [MagicMock(data=[{"id": f"new-{i}"}]) for i in range(10)]
        return db

    def test_inserted_payload_contains_all_required_fields(self) -> None:  # TC-M3-A03
        from api.workers.recommendations import generate_org_recommendations

        summaries = [
            {
                "provider": "openai",
                "model": "gpt-4o",
                "feature_tag": None,
                "total_cost_usd": "100.00",
                "total_requests": 1000,
                "total_tokens": 500_000,
            }
        ]

        with patch("api.workers.recommendations._get_supabase") as mock_sup:
            db = self._db_for_org(summaries)
            mock_sup.return_value = db
            generate_org_recommendations("org-test")

        assert db.insert.called
        payload = db.insert.call_args_list[0][0][0]
        required_fields = {
            "org_id", "type", "title", "description",
            "projected_savings_usd", "confidence", "evidence",
            "scope_value", "status", "generated_at",
        }
        assert required_fields <= set(payload.keys())
        assert payload["org_id"] == "org-test"
        assert payload["status"] == "new"

    def test_multi_row_summaries_aggregated_into_single_stats(self) -> None:  # TC-M3-A04
        """Two rows for the same (provider, model, feature_tag) must be summed."""
        from api.workers.recommendations import generate_org_recommendations

        # Two daily rows for the same group: total = $60 + $40 = $100
        summaries = [
            {
                "provider": "openai", "model": "gpt-4o", "feature_tag": None,
                "total_cost_usd": "60.00", "total_requests": 600, "total_tokens": 300_000,
            },
            {
                "provider": "openai", "model": "gpt-4o", "feature_tag": None,
                "total_cost_usd": "40.00", "total_requests": 400, "total_tokens": 200_000,
            },
        ]

        captured_stats: list = []

        def _capture_recs(stats):
            captured_stats.extend(stats)
            return []  # return empty so no insert paths are needed

        with (
            patch("api.workers.recommendations._get_supabase") as mock_sup,
            patch("api.workers.recommendations.generate_recommendations", side_effect=_capture_recs),
        ):
            db = self._db_for_org(summaries)
            mock_sup.return_value = db
            generate_org_recommendations("org-test")

        # The two rows must have been merged into a single ModelStats
        assert len(captured_stats) == 1
        from decimal import Decimal
        assert captured_stats[0].total_cost_usd == Decimal("100.00")
        assert captured_stats[0].total_requests == 1000
        assert captured_stats[0].total_tokens == 500_000

    def test_within_run_dedup_prevents_double_insert(self) -> None:  # TC-M3-A05
        """
        If generate_recommendations returns two Recommendations with the same
        (type, scope_value), only the first should be inserted; the second is
        blocked by the existing_keys.add() guard inside the worker loop.
        """
        from api.workers.recommendations import generate_org_recommendations
        from api.services.recommendations import Recommendation
        from decimal import Decimal

        duplicate_rec = Recommendation(
            type="model_swap",
            title="Switch gpt-4o → gpt-4o-mini",
            description="desc",
            projected_savings_usd=Decimal("94.00"),
            confidence=Decimal("0.85"),
            evidence={},
            scope_value="gpt-4o",
        )

        summaries = [
            {
                "provider": "openai", "model": "gpt-4o", "feature_tag": None,
                "total_cost_usd": "100.00", "total_requests": 1000, "total_tokens": 500_000,
            }
        ]

        with (
            patch("api.workers.recommendations._get_supabase") as mock_sup,
            # Return two identical recs - simulates a hypothetical service bug
            patch(
                "api.workers.recommendations.generate_recommendations",
                return_value=[duplicate_rec, duplicate_rec],
            ),
        ):
            db = self._db_for_org(summaries, existing_recs=[])
            mock_sup.return_value = db
            generate_org_recommendations("org-test")

        # Only one insert despite two identical recs
        assert db.insert.call_count == 1


# ── TC-REC-20: input_compression type not yet implemented ─────────────────────

class TestInputCompressionNotImplemented:
    """
    TC-REC-20 - FR-19 spec gap tracker: input_compression recommendation type
    is NOT returned by generate_recommendations (not yet implemented).

    When implemented: update this test to assert input_compression IS returned
    when avg_tokens > 2000 for an eligible model.
    """

    def test_input_compression_type_not_returned(self) -> None:
        """TC-REC-20 - generate_recommendations never returns type='input_compression'."""
        # Stats that would trigger input_compression if it were implemented:
        # avg_tokens = 3_000_000 / 500 = 6000 > 2000 threshold, high cost
        heavy_stats = [
            ModelStats(
                provider="anthropic",
                model="claude-opus-4-5",
                feature_tag=None,
                total_cost_usd=Decimal("300.00"),
                total_requests=500,
                total_tokens=3_000_000,
            )
        ]
        recs = generate_recommendations(heavy_stats)
        types_returned = {r.type for r in recs}
        assert "input_compression" not in types_returned, (
            "input_compression rule was unexpectedly implemented. "
            "Update this test to assert it IS returned (see FR-19, BUG-08)."
        )
