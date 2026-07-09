"""
Pricing calculation tests using pricing.yaml.
TC-PRI-01 to TC-PRI-05.
Replaces the placeholder in test_pricing.py.
"""

from decimal import Decimal
from pathlib import Path

import yaml

_PRICING_PATH = Path(__file__).parents[3] / "packages" / "pricing" / "pricing.yaml"

_REQUIRED_RATE_KEYS = {"input_per_mtok", "output_per_mtok", "cached_per_mtok"}


def _load_pricing() -> dict:
    with open(_PRICING_PATH) as f:
        return yaml.safe_load(f)


class TestPricingYaml:
    def test_yaml_parses_correctly(self) -> None:  # TC-PRI-01
        data = _load_pricing()
        assert "providers" in data
        providers = data["providers"]
        assert "openai" in providers
        assert "anthropic" in providers
        assert "gemini" in providers

    def test_all_models_have_three_rate_keys(self) -> None:  # TC-PRI-02
        data = _load_pricing()
        for provider, pdata in data["providers"].items():
            for model, rates in pdata["models"].items():
                missing = _REQUIRED_RATE_KEYS - set(rates.keys())
                assert not missing, f"{provider}/{model} missing rate keys: {missing}"

    def test_no_zero_rates(self) -> None:  # TC-PRI-03
        data = _load_pricing()
        for provider, pdata in data["providers"].items():
            for model, rates in pdata["models"].items():
                for key in _REQUIRED_RATE_KEYS:
                    assert rates[key] > 0, f"{provider}/{model}.{key} = {rates[key]} (must be > 0)"

    def test_claude_sonnet_cost_calc(self) -> None:  # TC-PRI-04
        """1M input + 1M output tokens for claude-sonnet-4-5 = $18.00."""
        from api.adapters.anthropic import _compute_cost

        cost = _compute_cost(
            model="claude-sonnet-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cached_tokens=0,
        )
        assert cost == Decimal("18.0"), f"Expected $18.00, got ${cost}"

    def test_cached_tokens_cheaper_than_input(self) -> None:  # TC-PRI-05
        data = _load_pricing()
        rates = data["providers"]["anthropic"]["models"]["claude-sonnet-4-5"]
        assert rates["cached_per_mtok"] < rates["input_per_mtok"], (
            f"cached_per_mtok ({rates['cached_per_mtok']}) should be < "
            f"input_per_mtok ({rates['input_per_mtok']})"
        )


# ── TC-PRI-10 + TC-PRI-11: pricing.yaml ↔ recommendations sync ───────────────


class TestPricingYamlRecommendationsSync:
    """
    TC-PRI-10 / TC-PRI-11 (HIGH) - Enforce sync between pricing.yaml and the
    hardcoded price maps in services/recommendations.py.

    If pricing.yaml is updated but _INPUT_PRICE_PER_MTOK / _CACHE_SAVINGS_PER_MTOK
    are not, these tests catch the drift (BUG-04 prevention).
    """

    def _yaml_prices(self) -> dict[str, dict]:
        """Build {model: {input_per_mtok, cached_per_mtok}} from all providers in the YAML."""
        data = _load_pricing()
        prices: dict[str, dict] = {}
        for provider_data in data["providers"].values():
            for model, rates in provider_data["models"].items():
                prices[model] = rates
        return prices

    def test_input_price_map_matches_yaml(self) -> None:  # TC-PRI-10
        """TC-PRI-10 - _INPUT_PRICE_PER_MTOK values match input_per_mtok in pricing.yaml."""
        from api.services.recommendations import _INPUT_PRICE_PER_MTOK

        yaml_prices = self._yaml_prices()

        for model, rec_price in _INPUT_PRICE_PER_MTOK.items():
            assert model in yaml_prices, (
                f"Model '{model}' is in _INPUT_PRICE_PER_MTOK but missing from pricing.yaml. "
                "Add it to pricing.yaml or remove it from the recommendations map."
            )
            yaml_input = Decimal(str(yaml_prices[model]["input_per_mtok"]))
            assert rec_price == yaml_input, (
                f"_INPUT_PRICE_PER_MTOK['{model}'] = {rec_price} but pricing.yaml has "
                f"input_per_mtok = {yaml_input}. Update both maps together (BUG-04)."
            )

    def test_cache_savings_map_matches_yaml(self) -> None:  # TC-PRI-11
        """TC-PRI-11 - _CACHE_SAVINGS_PER_MTOK equals (input - cached) from pricing.yaml."""
        from api.services.recommendations import _CACHE_SAVINGS_PER_MTOK

        yaml_prices = self._yaml_prices()

        for model, rec_savings in _CACHE_SAVINGS_PER_MTOK.items():
            assert (
                model in yaml_prices
            ), f"Model '{model}' is in _CACHE_SAVINGS_PER_MTOK but missing from pricing.yaml."
            rates = yaml_prices[model]
            yaml_savings = Decimal(str(rates["input_per_mtok"])) - Decimal(
                str(rates["cached_per_mtok"])
            )
            assert rec_savings == yaml_savings, (
                f"_CACHE_SAVINGS_PER_MTOK['{model}'] = {rec_savings} but "
                f"pricing.yaml implies {yaml_savings} (input - cached). "
                "Update both maps together (BUG-04)."
            )
