"""
Process-wide Supabase client.

Every router used to call create_client() per request, which sets up a fresh
HTTP connection pool each time and is pure overhead - the service-role client
carries no per-request state. supabase-py's sync client wraps httpx.Client,
which is thread-safe, so one shared instance serves the whole process.
"""

from functools import lru_cache

from supabase import Client, create_client

from api.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
