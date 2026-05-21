"""
Tag engine security and correctness gap tests.

Gap-22 (high): _matches() uses re.search() with no timeout — ReDoS vulnerability.
               Invalid regex returns False (safe). Empty substring matches any label.
"""

import time

import pytest

from api.services.tag_engine import CompiledRule, _matches, apply_rules, compile_rules


# ── Helper ─────────────────────────────────────────────────────────────────────

def _rule(
    match_type: str,
    pattern: str,
    tag_type: str = "feature",
    tag_name: str = "test-tag",
    priority: int = 1,
) -> CompiledRule:
    return CompiledRule(
        tag_type=tag_type,
        tag_name=tag_name,
        match_type=match_type,
        match_pattern=pattern,
        priority=priority,
    )


# ── Gap-22: ReDoS vulnerability in _matches() ─────────────────────────────────

class TestMatchesRegexSecurity:
    """Gap-22 (high): No regex timeout in _matches() — catastrophic backtracking possible."""

    def test_invalid_regex_returns_false_without_raising(self) -> None:
        """
        An invalid regex pattern (unclosed group, invalid escape) must return False
        silently. re.error is caught and suppressed — no exception escapes.
        """
        invalid_patterns = [
            "[invalid(regex",   # unclosed bracket + group
            "(?P<name",         # malformed named group
            "(a|b",             # unclosed alternation
            "\\",               # trailing backslash
        ]
        for pattern in invalid_patterns:
            rule = _rule("regex", pattern)
            result = _matches(rule, "some label string")
            assert result is False, (
                f"Gap-22: Invalid regex '{pattern}' must return False, not raise. "
                f"Got {result!r}."
            )

    def test_catastrophic_backtracking_regex_completes_without_hang(self) -> None:
        """
        Gap-22 (critical sub-issue): Classic ReDoS pattern ^(a+)+$ with a long
        non-matching string causes exponential backtracking in naive regex engines.
        This test will HANG (timeout) if the engine is vulnerable.

        CPython 3.11+ has some mitigations, but complex patterns are still risky.
        Fix: wrap re.search() with a signal-based timeout (Linux) or use the re2 library.
        """
        rule = _rule("regex", r"^(a+)+$")
        # Classic ReDoS input: many 'a's followed by a non-matching char
        evil_input = "a" * 25 + "!"

        start = time.monotonic()
        result = _matches(rule, evil_input)
        elapsed = time.monotonic() - start

        assert result is False, "^(a+)+$ must not match 'aaa...a!'"
        # If this assertion fails, the regex engine backtracked catastrophically
        assert elapsed < 5.0, (
            f"Gap-22: ReDoS pattern took {elapsed:.3f}s (expected < 5s). "
            "Catastrophic backtracking detected. Fix: add re timeout or use re2."
        )

    def test_another_redos_pattern(self) -> None:
        """
        Second ReDoS family: (a|aa)+ with a long non-matching string.
        """
        rule = _rule("regex", r"^(a|aa)+$")
        evil_input = "a" * 20 + "b"

        start = time.monotonic()
        result = _matches(rule, evil_input)
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed < 5.0, (
            f"Gap-22: (a|aa)+ ReDoS took {elapsed:.3f}s. "
            "Potentially vulnerable to denial-of-service."
        )

    def test_valid_regex_matches_correctly(self) -> None:
        """Sanity check: valid regex patterns match as expected."""
        assert _matches(_rule("regex", r"^gpt-4"), "gpt-4o") is True
        assert _matches(_rule("regex", r"^gpt-4"), "claude-sonnet") is False
        assert _matches(_rule("regex", r"(?i)PROD"), "production-key") is True
        assert _matches(_rule("regex", r"\d{4}"), "key-2026-test") is True

    def test_empty_substring_matches_any_label(self) -> None:
        """
        Empty substring pattern ('') is contained in every string including ''.
        This acts as a catch-all — any label gets assigned the tag.
        """
        rule = _rule("substring", "")
        assert _matches(rule, "any-api-key-label") is True
        assert _matches(rule, "") is True
        assert _matches(rule, "production-openai-key") is True

    def test_empty_exact_matches_only_empty_label(self) -> None:
        """Exact match with '' matches only the empty/None label (coerced to '')."""
        rule = _rule("exact", "")
        assert _matches(rule, "") is True
        assert _matches(rule, "not-empty") is False

    def test_unknown_match_type_returns_false(self) -> None:
        """Any match_type not in {exact, substring, regex} falls through to False."""
        for unknown_type in ("glob", "fuzzy", "prefix", "", "REGEX"):
            rule = CompiledRule(
                tag_type="feature",
                tag_name="should-not-match",
                match_type=unknown_type,
                match_pattern="anything",
                priority=1,
            )
            assert _matches(rule, "anything") is False, (
                f"Unknown match_type '{unknown_type}' must return False"
            )


# ── Additional compile_rules / apply_rules coverage ──────────────────────────

