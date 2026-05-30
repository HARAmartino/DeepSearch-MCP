"""SQLite-backed telemetry for MCP tool calls.

Day 2 Operations (Phase 6) requires observability so that production usage
patterns can drive automated improvements (failing domains → domain adapters,
high-token outputs → noise filters, etc.).

Design constraints
------------------
1. **Zero impact on tool latency.** All DB writes happen via
   `asyncio.create_task(_write_event(...))` — the tool returns before the
   write completes. Failures during write are swallowed silently so a
   telemetry outage cannot break a live agent loop.

2. **Per-process schema bootstrap.** The table/indices are created lazily on
   first write and cached in `_initialized`. Connections are opened per-write
   (aiosqlite is not safely sharable across coroutines).

3. **Environment-gated.** Set `DEEPSEARCH_TELEMETRY=0` to disable entirely
   (default for `tests/conftest.py`). Use `DEEPSEARCH_TELEMETRY_DIR` to
   redirect the DB during one-off analysis runs.

4. **No PII.** `input_summary` is truncated to 80 chars and replaces the
   sensitive tail with a `sha1[:8]` digest when longer — long enough to group
   identical calls but short enough not to log the entire query string.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiosqlite

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DIR = "./.cache"
_DB_FILENAME = "telemetry.db"


def is_enabled() -> bool:
    """Telemetry is on unless DEEPSEARCH_TELEMETRY=0."""
    return os.getenv("DEEPSEARCH_TELEMETRY", "1") != "0"


def get_db_path() -> Path:
    """Resolve the DB path at call time so tests can override via env var."""
    dirpath = Path(os.getenv("DEEPSEARCH_TELEMETRY_DIR", _DEFAULT_DIR))
    return dirpath / _DB_FILENAME


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS telemetry (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,
    tool_name     TEXT    NOT NULL,
    input_summary TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    tokens_approx INTEGER NOT NULL,
    latency_ms    INTEGER NOT NULL,
    domain        TEXT
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tool_time ON telemetry(tool_name, timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_status     ON telemetry(status);",
    "CREATE INDEX IF NOT EXISTS idx_domain     ON telemetry(domain);",
]

# Cache the (db_path, initialized) tuple so we re-init when path changes.
_initialized_for: Path | None = None

# Strong references to pending fire-and-forget writes.
# Without this, asyncio may GC the Task before it runs (PEP 3156 caveat).
# Also serves as the queue `drain()` awaits in tests.
_pending_tasks: set[asyncio.Task] = set()


async def _ensure_schema(db_path: Path) -> None:
    global _initialized_for
    if _initialized_for == db_path:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(_CREATE_TABLE)
        for ix in _INDEXES:
            await db.execute(ix)
        await db.commit()
    _initialized_for = db_path


# ---------------------------------------------------------------------------
# Event recording
# ---------------------------------------------------------------------------

async def _write_event(row: tuple) -> None:
    """Fire-and-forget DB insert. All exceptions are suppressed."""
    try:
        db_path = get_db_path()
        await _ensure_schema(db_path)
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute(
                "INSERT INTO telemetry "
                "(timestamp, tool_name, input_summary, status, "
                " tokens_approx, latency_ms, domain) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            await db.commit()
    except Exception:
        # Telemetry NEVER fails the tool path.
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUMMARY_MAX = 80


def summarize_input(value: Any) -> str:
    """Truncate long inputs and append a stable sha1 fingerprint."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if len(s) <= _SUMMARY_MAX:
        return s
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
    return f"{s[: _SUMMARY_MAX - 11]}…[{digest}]"


def domain_from_url(url: str) -> str | None:
    """Lower-cased hostname or None."""
    if not url:
        return None
    try:
        host = urlparse(url).hostname
        return host.lower() if host else None
    except Exception:
        return None


def parse_status(result: str) -> str:
    """A structured-error JSON → its `code`; anything else → 'success'."""
    if not result:
        return "success"
    try:
        data = json.loads(result)
        if isinstance(data, dict) and data.get("status") == "error":
            return data.get("code", "ERROR")
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return "success"


def iso_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def track(
    tool_name: str,
    primary_input: str,
) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    """Decorator that records a telemetry row each time `fn` is awaited.

    Parameters
    ----------
    tool_name
        Stored in `telemetry.tool_name` (e.g. "search_web").
    primary_input
        Name of the kwarg used to summarize the call. For URL-taking tools
        ("url") the hostname is also stored in the `domain` column.
        Falls back to the first positional argument if the kwarg is absent.
    """

    def deco(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            if not is_enabled():
                return await fn(*args, **kwargs)

            t0 = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                # If the tool itself raises, telemetry can't capture the body —
                # let the exception propagate (the tool layer is the one that
                # promised "never raise to MCP").
                raise
            latency_ms = int((time.perf_counter() - t0) * 1000)

            input_val = kwargs.get(primary_input, "")
            if not input_val and args:
                input_val = args[0]
            summary = summarize_input(input_val)
            domain = domain_from_url(str(input_val)) if primary_input == "url" else None
            status = parse_status(result)
            tokens = (len(result) // 4) if result else 0

            row = (
                iso_timestamp(),
                tool_name,
                summary,
                status,
                tokens,
                latency_ms,
                domain,
            )
            # Fire and forget — does not block tool return. The task is held
            # in _pending_tasks so the GC cannot collect it before it runs.
            try:
                task = asyncio.create_task(_write_event(row))
                _pending_tasks.add(task)
                task.add_done_callback(_pending_tasks.discard)
            except RuntimeError:
                # No running loop (rare; e.g. tool called sync-style). Skip.
                pass

            return result

        return wrapper

    return deco


# ---------------------------------------------------------------------------
# Maintenance helpers (used by analyze script + tests)
# ---------------------------------------------------------------------------

async def drain() -> None:
    """Wait for all pending fire-and-forget writes to complete.

    Test helper — production code never needs this; the OS process exit
    cleans up gracefully because tasks are stored in a strong-ref set.
    """
    if _pending_tasks:
        await asyncio.gather(*list(_pending_tasks), return_exceptions=True)


async def reset_for_tests() -> None:
    """Drop and recreate the table. ONLY for test/dev use."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("DROP TABLE IF EXISTS telemetry;")
        await db.execute(_CREATE_TABLE)
        for ix in _INDEXES:
            await db.execute(ix)
        await db.commit()
    global _initialized_for
    _initialized_for = db_path
