"""
Rule-based recommendations engine (M3 - no AI).

Rules applied in priority order:
  1. model_swap  - expensive model with a cheaper same-family alternative
  2. caching     - high-volume model+tag group that can benefit from prompt caching
  3. batch       - high request count at low tokens/request, eligible for Batch API

All rules are pure functions over ModelStats - no DB access, fully testable in isolation.
Confidence is numeric (0.0–1.0): 0.85 = high, 0.60 = medium.
"""

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Literal

# Anthropic usage-report model IDs carry a date suffix (claude-sonnet-4-5-20250929);
# the maps below are keyed by model family. Strip the suffix before lookup.
_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def _model_family(model: str) -> str:
    return _DATE_SUFFIX_RE.sub("", model)


# ── Model family downgrade map ────────────────────────────────────────────────
# Maps an expensive model to the cheapest same-family alternative.
# Only include pairs where the cheaper model is broadly task-compatible.
_MODEL_DOWNGRADE: dict[str, str] = {
    "gpt-4o": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4o",
    "o1": "o1-mini",
    "claude-opus-4-5": "claude-sonnet-4-5",
    "claude-opus-4-6": "claude-sonnet-4-6",
    "claude-opus-4-7": "claude-sonnet-4-6",
    "claude-opus-4-8": "claude-sonnet-4-6",
    "claude-sonnet-4-5": "claude-haiku-4-5",
    "claude-sonnet-4-6": "claude-haiku-4-5",
    "claude-3-5-sonnet": "claude-3-5-haiku",
}

# Input price per million tokens - used to compute the savings ratio between models.
# Kept in sync with packages/pricing/pricing.yaml; update both when prices change.
_INPUT_PRICE_PER_MTOK: dict[str, Decimal] = {
    "gpt-4o": Decimal("2.50"),
    "gpt-4o-mini": Decimal("0.15"),
    "gpt-4-turbo": Decimal("10.00"),
    "o1": Decimal("15.00"),
    "o1-mini": Decimal("3.00"),
    "claude-opus-4-5": Decimal("5.00"),
    "claude-opus-4-6": Decimal("5.00"),
    "claude-opus-4-7": Decimal("5.00"),
    "claude-opus-4-8": Decimal("5.00"),
    "claude-sonnet-4-5": Decimal("3.00"),
    "claude-sonnet-4-6": Decimal("3.00"),
    "claude-haiku-4-5": Decimal("1.00"),
    "claude-3-5-sonnet": Decimal("3.00"),
    "claude-3-5-haiku": Decimal("0.80"),
}

# Cache-read savings per million tokens = input_price - cache_read_price (0.1x input).
# Only models with published cache pricing are listed.
_CACHE_SAVINGS_PER_MTOK: dict[str, Decimal] = {
    "gpt-4o": Decimal("1.25"),                # 2.50 - 1.25
    "gpt-4o-mini": Decimal("0.075"),          # 0.15 - 0.075
    "claude-3-5-sonnet": Decimal("2.70"),     # 3.00 - 0.30
    "claude-3-5-haiku": Decimal("0.72"),      # 0.80 - 0.08
    "claude-opus-4-5": Decimal("4.50"),       # 5.00 - 0.50
    "claude-opus-4-6": Decimal("4.50"),
    "claude-opus-4-7": Decimal("4.50"),
    "claude-opus-4-8": Decimal("4.50"),
    "claude-sonnet-4-5": Decimal("2.70"),
    "claude-sonnet-4-6": Decimal("2.70"),
    "claude-haiku-4-5": Decimal("0.90"),      # 1.00 - 0.10
}

# Models eligible for OpenAI Batch API (50% discount, 24h turnaround).
_BATCH_ELIGIBLE: frozenset[str] = frozenset({"gpt-4o", "gpt-4o-mini"})

# Minimum projected savings to surface a recommendation (avoids noise).
_MIN_SAVINGS_USD = Decimal("1.00")


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ModelStats:
    """Aggregated 30-day stats for one (provider, model, feature_tag) group."""
    provider: str
    model: str
    feature_tag: str | None
    total_cost_usd: Decimal
    total_requests: int
    # total_tokens = input + output + cached (combined as stored in daily_cost_summaries)
    total_tokens: int


