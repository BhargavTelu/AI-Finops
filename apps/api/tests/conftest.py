"""
Shared pytest fixtures.
Provider API calls are mocked at the httpx transport level - no real network.
"""

import pytest
from httpx import AsyncClient

from api.main import app


@pytest.fixture(autouse=True)
def _isolate_dependency_overrides():
    """
    Snapshot and restore app.dependency_overrides around every test.

    Several test modules install an auth override at import time and others
    pop it in finally blocks - whichever module ran last decided what the
    next module saw, making failures depend on file selection/order. This
    fixture makes any in-test mutation (set, del, pop) invisible to the
    next test.
    """
    saved = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


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
