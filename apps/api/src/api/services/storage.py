"""
Cloudflare R2 object storage via the S3-compatible API.

Hand-rolled AWS Signature V4 over httpx instead of boto3: boto3+botocore is
~80MB and we need exactly two operations (PUT object, presigned GET). R2 uses
region "auto" and path-style URLs: https://{account}.r2.cloudflarestorage.com/{bucket}/{key}.

`now` is injectable for deterministic signature tests.
"""

from datetime import UTC, datetime
import hashlib
import hmac
from urllib.parse import quote

import httpx
import structlog

from api.config import settings

log = structlog.get_logger()

_REGION = "auto"
_SERVICE = "s3"
_ALGORITHM = "AWS4-HMAC-SHA256"


def is_configured() -> bool:
    return bool(
        settings.r2_account_id
        and settings.r2_bucket_name
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
    )


def _host() -> str:
    return f"{settings.r2_account_id}.r2.cloudflarestorage.com"


def _canonical_uri(key: str) -> str:
    # Each path segment percent-encoded, slashes preserved (SigV4 spec).
    return quote(f"/{settings.r2_bucket_name}/{key}", safe="/-_.~")


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(date_stamp: str) -> bytes:
    k_date = _hmac_sha256(f"AWS4{settings.r2_secret_access_key}".encode(), date_stamp)
    k_region = _hmac_sha256(k_date, _REGION)
    k_service = _hmac_sha256(k_region, _SERVICE)
    return _hmac_sha256(k_service, "aws4_request")


def _scope(date_stamp: str) -> str:
    return f"{date_stamp}/{_REGION}/{_SERVICE}/aws4_request"


def _string_to_sign(amz_date: str, date_stamp: str, canonical_request: str) -> str:
    return "\n".join(
        [
            _ALGORITHM,
            amz_date,
            _scope(date_stamp),
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )


def upload_pdf(key: str, body: bytes, *, now: datetime | None = None) -> None:
    """PUT the PDF to R2. Raises ValueError on any failure so Celery can retry."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    canonical_headers = (
        "content-type:application/pdf\n"
        f"host:{_host()}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["PUT", _canonical_uri(key), "", canonical_headers, signed_headers, payload_hash]
    )
    signature = hmac.new(
        _signing_key(date_stamp),
        _string_to_sign(amz_date, date_stamp, canonical_request).encode(),
        hashlib.sha256,
    ).hexdigest()

    authorization = (
        f"{_ALGORITHM} Credential={settings.r2_access_key_id}/{_scope(date_stamp)}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"https://{_host()}{_canonical_uri(key)}"
    try:
        resp = httpx.put(
            url,
            content=body,
            headers={
                "Authorization": authorization,
                "Content-Type": "application/pdf",
                "x-amz-content-sha256": payload_hash,
                "x-amz-date": amz_date,
            },
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise ValueError(f"R2 upload network error: {exc}") from exc
    if resp.status_code not in (200, 201):
        raise ValueError(f"R2 upload failed with status {resp.status_code}")
    log.info("r2_upload_ok", key=key, size_bytes=len(body))


def presign_download(key: str, expires_seconds: int = 600, *, now: datetime | None = None) -> str:
    """Return a presigned GET URL. Signature covers only the host header."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Query params must be sorted by name for the canonical request.
    params = [
        ("X-Amz-Algorithm", _ALGORITHM),
        ("X-Amz-Credential", f"{settings.r2_access_key_id}/{_scope(date_stamp)}"),
        ("X-Amz-Date", amz_date),
        ("X-Amz-Expires", str(expires_seconds)),
        ("X-Amz-SignedHeaders", "host"),
    ]
    canonical_query = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in params)
    canonical_request = "\n".join(
        [
            "GET",
            _canonical_uri(key),
            canonical_query,
            f"host:{_host()}\n",
            "host",
            "UNSIGNED-PAYLOAD",
        ]
    )
    signature = hmac.new(
        _signing_key(date_stamp),
        _string_to_sign(amz_date, date_stamp, canonical_request).encode(),
        hashlib.sha256,
    ).hexdigest()

    return (
        f"https://{_host()}{_canonical_uri(key)}" f"?{canonical_query}&X-Amz-Signature={signature}"
    )
