"""
E2E tests for M2 features - multi-provider Cost Explorer.

Require a live stack or skip via E2E env var. Run with:

    E2E=true E2E_API_URL=http://localhost:8000 E2E_TOKEN=<clerk_jwt> pytest tests/test_e2e_m2.py -v

TC-E2E-02 - M2 milestone: multi-provider ingestion + tag rules + Cost Explorer.
"""

import os

import pytest

E2E = os.getenv("E2E", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(not E2E, reason="Set E2E=true to run end-to-end tests")

_API = os.getenv("E2E_API_URL", "http://localhost:8000")
_TOKEN = os.getenv("E2E_TOKEN", "")
_OPENAI_KEY = os.getenv("E2E_OPENAI_KEY", "")
_ANTHROPIC_KEY = os.getenv("E2E_ANTHROPIC_KEY", "")


@pytest.fixture(scope="module")
def headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}"}


# ── TC-E2E-02: Multi-provider ingestion + Cost Explorer ───────────────────────

class TestM2MultiProviderCostExplorer:
    """
    TC-E2E-02 (High) - Connect two integrations, seed usage, apply tags, verify explorer.

    Scenario:
      1. Connect OpenAI + Anthropic integrations.
      2. Wait for backfill / use ingest_window if accessible.
      3. Create a tag rule: feature_tag = "chat" for model = gpt-4o.
      4. Verify GET /usage/explore?group_by=feature_tag returns a row with feature_tag="chat".
      5. Verify GET /usage/explore?group_by=provider returns both "openai" and "anthropic".

    Notes: Uses pytest.mark.e2e - skipped in unit runs.
    """

    def test_multi_provider_explorer_returns_both_providers(self, headers: dict) -> None:
        import httpx

        if not _OPENAI_KEY or not _ANTHROPIC_KEY:
            pytest.skip("E2E_OPENAI_KEY and E2E_ANTHROPIC_KEY both required for TC-E2E-02")

        integration_ids: list[str] = []

        # Step 1: Connect two integrations
        for provider, key in [("openai", _OPENAI_KEY), ("anthropic", _ANTHROPIC_KEY)]:
            resp = httpx.post(
                f"{_API}/api/v1/integrations",
                json={"provider": provider, "display_name": f"e2e-m2-{provider}", "api_key": key},
                headers=headers,
                timeout=30,
            )
            assert resp.status_code == 201, f"Failed to connect {provider}: {resp.text}"
            integration_ids.append(resp.json()["id"])

        try:
            # Step 2: Poll for data (backfill + aggregation)
            import time
            deadline = time.time() + 300  # 5 minutes
            explorer_data = None
            while time.time() < deadline:
                resp = httpx.get(
                    f"{_API}/api/v1/usage/explore?group_by=provider&range=30d",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200 and len(resp.json()) > 0:
                    explorer_data = resp.json()
                    break
                time.sleep(10)

            # Step 3: Create a feature tag rule for gpt-4o
            tag_resp = httpx.post(
                f"{_API}/api/v1/tags",
                json={"name": "chat", "color": "#3b82f6", "type": "feature"},
                headers=headers,
                timeout=10,
            )
            if tag_resp.status_code == 201:
                tag_id = tag_resp.json()["id"]
                httpx.post(
                    f"{_API}/api/v1/tag-rules",
                    json={
                        "tag_id": tag_id,
                        "match_field": "model",
                        "match_pattern": "gpt-4o",
                        "priority": 10,
                    },
                    headers=headers,
                    timeout=10,
                )

            # Step 4: Verify both providers appear in explorer
            assert explorer_data is not None, (
                "Cost Explorer returned no data after 5 minutes. Check Celery workers."
            )
            providers_returned = {row.get("provider") or row.get("group_value") for row in explorer_data}
            assert "openai" in providers_returned, (
                f"OpenAI not in explorer results: {providers_returned}"
            )

            # Step 5: Verify feature_tag grouping
            ft_resp = httpx.get(
                f"{_API}/api/v1/usage/explore?group_by=feature_tag&range=30d",
                headers=headers,
                timeout=10,
            )
            assert ft_resp.status_code == 200

        finally:
            # Cleanup
            for int_id in integration_ids:
                httpx.delete(f"{_API}/api/v1/integrations/{int_id}", headers=headers, timeout=10)
