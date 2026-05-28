"""
Tests for manual tag override endpoints and ingestion worker override preservation.

Covers:
  - GET /usage/events  (admin-only event browser)
  - PATCH /usage/events/{id}/tags  (admin-only tag override)
  - _snapshot_overrides / _restore_overrides helpers in the ingestion worker
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from api.deps import OrgContext, _require_org, _require_admin_org
from api.main import app
from api.workers.ingestion import _norm_bucket_hour, _restore_overrides, _snapshot_overrides

ORG_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "user_test"
EVENT_ID = "eeeeeeee-0000-0000-0000-000000000001"

_org_ctx = OrgContext(user_id=USER_ID, org_id=ORG_ID)

# Override both auth dependencies - tests exercise admin paths
app.dependency_overrides[_require_org] = lambda: _org_ctx
app.dependency_overrides[_require_admin_org] = lambda: _org_ctx

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows
    db.table.return_value = db
    db.select.return_value = db
    db.eq.return_value = db
    db.gte.return_value = db
    db.lt.return_value = db
    db.lte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.update.return_value = db
    db.execute.return_value = result
    return db


def _sample_event(**overrides) -> dict:
    base = {
        "id": EVENT_ID,
        "provider": "openai",
        "model": "gpt-4o",
        "api_key_label": "prod-key",
        "feature_tag": None,
        "team_tag": None,
        "customer_tag": None,
        "env_tag": None,
        "cost_usd": "1.500000",
        "request_count": 10,
        "input_tokens": 5000,
        "output_tokens": 2000,
        "bucket_hour": "2025-01-15T12:00:00+00:00",
        "manual_override": False,
    }
    return {**base, **overrides}


# ── GET /usage/events ─────────────────────────────────────────────────────────

class TestListUsageEvents:
    def test_returns_event_list(self) -> None:
        rows = [_sample_event()]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/events")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == EVENT_ID
        assert body[0]["provider"] == "openai"
        assert body[0]["manual_override"] is False

    def test_empty_db_returns_empty_list(self) -> None:
        with patch("api.routers.usage._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/usage/events")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_param_forwarded(self) -> None:
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            client.get("/api/v1/usage/events?limit=50")

        limit_calls = [c.args for c in db.limit.call_args_list]
        assert (50,) in limit_calls

    def test_limit_above_max_rejected(self) -> None:
        resp = client.get("/api/v1/usage/events?limit=9999")
        assert resp.status_code == 422

    # TC-EV-101
    def test_results_ordered_by_bucket_hour_desc(self) -> None:
        """Events must be fetched newest-first so the UI shows the most recent rows."""
        db = _mock_db([])
        with patch("api.routers.usage._get_supabase", return_value=db):
            client.get("/api/v1/usage/events")

        db.order.assert_called_once_with("bucket_hour", desc=True)

    # TC-EV-102
    def test_response_includes_all_required_fields(self) -> None:
        """Each row must expose the full UsageEventRead projection."""
        rows = [_sample_event()]
        with patch("api.routers.usage._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/usage/events")

        assert resp.status_code == 200
        row = resp.json()[0]
        required = {
            "id", "provider", "model", "api_key_label",
            "feature_tag", "team_tag", "customer_tag", "env_tag",
            "cost_usd", "request_count", "input_tokens", "output_tokens",
            "bucket_hour", "manual_override",
        }
        assert required.issubset(row.keys())


# ── PATCH /usage/events/{id}/tags ─────────────────────────────────────────────

class TestOverrideEventTags:
    def test_happy_path_sets_feature_tag(self) -> None:
        updated = _sample_event(feature_tag="payments", manual_override=True)
        db = _mock_db([{"id": EVENT_ID}])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),   # ownership check
            MagicMock(data=[{"id": EVENT_ID}]),   # user lookup
            MagicMock(data=[updated]),             # update + return
        ]

        # aggregate_org is a local import inside the endpoint; patch at source module
        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org") as mock_agg,
        ):
            resp = client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": "payments"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["feature_tag"] == "payments"
        assert body["manual_override"] is True
        mock_agg.delay.assert_called_once_with(ORG_ID)

    def test_404_when_event_not_in_org(self) -> None:
        db = _mock_db([])
        db.execute.side_effect = [MagicMock(data=[])]  # ownership check returns nothing

        with patch("api.routers.usage._get_supabase", return_value=db):
            resp = client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": "payments"},
            )

        assert resp.status_code == 404

    def test_empty_patch_body_rejected(self) -> None:
        """Body with no tag fields must be rejected before hitting the DB."""
        resp = client.patch(
            f"/api/v1/usage/events/{EVENT_ID}/tags",
            json={},
        )
        assert resp.status_code == 422

    def test_multiple_tag_fields_accepted(self) -> None:
        updated = _sample_event(feature_tag="search", team_tag="ml", manual_override=True)
        db = _mock_db([])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),
            MagicMock(data=[{"id": EVENT_ID}]),
            MagicMock(data=[updated]),
        ]

        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org"),
        ):
            resp = client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": "search", "team_tag": "ml"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["feature_tag"] == "search"
        assert body["team_tag"] == "ml"

    def test_aggregate_org_enqueued_on_success(self) -> None:
        updated = _sample_event(env_tag="prod", manual_override=True)
        db = _mock_db([])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),
            MagicMock(data=[{"id": EVENT_ID}]),
            MagicMock(data=[updated]),
        ]

        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org") as mock_agg,
        ):
            client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"env_tag": "prod"},
            )

        mock_agg.delay.assert_called_once_with(ORG_ID)

    # TC-OV-101
    def test_manual_override_by_set_to_supabase_user_id(self) -> None:
        """The DB update payload must include the resolved Supabase user UUID."""
        SUPABASE_USER_ID = "supabase-user-uuid-001"
        updated = _sample_event(feature_tag="search", manual_override=True)
        db = _mock_db([])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),               # ownership check
            MagicMock(data=[{"id": SUPABASE_USER_ID}]),       # user lookup
            MagicMock(data=[updated]),                         # update + return
        ]

        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org"),
        ):
            resp = client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": "search"},
            )

        assert resp.status_code == 200
        update_payload = db.update.call_args.args[0]
        assert update_payload["manual_override_by"] == SUPABASE_USER_ID

    # TC-OV-102
    def test_manual_override_at_set_in_db_update(self) -> None:
        """The DB update must include a non-null ISO-8601 timestamp for manual_override_at."""
        updated = _sample_event(feature_tag="billing", manual_override=True)
        db = _mock_db([])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),
            MagicMock(data=[{"id": "some-uuid"}]),
            MagicMock(data=[updated]),
        ]

        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org"),
        ):
            client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": "billing"},
            )

        update_payload = db.update.call_args.args[0]
        ts = update_payload.get("manual_override_at")
        assert ts is not None
        # Must parse as a valid timezone-aware datetime
        from datetime import datetime as _dt
        parsed = _dt.fromisoformat(ts)
        assert parsed.tzinfo is not None

    # TC-OV-103
    def test_manual_override_by_none_when_user_lookup_fails(self) -> None:
        """If the user lookup returns no rows, manual_override_by stays None (best-effort)."""
        updated = _sample_event(feature_tag="search", manual_override=True)
        db = _mock_db([])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),   # ownership check
            MagicMock(data=[]),                    # user lookup: no match
            MagicMock(data=[updated]),             # update + return
        ]

        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org"),
        ):
            resp = client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": "search"},
            )

        assert resp.status_code == 200
        update_payload = db.update.call_args.args[0]
        assert update_payload["manual_override_by"] is None

    # TC-OV-104
    def test_null_tag_value_clears_existing_tag(self) -> None:
        """Sending null for a tag field should clear it in the DB update payload."""
        updated = _sample_event(feature_tag=None, manual_override=True)
        db = _mock_db([])
        db.execute.side_effect = [
            MagicMock(data=[{"id": EVENT_ID}]),
            MagicMock(data=[{"id": "some-uuid"}]),
            MagicMock(data=[updated]),
        ]

        with (
            patch("api.routers.usage._get_supabase", return_value=db),
            patch("api.workers.aggregation.aggregate_org"),
        ):
            resp = client.patch(
                f"/api/v1/usage/events/{EVENT_ID}/tags",
                json={"feature_tag": None},  # explicit null to clear
            )

        assert resp.status_code == 200
        update_payload = db.update.call_args.args[0]
        assert "feature_tag" in update_payload
        assert update_payload["feature_tag"] is None


# ── AdminOrgDep enforcement ───────────────────────────────────────────────────

class TestAdminRequired:
    def test_non_admin_gets_403_on_events_list(self) -> None:
        # Remove the admin override so the real dependency runs
        del app.dependency_overrides[_require_admin_org]
        try:
            db = _mock_db([])
            # user lookup returns a row but role is 'member'
            db.execute.side_effect = [
                MagicMock(data=[{"id": "user-uuid"}]),   # users lookup
                MagicMock(data=[{"role": "member"}]),    # org member check
            ]
            with patch("api.deps.create_client", return_value=db):
                resp = client.get("/api/v1/usage/events")
        finally:
            app.dependency_overrides[_require_admin_org] = lambda: _org_ctx

        assert resp.status_code == 403

    def test_user_not_found_gets_403(self) -> None:
        del app.dependency_overrides[_require_admin_org]
        try:
            db = _mock_db([])
            db.execute.side_effect = [MagicMock(data=[])]  # no user found
            with patch("api.deps.create_client", return_value=db):
                resp = client.get("/api/v1/usage/events")
        finally:
            app.dependency_overrides[_require_admin_org] = lambda: _org_ctx

        assert resp.status_code == 403

    # TC-OV-105
    def test_non_admin_gets_403_on_patch_endpoint(self) -> None:
        """AdminOrgDep must block non-admins on PATCH /usage/events/{id}/tags too."""
        del app.dependency_overrides[_require_admin_org]
        try:
            db = _mock_db([])
            db.execute.side_effect = [
                MagicMock(data=[{"id": "user-uuid"}]),   # users lookup
                MagicMock(data=[{"role": "member"}]),    # org member check
            ]
            with patch("api.deps.create_client", return_value=db):
                resp = client.patch(
                    f"/api/v1/usage/events/{EVENT_ID}/tags",
                    json={"feature_tag": "payments"},
                )
        finally:
            app.dependency_overrides[_require_admin_org] = lambda: _org_ctx

        assert resp.status_code == 403


# ── Ingestion worker helpers ───────────────────────────────────────────────────

class TestNormBucketHour:
    def test_iso_with_offset(self) -> None:
        result = _norm_bucket_hour("2025-01-15T12:00:00+00:00")
        assert result == "2025-01-15T12:00:00+00:00"

    def test_postgres_space_format(self) -> None:
        result = _norm_bucket_hour("2025-01-15 12:00:00+00")
        assert result == "2025-01-15T12:00:00+00:00"

    def test_naive_datetime_treated_as_utc(self) -> None:
        result = _norm_bucket_hour("2025-01-15T12:00:00")
        assert result == "2025-01-15T12:00:00+00:00"


class TestSnapshotOverrides:
    def test_returns_empty_when_no_overrides(self) -> None:
        db = _mock_db([])
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        result = _snapshot_overrides(db, ORG_ID, "int-1", start, end)

        assert result == {}

    def test_indexes_by_model_label_hour(self) -> None:
        db = _mock_db([
            {
                "model": "gpt-4o",
                "api_key_label": "prod",
                "bucket_hour": "2025-01-15T12:00:00+00:00",
                "feature_tag": "payments",
                "team_tag": None,
                "customer_tag": None,
                "env_tag": "prod",
                "manual_override_by": None,
                "manual_override_at": None,
            }
        ])
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        result = _snapshot_overrides(db, ORG_ID, "int-1", start, end)

        assert len(result) == 1
        key = ("gpt-4o", "prod", "2025-01-15T12:00:00+00:00")
        assert key in result
        assert result[key]["feature_tag"] == "payments"
        assert result[key]["manual_override"] is True

    # TC-IW-101
    def test_none_api_key_label_normalised_to_empty_string_in_key(self) -> None:
        """api_key_label=None must produce "" in the snapshot key, not None."""
        db = _mock_db([
            {
                "model": "gpt-4o",
                "api_key_label": None,
                "bucket_hour": "2025-01-15T12:00:00+00:00",
                "feature_tag": "payments",
                "team_tag": None,
                "customer_tag": None,
                "env_tag": None,
                "manual_override_by": None,
                "manual_override_at": None,
            }
        ])
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        result = _snapshot_overrides(db, ORG_ID, "int-1", start, end)

        assert len(result) == 1
        key = ("gpt-4o", "", "2025-01-15T12:00:00+00:00")
        assert key in result, f"Expected key {key!r} not found; got {list(result.keys())}"


class TestRestoreOverrides:
    def test_patches_matching_row(self) -> None:
        db = MagicMock()
        db.table.return_value = db
        db.update.return_value = db
        db.eq.return_value = db
        db.execute.return_value = MagicMock()

        snapshot = {
            ("gpt-4o", "prod", "2025-01-15T12:00:00+00:00"): {
                "feature_tag": "payments",
                "team_tag": None,
                "customer_tag": None,
                "env_tag": None,
                "manual_override": True,
                "manual_override_by": None,
                "manual_override_at": None,
            }
        }
        rows = [
            {
                "model": "gpt-4o",
                "api_key_label": "prod",
                "bucket_hour": "2025-01-15T12:00:00+00:00",
            }
        ]

        _restore_overrides(db, ORG_ID, "int-1", rows, snapshot)

        db.update.assert_called_once()
        update_arg = db.update.call_args.args[0]
        assert update_arg["feature_tag"] == "payments"
        assert update_arg["manual_override"] is True

    def test_skips_rows_not_in_snapshot(self) -> None:
        db = MagicMock()
        db.table.return_value = db
        db.update.return_value = db

        snapshot: dict = {}  # no overrides
        rows = [{"model": "gpt-4o", "api_key_label": "prod", "bucket_hour": "2025-01-15T12:00:00+00:00"}]

        _restore_overrides(db, ORG_ID, "int-1", rows, snapshot)

        db.update.assert_not_called()

    # TC-IW-102
    def test_multiple_matching_rows_all_restored(self) -> None:
        """Two overridden rows in snapshot → two separate DB update calls."""
        db = MagicMock()
        db.table.return_value = db
        db.update.return_value = db
        db.eq.return_value = db
        db.execute.return_value = MagicMock()

        snapshot = {
            ("gpt-4o", "prod", "2025-01-15T12:00:00+00:00"): {
                "feature_tag": "payments",
                "team_tag": None,
                "customer_tag": None,
                "env_tag": None,
                "manual_override": True,
                "manual_override_by": None,
                "manual_override_at": None,
            },
            ("claude-3-5-sonnet-20241022", "staging", "2025-01-16T08:00:00+00:00"): {
                "feature_tag": "search",
                "team_tag": "ml",
                "customer_tag": None,
                "env_tag": "staging",
                "manual_override": True,
                "manual_override_by": None,
                "manual_override_at": None,
            },
        }
        rows = [
            {"model": "gpt-4o", "api_key_label": "prod", "bucket_hour": "2025-01-15T12:00:00+00:00"},
            {"model": "claude-3-5-sonnet-20241022", "api_key_label": "staging", "bucket_hour": "2025-01-16T08:00:00+00:00"},
        ]

        _restore_overrides(db, ORG_ID, "int-1", rows, snapshot)

        assert db.update.call_count == 2

    # TC-IW-103
    def test_mixed_batch_only_matching_rows_patched(self) -> None:
        """One matching row + one non-matching → exactly one update call."""
        db = MagicMock()
        db.table.return_value = db
        db.update.return_value = db
        db.eq.return_value = db
        db.execute.return_value = MagicMock()

        snapshot = {
            ("gpt-4o", "prod", "2025-01-15T12:00:00+00:00"): {
                "feature_tag": "payments",
                "team_tag": None,
                "customer_tag": None,
                "env_tag": None,
                "manual_override": True,
                "manual_override_by": None,
                "manual_override_at": None,
            },
        }
        rows = [
            {"model": "gpt-4o", "api_key_label": "prod", "bucket_hour": "2025-01-15T12:00:00+00:00"},     # match
            {"model": "claude-3-5-sonnet-20241022", "api_key_label": "prod", "bucket_hour": "2025-01-15T12:00:00+00:00"},  # no match
        ]

        _restore_overrides(db, ORG_ID, "int-1", rows, snapshot)

        assert db.update.call_count == 1
