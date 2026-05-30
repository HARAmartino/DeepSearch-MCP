"""Stealth HTTP fetcher using curl_cffi with TLS impersonation.

Key design choices:
- Primary impersonate is "chrome131" (best general compatibility). On a *block*
  (401/403) we rotate to a different fingerprint — some anti-bot setups block
  Chrome's TLS fingerprint but allow Safari's. Diagnosed 2026-05-30: Reuters
  returned 401 to chrome131/124/120 but 200 to safari17_0.
- AsyncSession is reused per-call (context manager) to avoid connection overhead.
- Exponential backoff with jitter on 429/5xx (per fingerprint).
- Rotation happens ONLY on block statuses (which don't retry → cheap). Genuine
  network errors are surfaced immediately, not multiplied across fingerprints.
"""

from __future__ import annotations

import asyncio
import os
import random
import re

from curl_cffi.requests import AsyncSession, Response

from .errors import BLOCKED_403, CONN_ERROR, RATE_LIMITED, TIMEOUT

_TIMEOUT = int(os.getenv("DEEPSEARCH_TIMEOUT", "10"))
_MAX_RETRIES = 3
# Tried in order; rotation triggered only by a 401/403 block. Chrome first
# (broadest compatibility), Safari as the anti-bot escape hatch.
_IMPERSONATE_TARGETS: tuple[str, ...] = ("chrome131", "safari17_0")
_IMPERSONATE = _IMPERSONATE_TARGETS[0]  # back-compat alias

_DEFAULT_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml"
        ";q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


async def fetch(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = _TIMEOUT,
) -> Response:
    """Fetch a URL with stealth settings. Retries transient errors; rotates the
    TLS fingerprint on a 401/403 block before giving up.

    Returns:
        curl_cffi Response object on success.

    Raises:
        FetchError: wraps the underlying error with a structured code.
    """
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    block_exc: FetchError | None = None

    for impersonate in _IMPERSONATE_TARGETS:
        try:
            return await _fetch_with_target(url, merged, timeout, impersonate)
        except FetchError as exc:
            if exc.code == BLOCKED_403:
                # This fingerprint is blocked; a different one may pass.
                block_exc = exc
                continue
            # Genuine network / rate-limit / timeout: don't multiply across
            # fingerprints — surface immediately.
            raise

    # Every fingerprint was blocked.
    assert block_exc is not None
    raise block_exc


async def _fetch_with_target(
    url: str, headers: dict[str, str], timeout: int, impersonate: str
) -> Response:
    """One impersonate target: retries transient errors with backoff."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            delay = (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
            await asyncio.sleep(delay)

        try:
            async with AsyncSession(impersonate=impersonate) as session:
                resp = await session.get(
                    url, headers=headers, timeout=timeout, allow_redirects=True
                )

            if resp.status_code == 200:
                return resp

            # 401 and 403 are anti-bot blocks → BLOCKED_403 (triggers fingerprint
            # rotation in the caller). Previously 401 mis-mapped to CONN_ERROR.
            if resp.status_code in (401, 403):
                raise FetchError(
                    BLOCKED_403, f"HTTP {resp.status_code} for {url}", retryable=False
                )

            if resp.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES - 1:
                last_exc = FetchError(
                    RATE_LIMITED if resp.status_code == 429 else CONN_ERROR,
                    f"HTTP {resp.status_code} for {url}",
                    retryable=True,
                )
                continue

            raise FetchError(
                RATE_LIMITED if resp.status_code == 429 else CONN_ERROR,
                f"HTTP {resp.status_code} for {url}",
                retryable=resp.status_code in _RETRYABLE_STATUSES,
            )

        except FetchError:
            raise
        except TimeoutError as exc:
            if attempt < _MAX_RETRIES - 1:
                last_exc = exc
                continue
            raise FetchError(TIMEOUT, f"Timeout after {timeout}s fetching {url}") from exc
        except Exception as exc:
            err_msg = str(exc)
            if attempt < _MAX_RETRIES - 1 and _is_transient(err_msg):
                last_exc = exc
                continue
            raise FetchError(CONN_ERROR, f"Connection error fetching {url}: {err_msg}") from exc

    raise FetchError(CONN_ERROR, f"All {_MAX_RETRIES} attempts failed for {url}") from last_exc


def _is_transient(message: str) -> bool:
    keywords = ("connection reset", "connection refused", "eof", "ssl", "timeout")
    return any(k in message.lower() for k in keywords)


# ---------------------------------------------------------------------------
# Charset-aware decoding (B20)
# ---------------------------------------------------------------------------
# curl_cffi defaults `.text` to utf-8 when the HTTP header omits a charset, so
# a Shift_JIS / EUC-JP page (common on Japanese government & legacy sites)
# decodes to mojibake. Diagnosed 2026-05-30 on soumu.go.jp: header had no
# charset, `<meta charset="Shift_JIS">` was the truth. Decode from raw bytes,
# detecting the charset: HTTP header → <meta> → detector → utf-8.

_HEADER_CHARSET_RE = re.compile(r"charset=([\w\-]+)", re.I)
_META_CHARSET_RE = re.compile(rb"""charset=["']?\s*([\w\-]+)""", re.I)


def _normalize_charset(enc: str) -> str:
    e = enc.strip().strip("\"'").lower()
    if e in ("shift_jis", "shift-jis", "sjis", "x-sjis", "shiftjis"):
        return "cp932"  # cp932 is a tolerant superset of Shift_JIS
    return e


def _detect_charset(raw: bytes) -> str | None:
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        return best.encoding if best else None
    except Exception:
        return None


def decode_html(resp: Response) -> str:
    """Decode a response body to text using the *declared* charset.

    Priority: HTTP `Content-Type` charset → HTML `<meta charset>` → detector →
    utf-8. Defensive: if `.content` is not bytes (e.g. a test mock), fall back
    to `resp.text`.
    """
    raw = getattr(resp, "content", None)
    if not isinstance(raw, (bytes, bytearray)):
        return resp.text
    if not raw:
        return ""

    enc: str | None = None
    try:
        ctype = resp.headers.get("content-type", "") or ""
    except Exception:
        ctype = ""
    m = _HEADER_CHARSET_RE.search(ctype)
    if m:
        enc = m.group(1)
    if not enc:
        mm = _META_CHARSET_RE.search(raw[:4096])
        if mm:
            enc = mm.group(1).decode("ascii", "ignore")
    if not enc:
        enc = _detect_charset(raw)

    enc = _normalize_charset(enc) if enc else "utf-8"
    try:
        return bytes(raw).decode(enc, errors="replace")
    except LookupError:
        return bytes(raw).decode("utf-8", errors="replace")


class FetchError(Exception):
    """Wraps an HTTP/network error with a structured error code."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
