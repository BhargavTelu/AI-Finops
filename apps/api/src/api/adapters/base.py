from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass
class NormalizedUsageEvent:
    """
    Provider-agnostic usage record.
    One row per (model, api_key_label, bucket_hour) after normalization.
    """

    provider: Literal["openai", "anthropic", "gemini"]
    model: str
    api_key_label: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: Decimal
    request_count: int
    bucket_hour: datetime  # floored to UTC hour
    raw_meta: dict[str, Any]


@runtime_checkable
class UsageAdapter(Protocol):
    """
    Implement one file per provider. See adapters/openai.py for the reference.
    Each adapter is stateless - encryption/decryption happens in the caller.
    """

    provider: str

    def validate(self, key: bytes) -> bool:
        """
        Make a cheap API call to confirm the key is valid.
        Raises ValueError with a human-readable message if invalid.
        """
        ...

    def fetch_costs(
        self,
        key: bytes,
        start: datetime,
        end: datetime,
    ) -> Iterator[NormalizedUsageEvent]:
        """
        Page through provider cost/usage data and yield normalized events.
        key is the raw (decrypted) Admin API key bytes.
        """
        ...
