"""
Unit tests for the tag-rule engine.
No DB access - all pure function tests.
"""

import pytest

from api.services.tag_engine import CompiledRule, apply_rules, compile_rules


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db_row(
    match_type: str,
    match_pattern: str,
    tag_type: str,
    tag_name: str,
    priority: int = 100,
    enabled: bool = True,
) -> dict:
    """Build a fake PostgREST row (tag_rules joined with tags)."""
    return {
        "match_type": match_type,
        "match_pattern": match_pattern,
        "priority": priority,
        "enabled": enabled,
        "tags": {"type": tag_type, "name": tag_name},
    }


def _rule(
    tag_type: str,
    tag_name: str,
    match_type: str,
    match_pattern: str,
    priority: int = 100,
) -> CompiledRule:
    return CompiledRule(
        tag_type=tag_type,
        tag_name=tag_name,
        match_type=match_type,
        match_pattern=match_pattern,
        priority=priority,
    )


_EMPTY_TAGS = {"feature_tag": None, "team_tag": None, "customer_tag": None, "env_tag": None}


# ── compile_rules ─────────────────────────────────────────────────────────────

class TestCompileRules:
    def test_empty_input_returns_empty_list(self) -> None:
        assert compile_rules([]) == []

    def test_disabled_rules_are_excluded(self) -> None:
        rows = [_db_row("exact", "prod", "env", "production", enabled=False)]
        assert compile_rules(rows) == []

    def test_enabled_rule_is_included(self) -> None:
        rows = [_db_row("exact", "prod-key", "env", "production", priority=50)]
        result = compile_rules(rows)
        assert len(result) == 1
        assert result[0].tag_type == "env"
        assert result[0].tag_name == "production"
        assert result[0].match_pattern == "prod-key"
        assert result[0].priority == 50

    def test_sorts_by_priority_ascending(self) -> None:
        rows = [
            _db_row("exact", "b", "feature", "B", priority=200),
            _db_row("exact", "a", "team", "A", priority=10),
            _db_row("exact", "c", "customer", "C", priority=100),
        ]
        result = compile_rules(rows)
        assert [r.priority for r in result] == [10, 100, 200]

    def test_row_missing_tags_key_is_skipped(self) -> None:
        row = {"match_type": "exact", "match_pattern": "x", "priority": 100, "enabled": True, "tags": None}
        assert compile_rules([row]) == []

    def test_row_without_enabled_key_defaults_to_included(self) -> None:
        """Rows without 'enabled' key should default to True (included)."""
        row = {
            "match_type": "exact",
            "match_pattern": "x",
            "priority": 100,
            "tags": {"type": "env", "name": "prod"},
        }
        result = compile_rules([row])
        assert len(result) == 1

    def test_mixed_enabled_and_disabled(self) -> None:
        rows = [
            _db_row("exact", "a", "feature", "A", priority=1, enabled=True),
            _db_row("exact", "b", "team", "B", priority=2, enabled=False),
            _db_row("exact", "c", "env", "C", priority=3, enabled=True),
        ]
        result = compile_rules(rows)
        assert len(result) == 2
        assert result[0].tag_type == "feature"
        assert result[1].tag_type == "env"


# ── apply_rules - no rules ────────────────────────────────────────────────────

class TestApplyRulesNoRules:
    def test_no_rules_returns_all_none(self) -> None:
        assert apply_rules("prod-api-key", []) == _EMPTY_TAGS

    def test_none_label_no_rules_returns_all_none(self) -> None:
        assert apply_rules(None, []) == _EMPTY_TAGS


# ── apply_rules - exact matching ──────────────────────────────────────────────

class TestExactMatching:
    def test_exact_match_assigns_tag(self) -> None:
        rules = [_rule("env", "production", "exact", "prod-key")]
        result = apply_rules("prod-key", rules)
        assert result["env_tag"] == "production"

    def test_exact_no_match_returns_none(self) -> None:
        rules = [_rule("env", "production", "exact", "prod-key")]
        result = apply_rules("staging-key", rules)
        assert result["env_tag"] is None

    def test_exact_is_case_sensitive(self) -> None:
        rules = [_rule("env", "production", "exact", "Prod-Key")]
        result = apply_rules("prod-key", rules)
        assert result["env_tag"] is None

    def test_exact_partial_string_does_not_match(self) -> None:
        rules = [_rule("env", "production", "exact", "prod")]
        result = apply_rules("prod-key-123", rules)
        assert result["env_tag"] is None


# ── apply_rules - substring matching ─────────────────────────────────────────

