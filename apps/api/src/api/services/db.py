"""
Process-wide Supabase client.

Every router used to call create_client() per request, which sets up a fresh
HTTP connection pool each time and is pure overhead - the service-role client
carries no per-request state. supabase-py's sync client wraps httpx.Client,
which is thread-safe, so one shared instance serves the whole process.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from api.config import settings

_PAGE_SIZE = 1000


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def fetch_all_pages(
    build_query: Callable[[], Any], page_size: int = _PAGE_SIZE
) -> list[dict[str, Any]]:
    """
    Exhaust a PostgREST query past the server's max-rows cap.

    Supabase silently truncates any unpaged select at its max-rows setting
    (default 1000), so summing or grouping over a single .execute() gives
    wrong answers once an org's rows exceed one page. Takes a zero-arg
    callable that builds a fresh filtered query; ordering by primary key
    makes offset pagination deterministic (same fix as aggregate_org).
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        result = (
            build_query().order("id", desc=False).range(offset, offset + page_size - 1).execute()
        )
        rows.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return rows
