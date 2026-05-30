"""Custom exceptions and structured error response helpers.

All public functions return JSON strings — never raise exceptions to MCP clients.

Phase 5 changes (Persona A FRICTION-B1/B2/B3):
- `sanitize_error_text` strips raw URLs and noisy backend paths from messages
  so the LLM does not waste tokens parsing /search?q=... query strings.
- `structured_error` accepts `hint_override` / `retryable_override` so a caller
  (e.g. search_web vs read_article) can substitute a tool-specific hint —
  the same error code can mean different things in different contexts.
- `is_transient_conn_error` detects DNS / timeout / reset patterns and
  flips `retryable` to True so the agent doesn't give up on flaky networks.
"""

from __future__ import annotations

import json
import re

from .models import StructuredError

# Error code constants
BLOCKED_403 = "BLOCKED_403"
RATE_LIMITED = "RATE_LIMITED"
TIMEOUT = "TIMEOUT"
EMPTY_CONTENT = "EMPTY_CONTENT"
CONN_ERROR = "CONN_ERROR"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"

_HINTS: dict[str, tuple[str, bool]] = {
    BLOCKED_403: (
        "Access denied. The site likely has anti-bot protection. Try a different source.",
        False,
    ),
    RATE_LIMITED: (
        "Rate limit reached. Wait 60s before retrying, or refine the query.",
        True,
    ),
    TIMEOUT: (
        "Endpoint is unresponsive. Skip this target and try another.",
        False,
    ),
    EMPTY_CONTENT: (
        "Could not extract main content (maybe PDF, dynamic SPA, or login-wall). Skip this URL.",
        False,
    ),
    CONN_ERROR: (
        "Connection failed. Retry once; if it persists, try a different approach.",
        False,
    ),
    UNSUPPORTED_FORMAT: (
        "URL points to a non-HTML resource (PDF, image, archive, etc.). "
        "Skip this URL and search for an HTML alternative.",
        False,
    ),
}

# ---------------------------------------------------------------------------
# Sanitization (FRICTION-B1)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_MAX_MSG_LEN = 200


def sanitize_error_text(text: str) -> str:
    """Strip raw URLs, control chars, and over-long internals from an error message.

    Keeps the message under ~200 chars so the LLM can scan it in one glance.
    """
    if not text:
        return ""
    cleaned = _URL_RE.sub("[REDACTED_URL]", text)
    cleaned = _CONTROL_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > _MAX_MSG_LEN:
        cleaned = cleaned[: _MAX_MSG_LEN - 1].rstrip() + "…"
    return cleaned


# ---------------------------------------------------------------------------
# Transient network error detection (FRICTION-B3)
# ---------------------------------------------------------------------------

_TRANSIENT_KEYWORDS = (
    "dns",
    "name resolution",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "eof",
    "broken pipe",
    "network is unreachable",
)


def is_transient_conn_error(message: str) -> bool:
    """Return True if the message describes a typically-transient network failure.

    These should be flagged `retryable=True` so the agent retries after a delay
    instead of abandoning the source forever.
    """
    if not message:
        return False
    lower = message.lower()
    return any(kw in lower for kw in _TRANSIENT_KEYWORDS)


# ---------------------------------------------------------------------------
# Structured error builders
# ---------------------------------------------------------------------------

def structured_error(
    code: str,
    message: str,
    hint_override: str | None = None,
    retryable_override: bool | None = None,
) -> str:
    """Return a JSON-encoded StructuredError string safe to return from any MCP tool.

    Parameters
    ----------
    code
        Machine-readable error code (one of the module-level constants).
    message
        Human-/LLM-readable message. Will be sanitized to strip raw URLs and
        truncated to ~200 chars. Pass already-sanitized text if you want to
        preserve formatting.
    hint_override
        Tool-specific hint that replaces the default for this code. Use when
        the same error code carries different recovery advice per call site
        (e.g. CONN_ERROR from search_web vs CONN_ERROR from read_article).
    retryable_override
        Tool-specific retryable flag that replaces the default. Use for
        transient errors (DNS / timeout) where the default retryable=False
        would cause the agent to give up too early.
    """
    default_hint, default_retryable = _HINTS.get(
        code, ("Unexpected error. Try a different approach.", False)
    )
    hint = hint_override if hint_override is not None else default_hint
    retryable = retryable_override if retryable_override is not None else default_retryable

    err = StructuredError(
        code=code,
        message=sanitize_error_text(message),
        hint=hint,
        retryable=retryable,
    )
    return json.dumps(err.model_dump())


def from_http_status(status: int, url: str) -> str:
    if status == 403:
        return structured_error(BLOCKED_403, f"HTTP 403 Forbidden for url: {url}")
    if status == 429:
        return structured_error(RATE_LIMITED, f"HTTP 429 Too Many Requests for url: {url}")
    if status in (500, 502, 503, 504):
        return structured_error(
            CONN_ERROR, f"HTTP {status} server error for url: {url}"
        )
    return structured_error(CONN_ERROR, f"HTTP {status} unexpected status for url: {url}")
