"""
Unit tests for Slack Block Kit builder functions and email HTML renderers
in workers/notifications.py.
TC-NOT-01 to TC-NOT-13.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from api.workers.notifications import (
    _anomaly_slack_blocks,
    _budget_slack_blocks,
    _digest_slack_blocks,
    _exceeded_email_html,
    _scope_label,
    _warning_email_html,
)


def _make_anomaly(
    severity: str = "high",
    scope_value: str = "claude-3-opus",
    spike_pct: int = 150,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "scope_value": scope_value,
        "spike_pct": spike_pct,
        "baseline_usd": "10.00",
        "actual_usd": "25.00",
        "context": context or {},
    }


# ── _anomaly_slack_blocks ──────────────────────────────────────────────────────


class TestAnomalySlackBlocks:
    def test_high_severity_has_rotating_light(self) -> None:  # TC-NOT-01
        blocks = _anomaly_slack_blocks(_make_anomaly(severity="high"))
        assert len(blocks) >= 2
        first_text: str = blocks[0]["text"]["text"]
        assert ":rotating_light:" in first_text

    def test_medium_severity_has_orange_diamond(self) -> None:  # TC-NOT-02
        blocks = _anomaly_slack_blocks(_make_anomaly(severity="medium"))
        first_text: str = blocks[0]["text"]["text"]
        assert ":large_orange_diamond:" in first_text

    def test_tag_context_block_present(self) -> None:  # TC-NOT-03
        context = {"team_tag": "platform", "feature_tag": "search"}
        blocks = _anomaly_slack_blocks(_make_anomaly(context=context))
        assert len(blocks) >= 3, "Expected a context block as the third element"
        context_block = blocks[2]
        assert context_block["type"] == "context"
        context_text: str = context_block["elements"][0]["text"]
        assert "Team:" in context_text
        assert "Feature:" in context_text


# ── _budget_slack_blocks ───────────────────────────────────────────────────────


class TestBudgetSlackBlocks:
    def test_warning_block_contains_warning_emoji(self) -> None:  # TC-NOT-04
        blocks = _budget_slack_blocks(
            "all providers (global)", Decimal("1000"), Decimal("820"), 82, is_exceeded=False
        )
        header: str = blocks[0]["text"]["text"]
        assert ":warning:" in header

    def test_exceeded_block_contains_red_circle(self) -> None:  # TC-NOT-05
        blocks = _budget_slack_blocks(
            "all providers (global)", Decimal("1000"), Decimal("1100"), 110, is_exceeded=True
        )
        header: str = blocks[0]["text"]["text"]
        assert ":red_circle:" in header


# ── _digest_slack_blocks ───────────────────────────────────────────────────────


class TestDigestSlackBlocks:
    def _blocks(self, mom_pct: int | None) -> list[dict[str, Any]]:
        return _digest_slack_blocks(
            digest_date=date(2026, 5, 20),
            yesterday_usd=Decimal("100"),
            avg_7d_usd=Decimal("90"),
            mom_pct=mom_pct,
            top_drivers=[{"label": "gpt-4o", "usd": Decimal("50")}],
            open_anomaly_count=2,
        )

    def _mom_text(self, mom_pct: int | None) -> str:
        blocks = self._blocks(mom_pct)
        # fields are in blocks[1]
        fields: list[dict[str, Any]] = blocks[1]["fields"]
        mom_field = next(f for f in fields if "Month" in f["text"])
        return mom_field["text"]

    def test_mom_none_shows_no_prior_month_data(self) -> None:  # TC-NOT-06
        assert "No prior month data" in self._mom_text(None)

    def test_mom_positive_shows_plus_prefix(self) -> None:  # TC-NOT-07
        assert "+15% vs last month" in self._mom_text(15)

    def test_mom_negative_shows_minus(self) -> None:  # TC-NOT-08
        assert "-5% vs last month" in self._mom_text(-5)

    def test_mom_flat_shows_flat(self) -> None:  # TC-NOT-09
        assert "Flat vs last month" in self._mom_text(0)


# ── _scope_label ───────────────────────────────────────────────────────────────


class TestScopeLabel:
    def test_global_scope(self) -> None:  # TC-NOT-10
        assert _scope_label("global", None) == "all providers (global)"

    def test_model_scope(self) -> None:  # TC-NOT-11
        assert _scope_label("model", "gpt-4o") == "model: gpt-4o"


# ── Email HTML renderers ───────────────────────────────────────────────────────


class TestEmailHtml:
    def test_warning_html_renders_with_pct(self) -> None:  # TC-NOT-12
        html = _warning_email_html("model: gpt-4o", Decimal("1000"), Decimal("800"), 80)
        assert html  # non-empty string
        assert "80" in html  # pct is in the output

    def test_exceeded_html_contains_exceeded(self) -> None:  # TC-NOT-13
        html = _exceeded_email_html("model: gpt-4o", Decimal("1000"), Decimal("1200"), 120)
        assert html  # non-empty string
        assert "exceeded" in html.lower()