class TestTagEngineRuleApplication:
    """Additional coverage for compile_rules and apply_rules edge cases."""

    def test_compile_rules_excludes_disabled_rules(self) -> None:
        """Disabled rules (enabled=False) must be excluded from compiled output."""
        rows = [
            {
                "match_type": "exact",
                "match_pattern": "key",
                "priority": 1,
                "enabled": False,
                "tags": {"type": "feature", "name": "should-not-appear"},
            },
            {
                "match_type": "exact",
                "match_pattern": "key",
                "priority": 2,
                "enabled": True,
                "tags": {"type": "feature", "name": "should-appear"},
            },
        ]
        compiled = compile_rules(rows)
        assert len(compiled) == 1
        assert compiled[0].tag_name == "should-appear"

    def test_compile_rules_excludes_rows_with_no_tags(self) -> None:
        """Rows with tags=None or tags={} are excluded."""
        rows = [
            {
                "match_type": "exact",
                "match_pattern": "key",
                "priority": 1,
                "enabled": True,
                "tags": {},  # empty dict
            },
            {
                "match_type": "exact",
                "match_pattern": "key",
                "priority": 2,
                "enabled": True,
                "tags": None,  # null
            },
        ]
        compiled = compile_rules(rows)
        assert compiled == []

    def test_compile_rules_sorted_by_priority_ascending(self) -> None:
        """compile_rules must sort rules by priority ASC (lower number = higher priority)."""
        rows = [
            {"match_type": "exact", "match_pattern": "a", "priority": 10, "enabled": True,
             "tags": {"type": "feature", "name": "low-priority"}},
            {"match_type": "exact", "match_pattern": "b", "priority": 1, "enabled": True,
             "tags": {"type": "feature", "name": "high-priority"}},
            {"match_type": "exact", "match_pattern": "c", "priority": 5, "enabled": True,
             "tags": {"type": "feature", "name": "mid-priority"}},
        ]
        compiled = compile_rules(rows)
        priorities = [r.priority for r in compiled]
        assert priorities == sorted(priorities)
        assert compiled[0].tag_name == "high-priority"

    def test_apply_rules_first_match_per_type_wins(self) -> None:
        """Lower priority number wins when two rules match the same tag type."""
        rules = compile_rules([
            {
                "match_type": "substring",
                "match_pattern": "feature",
                "priority": 1,
                "enabled": True,
                "tags": {"type": "feature", "name": "winner"},
            },
            {
                "match_type": "substring",
                "match_pattern": "feature",
                "priority": 2,
                "enabled": True,
                "tags": {"type": "feature", "name": "loser"},
            },
        ])
        result = apply_rules("feature-api-key", rules)
        assert result["feature_tag"] == "winner"

    def test_apply_rules_none_label_coerced_to_empty_string(self) -> None:
        """None label is treated as '' — a rule matching '' will fire."""
        rules = compile_rules([
            {
                "match_type": "exact",
                "match_pattern": "",
                "priority": 1,
                "enabled": True,
                "tags": {"type": "team", "name": "untagged"},
            }
        ])
        result = apply_rules(None, rules)
        assert result["team_tag"] == "untagged"

    def test_apply_rules_all_tag_types_resolved(self) -> None:
        """All four tag types can be resolved in one apply_rules call."""
        rules = compile_rules([
            {"match_type": "substring", "match_pattern": "prod", "priority": 1, "enabled": True,
             "tags": {"type": "env", "name": "production"}},
            {"match_type": "substring", "match_pattern": "api-key", "priority": 1, "enabled": True,
             "tags": {"type": "feature", "name": "api"}},
            {"match_type": "substring", "match_pattern": "platform", "priority": 1, "enabled": True,
             "tags": {"type": "team", "name": "platform-team"}},
            {"match_type": "substring", "match_pattern": "customer", "priority": 1, "enabled": True,
             "tags": {"type": "customer", "name": "acme"}},
        ])
        label = "prod-platform-api-key-customer-acme"
        result = apply_rules(label, rules)
        assert result["env_tag"] == "production"
        assert result["feature_tag"] == "api"
        assert result["team_tag"] == "platform-team"
        assert result["customer_tag"] == "acme"

    def test_apply_rules_early_exit_when_all_types_resolved(self) -> None:
        """
        Once all 4 tag types are resolved, apply_rules must stop iterating.
        Verify by having a 5th rule that would only match if iteration continued.
        """
        rules = compile_rules([
            {"match_type": "substring", "match_pattern": "x", "priority": 1, "enabled": True,
             "tags": {"type": "feature", "name": "feat-x"}},
            {"match_type": "substring", "match_pattern": "x", "priority": 2, "enabled": True,
             "tags": {"type": "team", "name": "team-x"}},
            {"match_type": "substring", "match_pattern": "x", "priority": 3, "enabled": True,
             "tags": {"type": "customer", "name": "cust-x"}},
            {"match_type": "substring", "match_pattern": "x", "priority": 4, "enabled": True,
             "tags": {"type": "env", "name": "env-x"}},
            # This rule would overwrite feature_tag if iteration continued past 4 resolved types
            {"match_type": "substring", "match_pattern": "x", "priority": 5, "enabled": True,
             "tags": {"type": "feature", "name": "should-not-win"}},
        ])
        result = apply_rules("label-x", rules)
        assert result["feature_tag"] == "feat-x"  # first match wins
        assert result["team_tag"] == "team-x"
        assert result["customer_tag"] == "cust-x"
        assert result["env_tag"] == "env-x"
