"""
Route tests for /tags and /tag-rules endpoints.
Supabase calls are mocked. Auth dependency is overridden.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from api.deps import OrgContext, _require_org
from api.main import app

ORG_ID = "00000000-0000-0000-0000-000000000002"

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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows
    db.table.return_value = db
    db.select.return_value = db
    db.insert.return_value = db
    db.update.return_value = db
    db.delete.return_value = db
    db.eq.return_value = db
    db.neq.return_value = db
    db.gte.return_value = db
    db.order.return_value = db
    db.limit.return_value = db
    db.execute.return_value = result
    return db


def _tag_row(
    tag_id: str = "tag-001",
    tag_type: str = "feature",
    name: str = "chat",
    color: str | None = None,
) -> dict:
    return {
        "id": tag_id,
        "org_id": ORG_ID,
        "type": tag_type,
        "name": name,
        "color": color,
    }


def _rule_row(
    rule_id: str = "rule-001",
    tag_id: str = "tag-001",
    match_type: str = "substring",
    match_pattern: str = "chat",
    priority: int = 100,
    enabled: bool = True,
) -> dict:
    return {
        "id": rule_id,
        "org_id": ORG_ID,
        "tag_id": tag_id,
        "match_type": match_type,
        "match_pattern": match_pattern,
        "priority": priority,
        "enabled": enabled,
        "tags": None,
    }


# ── GET /tags ─────────────────────────────────────────────────────────────────


class TestListTags:
    def test_empty_db_returns_empty_list(self) -> None:
        with patch("api.routers.tags._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/tags")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_tags_for_org(self) -> None:
        rows = [_tag_row("t1", "feature", "chat"), _tag_row("t2", "env", "production")]
        with patch("api.routers.tags._get_supabase", return_value=_mock_db(rows)):
            resp = client.get("/api/v1/tags")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["name"] == "chat"
        assert body[1]["name"] == "production"


# ── POST /tags ────────────────────────────────────────────────────────────────


class TestCreateTag:
    def test_creates_tag_returns_201(self) -> None:
        created = _tag_row("new-id", "team", "alpha")
        db = _mock_db([created])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.post("/api/v1/tags", json={"type": "team", "name": "alpha"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "new-id"
        assert body["type"] == "team"
        assert body["name"] == "alpha"

    def test_duplicate_tag_returns_409(self) -> None:
        db = MagicMock()
        db.table.return_value = db
        db.insert.return_value = db
        db.execute.side_effect = Exception("duplicate key value violates unique constraint")
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.post("/api/v1/tags", json={"type": "feature", "name": "chat"})
        assert resp.status_code == 409

    def test_invalid_type_returns_422(self) -> None:
        resp = client.post("/api/v1/tags", json={"type": "invalid", "name": "x"})
        assert resp.status_code == 422


# ── DELETE /tags/{tag_id} ─────────────────────────────────────────────────────


class TestDeleteTag:
    def test_delete_existing_tag_returns_204(self) -> None:
        db = _mock_db([_tag_row("t1")])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.delete("/api/v1/tags/t1")
        assert resp.status_code == 204

    def test_delete_nonexistent_tag_returns_404(self) -> None:
        db = _mock_db([])  # empty result = not found
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.delete("/api/v1/tags/nonexistent")
        assert resp.status_code == 404


# ── GET /tag-rules ────────────────────────────────────────────────────────────


class TestListTagRules:
    def test_empty_db_returns_empty_list(self) -> None:
        with patch("api.routers.tags._get_supabase", return_value=_mock_db([])):
            resp = client.get("/api/v1/tag-rules")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_rules_with_tag_info(self) -> None:
        row = _rule_row("r1", "t1", "substring", "chat", 50)
        row["tags"] = {"type": "feature", "name": "chat"}
        with patch("api.routers.tags._get_supabase", return_value=_mock_db([row])):
            resp = client.get("/api/v1/tag-rules")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["priority"] == 50
        assert body[0]["tags"] == {"type": "feature", "name": "chat"}


# ── POST /tag-rules ───────────────────────────────────────────────────────────


class TestCreateTagRule:
    def test_creates_rule_returns_201(self) -> None:
        created = _rule_row("r-new", "t1", "regex", r"^prod-", 50)
        db = MagicMock()
        result = MagicMock()
        result.data = [{"id": "t1"}]  # tag ownership check
        db.table.return_value = db
        db.select.return_value = db
        db.insert.return_value = db
        db.eq.return_value = db
        # First execute() = tag ownership check, second = insert
        db.execute.side_effect = [
            MagicMock(data=[{"id": "t1"}]),  # tag check OK
            MagicMock(data=[created]),  # insert result
        ]
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.post(
                "/api/v1/tag-rules",
                json={
                    "tag_id": "t1",
                    "match_type": "regex",
                    "match_pattern": r"^prod-",
                    "priority": 50,
                },
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["match_pattern"] == r"^prod-"
        assert body["priority"] == 50

    def test_rule_with_nonexistent_tag_returns_404(self) -> None:
        db = MagicMock()
        db.table.return_value = db
        db.select.return_value = db
        db.eq.return_value = db
        db.execute.return_value = MagicMock(data=[])  # tag not found
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.post(
                "/api/v1/tag-rules",
                json={"tag_id": "nonexistent", "match_type": "exact", "match_pattern": "x"},
            )
        assert resp.status_code == 404


# ── DELETE /tag-rules/{rule_id} ───────────────────────────────────────────────


class TestDeleteTagRule:
    def test_delete_existing_rule_returns_204(self) -> None:
        db = _mock_db([_rule_row("r1")])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.delete("/api/v1/tag-rules/r1")
        assert resp.status_code == 204

    def test_delete_nonexistent_rule_returns_404(self) -> None:
        db = _mock_db([])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.delete("/api/v1/tag-rules/nonexistent")
        assert resp.status_code == 404


# ── POST /tag-rules/preview ───────────────────────────────────────────────────


class TestPreviewTagRule:
    def test_returns_matching_labels(self) -> None:
        usage_rows = [
            {"api_key_label": "prod-api-key", "provider": "openai", "model": "gpt-4o"},
            {"api_key_label": "staging-key", "provider": "openai", "model": "gpt-4o"},
            {
                "api_key_label": "prod-service-key",
                "provider": "anthropic",
                "model": "claude-sonnet-4-5",
            },
        ]
        with patch("api.routers.tags._get_supabase", return_value=_mock_db(usage_rows)):
            resp = client.post(
                "/api/v1/tag-rules/preview",
                json={"match_type": "substring", "match_pattern": "prod"},
            )
        assert resp.status_code == 200
        body = resp.json()
        labels = [m["api_key_label"] for m in body]
        assert "prod-api-key" in labels
        assert "prod-service-key" in labels
        assert "staging-key" not in labels

    def test_returns_empty_list_when_no_match(self) -> None:
        usage_rows = [
            {"api_key_label": "staging-key", "provider": "openai", "model": "gpt-4o"},
        ]
        with patch("api.routers.tags._get_supabase", return_value=_mock_db(usage_rows)):
            resp = client.post(
                "/api/v1/tag-rules/preview",
                json={"match_type": "exact", "match_pattern": "no-match"},
            )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_deduplicates_label_provider_model_combinations(self) -> None:
        usage_rows = [
            {"api_key_label": "prod-key", "provider": "openai", "model": "gpt-4o"},
            {"api_key_label": "prod-key", "provider": "openai", "model": "gpt-4o"},  # duplicate
        ]
        with patch("api.routers.tags._get_supabase", return_value=_mock_db(usage_rows)):
            resp = client.post(
                "/api/v1/tag-rules/preview",
                json={"match_type": "substring", "match_pattern": "prod"},
            )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── TC-TAG-10 to TC-TAG-14: PATCH /tags/:id and PATCH /tag-rules/:id ──────────


class TestUpdateTag:
    """TC-TAG-10 and TC-TAG-11 - PATCH /tags/:id."""

    def test_patch_tag_success_returns_200(self) -> None:
        """TC-TAG-10 - PATCH existing tag updates name and color."""
        updated = _tag_row("tag-001", "feature", "new-name", "#ff0000")
        db = _mock_db([updated])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.patch(
                "/api/v1/tags/tag-001",
                json={"type": "feature", "name": "new-name", "color": "#ff0000"},
            )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        body = resp.json()
        assert body["name"] == "new-name"
        assert body["color"] == "#ff0000"

    def test_patch_nonexistent_tag_returns_404(self) -> None:
        """TC-TAG-11 - PATCH tag that doesn't exist → 404."""
        db = _mock_db([])  # empty → not found
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.patch(
                "/api/v1/tags/nonexistent",
                json={"type": "feature", "name": "x"},
            )
        assert resp.status_code == 404