@dataclass
class Recommendation:
    type: Literal["model_swap", "caching", "batch", "other"]
    title: str
    description: str
    projected_savings_usd: Decimal | None
    confidence: Decimal  # 0.0–1.0
    evidence: dict
    # Deduplication key: used by the worker to skip re-inserting an existing open rec.
    scope_value: str


# ── Public entry point ────────────────────────────────────────────────────────

def generate_recommendations(stats: list[ModelStats]) -> list[Recommendation]:
    """
    Apply all rules and return recommendations sorted by projected savings descending.
    Empty stats list returns an empty list (no-op, not an error).
    """
    recs: list[Recommendation] = []
    recs.extend(_check_model_swap(stats))
    recs.extend(_check_caching_opportunity(stats))
    recs.extend(_check_batch_opportunity(stats))
    return sorted(recs, key=lambda r: r.projected_savings_usd or Decimal(0), reverse=True)


# ── Rule 1: model downgrade ───────────────────────────────────────────────────

def _check_model_swap(stats: list[ModelStats]) -> list[Recommendation]:
    """
    Trigger: avg cost/request > $0.01 AND ≥100 requests in 30 days AND a cheaper
    same-family model exists.

    Savings estimate uses the input-price ratio between models, applied to total cost.
    This overstates savings slightly (output tokens may have a different ratio) but
    is the right order of magnitude for a rule-based signal.
    """
    # Aggregate across feature_tags - the recommendation is per model family,
    # not per tag. Keying by family also folds dated ID variants together.
    by_model: dict[str, dict] = {}
    for s in stats:
        family = _model_family(s.model)
        if family not in by_model:
            by_model[family] = {
                "provider": s.provider,
                "total_cost_usd": Decimal(0),
                "total_requests": 0,
            }
        by_model[family]["total_cost_usd"] += s.total_cost_usd
        by_model[family]["total_requests"] += s.total_requests

    recs: list[Recommendation] = []
    for model, data in by_model.items():
        if data["total_requests"] < 100:
            continue

        avg_cost_per_req = data["total_cost_usd"] / data["total_requests"]
        if avg_cost_per_req <= Decimal("0.01"):
            continue

        cheaper = _MODEL_DOWNGRADE.get(model)
        if cheaper is None:
            continue

        current_price = _INPUT_PRICE_PER_MTOK.get(model)
        cheaper_price = _INPUT_PRICE_PER_MTOK.get(cheaper)
        if current_price is None or cheaper_price is None or current_price == 0:
            continue

        price_ratio = cheaper_price / current_price
        projected_savings = (data["total_cost_usd"] * (1 - price_ratio)).quantize(
            Decimal("0.01")
        )
        if projected_savings < _MIN_SAVINGS_USD:
            continue

        confidence = Decimal("0.85") if data["total_requests"] > 500 else Decimal("0.60")
        pct_cheaper = int((1 - float(price_ratio)) * 100)

        recs.append(
            Recommendation(
                type="model_swap",
                title=f"Switch {model} \u2192 {cheaper}",
                description=(
                    f"Your {model} workload averaged ${float(avg_cost_per_req):.4f}/request "
                    f"across {data['total_requests']:,} requests this month. "
                    f"{cheaper} is ~{pct_cheaper}% cheaper and handles classification, "
                    f"summarization, and structured extraction at comparable quality."
                ),
                projected_savings_usd=projected_savings,
                confidence=confidence,
                evidence={
                    "model": model,
                    "cheaper_model": cheaper,
                    "total_requests": data["total_requests"],
                    "avg_cost_per_request_usd": float(avg_cost_per_req),
                    "total_cost_usd_30d": float(data["total_cost_usd"]),
                    "price_ratio": float(price_ratio),
                },
                scope_value=model,
            )
        )
    return recs


# ── Rule 2: prompt caching ────────────────────────────────────────────────────

