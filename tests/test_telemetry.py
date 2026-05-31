"""Phase 6 Tests — telemetry recording, schema, helpers."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.deepsearch_mcp.core import telemetry


@pytest.fixture
async def telemetry_db(tmp_path, monkeypatch):
    """Enable telemetry pointed at a fresh tmp dir for the duration of the test."""
    monkeypatch.setenv("DEEPSEARCH_TELEMETRY", "1")
    monkeypatch.setenv("DEEPSEARCH_TELEMETRY_DIR", str(tmp_path))
    # Force re-init so schema is created in the new path
    telemetry._initialized_for = None
    yield tmp_path / "telemetry.db"
    telemetry._initialized_for = None


@pytest.fixture(autouse=True)
async def _drain_telemetry_after_test():
    """B8: guarantee no fire-and-forget telemetry write outlives its test.

    The `@track` decorator schedules the DB write via `asyncio.create_task`
    (fire-and-forget). A test that doesn't manually drain leaves that aiosqlite
    write racing the event-loop teardown, surfacing as an intermittent
    `PytestUnhandledThreadExceptionWarning`. Draining in teardown neutralizes it
    for *every* test — including the ones that legitimately don't assert on rows
    and so never call `_drain_pending_tasks()` themselves.
    """
    yield
    await telemetry.drain()


async def _drain_pending_tasks() -> None:
    """Wait until all fire-and-forget telemetry writes complete."""
    await telemetry.drain()


def _read_rows(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM telemetry ORDER BY id").fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Unit tests: pure helpers
# ---------------------------------------------------------------------------

class TestSummarizeInput:
    def test_short_input_passes_through(self):
        assert telemetry.summarize_input("python") == "python"

    def test_long_input_truncated_with_digest(self):
        long_q = "a" * 200
        out = telemetry.summarize_input(long_q)
        assert len(out) <= 80
        assert "…[" in out and out.endswith("]")

    def test_same_long_input_gives_same_digest(self):
        q = "x" * 150
        assert telemetry.summarize_input(q) == telemetry.summarize_input(q)

    def test_empty_returns_empty(self):
        assert telemetry.summarize_input("") == ""
        assert telemetry.summarize_input(None) == ""

    def test_whitespace_only_returns_empty(self):
        assert telemetry.summarize_input("   \n") == ""


class TestDomainFromUrl:
    def test_extracts_hostname(self):
        assert telemetry.domain_from_url("https://example.com/a/b") == "example.com"

    def test_lowercases_hostname(self):
        assert telemetry.domain_from_url("https://Example.COM/x") == "example.com"

    def test_subdomain_preserved(self):
        assert (
            telemetry.domain_from_url("https://blog.example.com/x")
            == "blog.example.com"
        )

    def test_empty_returns_none(self):
        assert telemetry.domain_from_url("") is None
        assert telemetry.domain_from_url(None) is None

    def test_malformed_returns_none(self):
        assert telemetry.domain_from_url("not a url") is None


class TestParseStatus:
    def test_structured_error_returns_code(self):
        result = json.dumps({"status": "error", "code": "RATE_LIMITED"})
        assert telemetry.parse_status(result) == "RATE_LIMITED"

    def test_structured_error_missing_code(self):
        result = json.dumps({"status": "error"})
        assert telemetry.parse_status(result) == "ERROR"

    def test_array_response_is_success(self):
        result = json.dumps([{"title": "a"}, {"title": "b"}])
        assert telemetry.parse_status(result) == "success"

    def test_non_json_is_success(self):
        result = "---\ntitle: x\n---\n\n# Body"
        assert telemetry.parse_status(result) == "success"

    def test_empty_is_success(self):
        assert telemetry.parse_status("") == "success"


# ---------------------------------------------------------------------------
# Integration: decorator records into a real (tmp) database
# ---------------------------------------------------------------------------

class TestTrackDecoratorRecords:
    async def test_success_records_status_success(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return json.dumps(["result1", "result2"])

        await dummy(query="hello world")
        await _drain_pending_tasks()

        rows = _read_rows(telemetry_db)
        assert len(rows) == 1
        assert rows[0]["tool_name"] == "dummy_tool"
        assert rows[0]["status"] == "success"
        assert rows[0]["input_summary"] == "hello world"
        assert rows[0]["tokens_approx"] > 0
        assert rows[0]["latency_ms"] >= 0
        assert rows[0]["domain"] is None  # primary_input != "url"

    async def test_structured_error_records_error_code(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return json.dumps({"status": "error", "code": "BLOCKED_403",
                                "message": "x", "hint": "y", "retryable": False})

        await dummy(query="forbidden test")
        await _drain_pending_tasks()

        rows = _read_rows(telemetry_db)
        assert len(rows) == 1
        assert rows[0]["status"] == "BLOCKED_403"

    async def test_url_primary_extracts_domain(self, telemetry_db):
        @telemetry.track("read_article", "url")
        async def dummy(url: str) -> str:
            return "ok body"

        await dummy(url="https://Example.COM/article/123")
        await _drain_pending_tasks()

        rows = _read_rows(telemetry_db)
        assert rows[0]["domain"] == "example.com"

    async def test_long_input_summary_truncated(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        long_query = "very long query " * 20
        await dummy(query=long_query)
        await _drain_pending_tasks()

        rows = _read_rows(telemetry_db)
        assert len(rows[0]["input_summary"]) <= 80

    async def test_multiple_calls_all_recorded(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        for i in range(5):
            await dummy(query=f"q{i}")
        await _drain_pending_tasks()

        rows = _read_rows(telemetry_db)
        assert len(rows) == 5

    async def test_decorator_does_not_change_return_value(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return json.dumps(["a", "b", "c"])

        result = await dummy(query="x")
        assert json.loads(result) == ["a", "b", "c"]

    async def test_positional_input_captured(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        await dummy("positional value")
        await _drain_pending_tasks()

        rows = _read_rows(telemetry_db)
        assert rows[0]["input_summary"] == "positional value"


class TestTrackDecoratorDisabled:
    async def test_disabled_does_not_record(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEEPSEARCH_TELEMETRY", "0")
        monkeypatch.setenv("DEEPSEARCH_TELEMETRY_DIR", str(tmp_path))

        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        result = await dummy(query="x")
        assert result == "ok"

        # DB file should not exist (no writes happened)
        assert not (tmp_path / "telemetry.db").exists()

    async def test_disabled_decorator_is_passthrough(self, tmp_path, monkeypatch):
        """Tool return value must be identical whether telemetry is on or off."""
        monkeypatch.setenv("DEEPSEARCH_TELEMETRY", "0")

        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return json.dumps({"echo": query})

        out = await dummy(query="hello")
        assert json.loads(out) == {"echo": "hello"}


class TestTrackDecoratorFailureSafety:
    async def test_db_write_failure_does_not_break_tool(self, telemetry_db, monkeypatch):
        """If the DB write raises, the tool must still return its result."""
        async def boom(*args, **kwargs):
            raise RuntimeError("simulated disk failure")

        monkeypatch.setattr(telemetry, "_write_event", boom)

        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "tool ok"

        result = await dummy(query="x")
        await _drain_pending_tasks()
        assert result == "tool ok"

    async def test_inner_function_exception_propagates(self, telemetry_db):
        """If the decorated function raises, the wrapper should not swallow it."""

        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            raise ValueError("tool bug")

        with pytest.raises(ValueError, match="tool bug"):
            await dummy(query="x")


class TestDrainSafety:
    """B8: the drain mechanism the autouse fixture relies on. The warning it
    prevents is a nondeterministic teardown artifact, so we pin the *invariant*
    — drain() must clear a genuinely-pending fire-and-forget write — rather than
    the flaky symptom."""

    async def test_drain_clears_a_pending_write(self, telemetry_db, monkeypatch):
        import asyncio

        # Make the write slow so the fire-and-forget task is provably still
        # pending after the tracked call returns — exactly the state that,
        # left undrained, races loop teardown.
        async def slow_write(row):
            await asyncio.sleep(0.05)

        monkeypatch.setattr(telemetry, "_write_event", slow_write)

        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        await dummy(query="hi")
        assert telemetry._pending_tasks, "a fire-and-forget write should be pending"
        await telemetry.drain()
        assert not telemetry._pending_tasks, "drain() must clear pending writes"


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------

class TestSchema:
    async def test_schema_has_indices(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        await dummy(query="x")
        await _drain_pending_tasks()

        con = sqlite3.connect(str(telemetry_db))
        idx = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='telemetry'"
        ).fetchall()]
        con.close()
        assert "idx_tool_time" in idx
        assert "idx_status" in idx
        assert "idx_domain" in idx

    async def test_all_required_columns_present(self, telemetry_db):
        @telemetry.track("dummy_tool", "query")
        async def dummy(query: str) -> str:
            return "ok"

        await dummy(query="x")
        await _drain_pending_tasks()

        con = sqlite3.connect(str(telemetry_db))
        cols = [r[1] for r in con.execute("PRAGMA table_info(telemetry)").fetchall()]
        con.close()
        required = {"timestamp", "tool_name", "input_summary", "status",
                    "tokens_approx", "latency_ms", "domain"}
        assert required.issubset(cols), f"Missing: {required - set(cols)}"
