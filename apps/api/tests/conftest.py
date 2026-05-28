"""
Shared pytest fixtures.
Provider API calls are mocked at the httpx transport level - no real network.
"""

import pytest
from httpx import AsyncClient

from api.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async test client for FastAPI. Yields once per test."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_org_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_user_id() -> str:
    return "user_test_00000000"