class TestUpdateTagRule:
    """TC-TAG-12, TC-TAG-13, TC-TAG-14 - PATCH /tag-rules/:id."""

    def test_patch_tag_rule_success_returns_200(self) -> None:
        """TC-TAG-12 - PATCH existing tag rule updates match_pattern and priority."""
        updated = _rule_row("rule-001", "tag-001", "regex", r"^api-", 75)
        db = _mock_db([updated])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.patch(
                "/api/v1/tag-rules/rule-001",
                json={
                    "tag_id": "tag-001",
                    "match_type": "regex",
                    "match_pattern": r"^api-",
                    "priority": 75,
                },
            )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        body = resp.json()
        assert body["match_pattern"] == r"^api-"
        assert body["priority"] == 75

    def test_patch_nonexistent_tag_rule_returns_404(self) -> None:
        """TC-TAG-13 - PATCH tag rule that doesn't exist → 404."""
        db = _mock_db([])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.patch(
                "/api/v1/tag-rules/nonexistent",
                json={"tag_id": "t1", "match_type": "exact", "match_pattern": "x"},
            )
        assert resp.status_code == 404

    def test_patch_tag_rule_cross_org_returns_404(self) -> None:
        """
        TC-TAG-14 - Org B attempts to PATCH a tag rule belonging to Org A.
        The DB query filters by org_id so returns empty → 404.
        No info leak: 404 not 403.
        """
        # The dependency override is Org A's ID (ORG_ID), so the DB filter
        # would include org_id=ORG_ID. Mock returns empty (rule belongs to Org B).
        db = _mock_db([])
        with patch("api.routers.tags._get_supabase", return_value=db):
            resp = client.patch(
                "/api/v1/tag-rules/rule-belongs-to-other-org",
                json={"tag_id": "t1", "match_type": "exact", "match_pattern": "x"},
            )
        assert resp.status_code == 404, f"Expected 404 (no info leak), got {resp.status_code}"
