"""Async SQLite cache for search results and article content.

Uses aiosqlite for non-blocking I/O. Schema per SPEC.md Section 6.

TTLs:
  - Search results: 24 h (prevents hammering DDG in ReAct loops)
  - Article content: 7 days (pages rarely change)

aiosqlite usage: always open with `async with aiosqlite.connect(...) as db`
per call — do NOT share connections across coroutines (thread-safety issue).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import aiosqlite

_CACHE_DIR = Path(os.getenv("DEEPSEARCH_CACHE_DIR", "./.cache"))
_DB_PATH = _CACHE_DIR / "cache.db"

TTL_SEARCH = 86_400      # 24 hours
TTL_ARTICLE = 604_800    # 7 days

_CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS cache ("
    "key TEXT PRIMARY KEY, "
    "value TEXT NOT NULL, "
    "timestamp INTEGER NOT NULL, "
    "ttl INTEGER NOT NULL"
    ");"
)
_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_cache_ts ON cache(timestamp);"
)

# Lazy init flag per process (schema is idempotent, but avoid re-running every call)
_db_initialized = False


async def _open_db() -> aiosqlite.Connection:
    """Open the DB and ensure schema exists. Caller must use `async with`."""
    global _db_initialized
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(_DB_PATH))
    if not _db_initialized:
        await db.execute(_CREATE_TABLE)
        await db.execute(_CREATE_INDEX)
        await db.commit()
        _db_initialized = True
    return db


def make_search_key(
    query: str,
    region: str | None,
    safesearch: str,
    timelimit: str | None,
) -> str:
    """Stable cache key for a search request (sha256 of params)."""
    raw = f"{query}|{region or ''}|{safesearch}|{timelimit or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_article_key(url: str) -> str:
    """Stable cache key for an article URL (sha256 of URL)."""
    return hashlib.sha256(url.encode()).hexdigest()


async def cache_get(key: str) -> str | None:
    """Return cached value if present and not expired; else None."""
    db = await _open_db()
    try:
        async with db.execute(
            "SELECT value, timestamp, ttl FROM cache WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
    finally:
        await db.close()

    if row is None:
        return None

    value, timestamp, ttl = row
    if (int(time.time()) - timestamp) >= ttl:
        await cache_delete(key)
        return None

    return value


async def cache_set(key: str, value: str, ttl: int) -> None:
    """Store value with a TTL (seconds). Overwrites existing entry."""
    db = await _open_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO cache (key, value, timestamp, ttl) "
            "VALUES (?, ?, ?, ?)",
            (key, value, int(time.time()), ttl),
        )
        await db.commit()
    finally:
        await db.close()


async def cache_delete(key: str) -> None:
    """Remove a single cache entry."""
    db = await _open_db()
    try:
        await db.execute("DELETE FROM cache WHERE key = ?", (key,))
        await db.commit()
    finally:
        await db.close()


async def cache_purge_expired() -> int:
    """Delete all expired entries. Returns count of deleted rows."""
    cutoff = int(time.time())
    db = await _open_db()
    try:
        cursor = await db.execute(
            "DELETE FROM cache WHERE (? - timestamp) >= ttl", (cutoff,)
        )
        await db.commit()
        return cursor.rowcount
    finally:
        await db.close()


async def cache_get_json(key: str) -> Any | None:
    """Convenience: get and JSON-decode a cached value."""
    raw = await cache_get(key)
    return json.loads(raw) if raw else None


async def cache_set_json(key: str, value: Any, ttl: int) -> None:
    """Convenience: JSON-encode and cache a value."""
    await cache_set(key, json.dumps(value, ensure_ascii=False), ttl)
