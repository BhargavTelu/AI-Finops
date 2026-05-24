"""
Tag-rule engine — pure functions, no side effects.

Matches usage event api_key_labels against org tag rules and returns tag assignments.
Rule priority: lower number = higher priority. First match per tag type wins.
"""

import concurrent.futures
import re
from dataclasses import dataclass

# Shared thread pool for regex evaluation; bounded to limit resource usage.
# Regex patterns with catastrophic backtracking are cancelled after this timeout.
_REGEX_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="re_match")
_REGEX_TIMEOUT_SECS = 1.0


@dataclass(frozen=True)
class CompiledRule:
    tag_type: str        # "feature" | "team" | "customer" | "env"
    tag_name: str        # value to store in usage_events (e.g. "chat-v2")
    match_type: str      # "regex" | "substring" | "exact"
    match_pattern: str
    priority: int


def compile_rules(db_rows: list[dict]) -> list[CompiledRule]:
    """
    Convert PostgREST rows (tag_rules joined with tags) into a sorted CompiledRule list.

    Expects each row to contain:
      - match_type, match_pattern, priority, enabled (from tag_rules)
      - tags: {"type": ..., "name": ...}  (PostgREST embedded resource syntax)

    Disabled rules are excluded. Result is sorted priority ASC (lower = higher priority).
    """
    rules: list[CompiledRule] = []
    for row in db_rows:
        if not row.get("enabled", True):
            continue
        tag = row.get("tags") or {}
        if not tag:
            continue
        rules.append(
            CompiledRule(
                tag_type=tag["type"],
                tag_name=tag["name"],
                match_type=row["match_type"],
                match_pattern=row["match_pattern"],
                priority=row["priority"],
            )
        )
    rules.sort(key=lambda r: r.priority)
    return rules


def _matches(rule: CompiledRule, label: str) -> bool:
    """
    Test whether a single rule matches the given label string.

    - exact: full string equality (case-sensitive)
    - substring: pattern appears anywhere in label
    - regex: re.search match; invalid regex patterns return False without raising
    """
    if rule.match_type == "exact":
        return label == rule.match_pattern
    if rule.match_type == "substring":
        return rule.match_pattern in label
    if rule.match_type == "regex":
        try:
            future = _REGEX_EXECUTOR.submit(re.search, rule.match_pattern, label)
            try:
                return bool(future.result(timeout=_REGEX_TIMEOUT_SECS))
            except concurrent.futures.TimeoutError:
                # Pattern is catastrophically backtracking — treat as non-match.
                return False
        except re.error:
            return False
    return False


def apply_rules(label: str | None, rules: list[CompiledRule]) -> dict[str, str | None]:
    """
    Apply compiled rules to a single api_key_label.

    Returns a dict with keys: feature_tag, team_tag, customer_tag, env_tag.
    For each tag type, the first matching rule (lowest priority number) wins.
    Types with no matching rule return None.

    None/empty label is treated as empty string — rules with empty pattern or
    regex patterns like ^$ will still match.
    """
    label_str = label or ""
    result: dict[str, str | None] = {
        "feature_tag": None,
        "team_tag": None,
        "customer_tag": None,
        "env_tag": None,
    }
    assigned: set[str] = set()

    for rule in rules:  # already sorted by priority ASC
        key = f"{rule.tag_type}_tag"
        if key in assigned:
            continue  # first match wins per type
        if _matches(rule, label_str):
            result[key] = rule.tag_name
            assigned.add(key)
        if len(assigned) == 4:
            break  # all types resolved — stop early

    return result