class TestSubstringMatching:
    def test_substring_match_anywhere_in_label(self) -> None:
        rules = [_rule("feature", "chat", "substring", "chat")]
        result = apply_rules("sk-prod-chat-service-01", rules)
        assert result["feature_tag"] == "chat"

    def test_substring_at_start(self) -> None:
        rules = [_rule("team", "alpha", "substring", "alpha")]
        result = apply_rules("alpha-team-key", rules)
        assert result["team_tag"] == "alpha"

    def test_substring_no_match(self) -> None:
        rules = [_rule("feature", "chat", "substring", "chat")]
        result = apply_rules("production-gpt-key", rules)
        assert result["feature_tag"] is None

    def test_empty_pattern_matches_any_label(self) -> None:
        """Empty substring pattern matches everything (any string contains '')."""
        rules = [_rule("env", "default", "substring", "")]
        result = apply_rules("anything", rules)
        assert result["env_tag"] == "default"


# ── apply_rules - regex matching ──────────────────────────────────────────────

class TestRegexMatching:
    def test_regex_match(self) -> None:
        rules = [_rule("env", "production", "regex", r"^prod-")]
        result = apply_rules("prod-api-v2", rules)
        assert result["env_tag"] == "production"

    def test_regex_no_match(self) -> None:
        rules = [_rule("env", "production", "regex", r"^prod-")]
        result = apply_rules("staging-api", rules)
        assert result["env_tag"] is None

    def test_invalid_regex_returns_false_does_not_raise(self) -> None:
        """Invalid regex patterns must not propagate exceptions."""
        rules = [_rule("env", "production", "regex", r"[invalid")]
        result = apply_rules("anything", rules)
        assert result["env_tag"] is None

    def test_regex_uses_search_not_fullmatch(self) -> None:
        """re.search allows pattern anywhere in the string."""
        rules = [_rule("team", "ml", "regex", r"ml-\d+")]
        result = apply_rules("sk-prod-ml-42-key", rules)
        assert result["team_tag"] == "ml"


# ── apply_rules - priority and multi-type ────────────────────────────────────

class TestApplyRulesPriority:
    def test_lower_priority_number_wins(self) -> None:
        """Priority 10 beats priority 50 for the same tag type."""
        rules = compile_rules([
            _db_row("substring", "prod", "env", "production", priority=50),
            _db_row("substring", "prod", "env", "prod-env", priority=10),
        ])
        result = apply_rules("prod-key", rules)
        assert result["env_tag"] == "prod-env"

    def test_first_match_per_type_wins_second_ignored(self) -> None:
        rules = compile_rules([
            _db_row("exact", "my-key", "feature", "feature-A", priority=1),
            _db_row("exact", "my-key", "feature", "feature-B", priority=2),
        ])
        result = apply_rules("my-key", rules)
        assert result["feature_tag"] == "feature-A"

    def test_multiple_types_assigned_from_different_rules(self) -> None:
        rules = compile_rules([
            _db_row("substring", "prod", "env", "production", priority=10),
            _db_row("substring", "chat", "feature", "chat-service", priority=20),
            _db_row("substring", "team-a", "team", "alpha", priority=30),
        ])
        result = apply_rules("prod-chat-team-a-key", rules)
        assert result["env_tag"] == "production"
        assert result["feature_tag"] == "chat-service"
        assert result["team_tag"] == "alpha"
        assert result["customer_tag"] is None

    def test_all_four_types_assigned(self) -> None:
        rules = compile_rules([
            _db_row("substring", "feat", "feature", "my-feature", priority=1),
            _db_row("substring", "team", "team", "my-team", priority=2),
            _db_row("substring", "cust", "customer", "my-customer", priority=3),
            _db_row("substring", "env", "env", "my-env", priority=4),
        ])
        result = apply_rules("feat-team-cust-env-key", rules)
        assert result == {
            "feature_tag": "my-feature",
            "team_tag": "my-team",
            "customer_tag": "my-customer",
            "env_tag": "my-env",
        }

    def test_none_label_treated_as_empty_string(self) -> None:
        """None label should not cause AttributeError."""
        rules = [_rule("env", "untagged", "substring", "")]
        result = apply_rules(None, rules)
        assert result["env_tag"] == "untagged"

    def test_empty_label_treated_as_empty_string(self) -> None:
        rules = [_rule("env", "untagged", "exact", "")]
        result = apply_rules("", rules)
        assert result["env_tag"] == "untagged"

    def test_returns_none_for_unmatched_types(self) -> None:
        rules = [_rule("feature", "chat", "substring", "chat")]
        result = apply_rules("chat-prod-key", rules)
        assert result["feature_tag"] == "chat"
        assert result["team_tag"] is None
        assert result["customer_tag"] is None
        assert result["env_tag"] is None