def _check_caching_opportunity(stats: list[ModelStats]) -> list[Recommendation]:
    """
    Trigger: model supports prompt caching AND ≥200 requests in 30 days.

    Savings estimate: 30% cache-hit rate on 70% of tokens (input fraction estimate).
    These are conservative defaults; real savings depend on prompt repetition patterns.
    """
    recs: list[Recommendation] = []
    for s in stats:
        family = _model_family(s.model)
        if family not in _CACHE_SAVINGS_PER_MTOK:
            continue
        if s.total_requests < 200:
            continue

        # Estimate input tokens as 70% of total (input >> output is typical for completions).
        est_input_tokens = int(s.total_tokens * 0.70)
        # Conservative: 30% of input tokens are repeated across requests and cacheable.
        cacheable_tokens = int(est_input_tokens * 0.30)
        savings_per_mtok = _CACHE_SAVINGS_PER_MTOK[family]
        projected_savings = (
            Decimal(cacheable_tokens) * savings_per_mtok / Decimal(1_000_000)
        ).quantize(Decimal("0.01"))

        if projected_savings < _MIN_SAVINGS_USD:
            continue

        tag_label = f" ({s.feature_tag})" if s.feature_tag else ""
        scope = f"{family}:{s.feature_tag or 'all'}"

        recs.append(
            Recommendation(
                type="caching",
                title=f"Enable prompt caching on {s.model}{tag_label}",
                description=(
                    f"You made {s.total_requests:,} requests to {s.model}{tag_label} this month. "
                    f"If your prompts share a repeated system prompt or context block, prompt "
                    f"caching cuts repeated input-token costs by 50\u201390%. "
                    f"Estimated at a 30% cache-hit rate."
                ),
                projected_savings_usd=projected_savings,
                confidence=Decimal("0.60"),
                evidence={
                    "model": s.model,
                    "feature_tag": s.feature_tag,
                    "total_requests": s.total_requests,
                    "estimated_input_tokens": est_input_tokens,
                    "estimated_cacheable_tokens": cacheable_tokens,
                    "savings_per_mtok_usd": float(savings_per_mtok),
                },
                scope_value=scope,
            )
        )
    return recs


# ── Rule 3: Batch API ─────────────────────────────────────────────────────────

def _check_batch_opportunity(stats: list[ModelStats]) -> list[Recommendation]:
    """
    Trigger: model is Batch-API eligible AND ≥500 requests AND avg tokens/request < 2000.

    OpenAI Batch API delivers a 50% cost reduction in exchange for ≤24h turnaround.
    Suitable for offline workloads: evals, bulk classification, data extraction pipelines.
    """
    # Aggregate across feature_tags - batch eligibility is per model, not per tag.
    by_model: dict[str, dict] = {}
    for s in stats:
        family = _model_family(s.model)
        if family not in _BATCH_ELIGIBLE:
            continue
        if family not in by_model:
            by_model[family] = {
                "total_cost_usd": Decimal(0),
                "total_requests": 0,
                "total_tokens": 0,
            }
        by_model[family]["total_cost_usd"] += s.total_cost_usd
        by_model[family]["total_requests"] += s.total_requests
        by_model[family]["total_tokens"] += s.total_tokens

    recs: list[Recommendation] = []
    for model, data in by_model.items():
        if data["total_requests"] < 500:
            continue

        avg_tokens = (
            data["total_tokens"] / data["total_requests"] if data["total_requests"] else 0
        )
        if avg_tokens >= 2000:
            continue

        projected_savings = (data["total_cost_usd"] * Decimal("0.50")).quantize(
            Decimal("0.01")
        )
        if projected_savings < _MIN_SAVINGS_USD:
            continue

        recs.append(
            Recommendation(
                type="batch",
                title=f"Use Batch API for {model}",
                description=(
                    f"You made {data['total_requests']:,} {model} requests averaging "
                    f"{avg_tokens:.0f} tokens/request. "
                    f"OpenAI\u2019s Batch API gives a 50% cost reduction for workloads that "
                    f"tolerate up-to-24h delivery \u2014 ideal for evals, bulk classification, "
                    f"or offline data processing."
                ),
                projected_savings_usd=projected_savings,
                confidence=Decimal("0.80"),
                evidence={
                    "model": model,
                    "total_requests": data["total_requests"],
                    "avg_tokens_per_request": float(avg_tokens),
                    "total_cost_usd_30d": float(data["total_cost_usd"]),
                },
                scope_value=model,
            )
        )
    return recs
