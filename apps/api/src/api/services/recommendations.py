"""
Rule-based recommendations engine (V1 — no AI).
AI-generated recommendations deferred to after 30 days of org data (V1 debt).

Rules applied in order:
  1. model_swap  — expensive model used for tasks where a cheaper one fits
  2. caching     — identical prompts detected via token pattern analysis
  3. batch       — high request volume at low tokens/request ratio
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass
class Recommendation:
    type: Literal["model_swap", "caching", "batch", "other"]
    title: str
    description: str
    projected_savings_usd: Decimal | None
    confidence: Decimal  # 0.0–1.0
    evidence: dict


def generate_recommendations(
    # Daily cost summaries grouped by model, 30 days
    model_costs: dict[str, list[Decimal]],
) -> list[Recommendation]:
    """
    Apply rule-based heuristics and return ranked recommendations.
    All rules are stateless and testable in isolation.
    """
    recs: list[Recommendation] = []
    recs.extend(_check_model_swap(model_costs))
    recs.extend(_check_caching_opportunity(model_costs))
    recs.extend(_check_batch_opportunity(model_costs))
    return sorted(recs, key=lambda r: r.projected_savings_usd or Decimal(0), reverse=True)


def _check_model_swap(model_costs: dict[str, list[Decimal]]) -> list[Recommendation]:
    raise NotImplementedError


def _check_caching_opportunity(model_costs: dict[str, list[Decimal]]) -> list[Recommendation]:
    raise NotImplementedError


def _check_batch_opportunity(model_costs: dict[str, list[Decimal]]) -> list[Recommendation]:
    raise NotImplementedError
