"""
Generate synthetic telemetry data for testing the analyzer.

Produces ~1,000 rows over the last 30 days with intentional pain points:

  - **substack.com**: high EMPTY_CONTENT rate (subscription gates → empty extraction)
  - **medium.com**: high BLOCKED_403 rate (member-only paywalls)
  - **techcrunch.com**: healthy baseline (low failure rate)
  - **bigcorp.com**: high avg tokens (noisy footer leaks)
  - **search_web**: occasional RATE_LIMITED bursts

Usage:
    python evals/generate_dummy_telemetry.py
    DEEPSEARCH_TELEMETRY_DIR=/tmp/demo python evals/generate_dummy_telemetry.py
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Profiles (domain → realistic failure characteristics)
# ---------------------------------------------------------------------------

_PROFILES = {
    # Healthy baseline — low failures, normal tokens
    "techcrunch.com":      {"failure_rate": 0.05, "top_failure": "EMPTY_CONTENT",
                            "avg_tokens": 1200, "samples": 60},
    "arstechnica.com":     {"failure_rate": 0.08, "top_failure": "BLOCKED_403",
                            "avg_tokens": 1100, "samples": 50},
    "github.com":          {"failure_rate": 0.02, "top_failure": "EMPTY_CONTENT",
                            "avg_tokens": 900,  "samples": 80},
    "arxiv.org":           {"failure_rate": 0.10, "top_failure": "UNSUPPORTED_FORMAT",
                            "avg_tokens": 1500, "samples": 40},

    # Hotspots — must trigger alerts in the analyzer
    "substack.com":        {"failure_rate": 0.42, "top_failure": "EMPTY_CONTENT",
                            "avg_tokens": 800,  "samples": 50},
    "medium.com":          {"failure_rate": 0.28, "top_failure": "BLOCKED_403",
                            "avg_tokens": 950,  "samples": 45},

    # Noise leak — high token count without failure
    "bigcorp.com":         {"failure_rate": 0.05, "top_failure": "EMPTY_CONTENT",
                            "avg_tokens": 3800, "samples": 35},
}

_SEARCH_QUERIES = [
    "python asyncio tutorial",
    "MCP model context protocol",
    "RAG vector database 2026",
    "transformers attention mechanism",
    "LLM agent benchmarks",
    "rust web framework comparison",
]

_SUGGEST_TOPICS = [
    "React Server Components",
    "CRISPR",
    "AI agent memory",
    "quantum computing",
]


def _iso_at(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _digest(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:8]


def _make_summary(value: str) -> str:
    if len(value) <= 80:
        return value
    return f"{value[:60]}…[{_digest(value)}]"


# ---------------------------------------------------------------------------
# Row generators
# ---------------------------------------------------------------------------

def _gen_read_article_rows(rng: random.Random, now: float) -> list[tuple]:
    rows: list[tuple] = []
    for domain, prof in _PROFILES.items():
        for _ in range(prof["samples"]):
            ts = now - rng.uniform(0, 30 * 86400)  # last 30 days
            url = f"https://{domain}/articles/{rng.randint(1000, 9999)}"
            summary = _make_summary(url)
            failed = rng.random() < prof["failure_rate"]
            if failed:
                # Top failure 70% of the time, other failures 30%
                if rng.random() < 0.7:
                    status = prof["top_failure"]
                else:
                    status = rng.choice(
                        ["BLOCKED_403", "EMPTY_CONTENT", "TIMEOUT", "UNSUPPORTED_FORMAT"]
                    )
                tokens = rng.randint(60, 200)  # small error JSON
                latency_ms = rng.randint(50, 1500)
            else:
                status = "success"
                # tokens distributed around domain avg with noise
                tokens = max(100, int(rng.gauss(prof["avg_tokens"], prof["avg_tokens"] * 0.15)))
                latency_ms = rng.randint(800, 3500)

            rows.append((
                _iso_at(ts), "read_article", summary,
                status, tokens, latency_ms, domain,
            ))
    return rows


def _gen_search_web_rows(rng: random.Random, now: float, n: int = 150) -> list[tuple]:
    rows: list[tuple] = []
    for _ in range(n):
        ts = now - rng.uniform(0, 30 * 86400)
        q = rng.choice(_SEARCH_QUERIES)
        # 8% of searches hit rate limit
        if rng.random() < 0.08:
            status = "RATE_LIMITED"
            tokens = rng.randint(40, 80)
            latency_ms = rng.randint(100, 600)
        elif rng.random() < 0.04:
            status = "CONN_ERROR"
            tokens = rng.randint(40, 100)
            latency_ms = rng.randint(2000, 5000)
        else:
            status = "success"
            tokens = rng.randint(400, 1200)
            latency_ms = rng.randint(400, 1800)
        rows.append((_iso_at(ts), "search_web", q, status, tokens, latency_ms, None))
    return rows


def _gen_suggest_rows(rng: random.Random, now: float, n: int = 50) -> list[tuple]:
    rows: list[tuple] = []
    for _ in range(n):
        ts = now - rng.uniform(0, 30 * 86400)
        topic = rng.choice(_SUGGEST_TOPICS)
        status = "success"
        tokens = rng.randint(80, 160)
        latency_ms = rng.randint(30, 200)
        rows.append((_iso_at(ts), "suggest_queries", topic, status, tokens, latency_ms, None))
    return rows


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

_CREATE = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    status TEXT NOT NULL,
    tokens_approx INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    domain TEXT
);
"""


def populate(db_path: Path, seed: int = 42) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    now = time.time()

    rows = (
        _gen_read_article_rows(rng, now)
        + _gen_search_web_rows(rng, now)
        + _gen_suggest_rows(rng, now)
    )
    rng.shuffle(rows)

    con = sqlite3.connect(str(db_path))
    con.execute(_CREATE)
    con.execute("DELETE FROM telemetry")  # idempotent re-runs
    con.executemany(
        "INSERT INTO telemetry "
        "(timestamp, tool_name, input_summary, status, tokens_approx, "
        " latency_ms, domain) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    con.commit()
    con.close()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Populate telemetry.db with synthetic data.")
    parser.add_argument("--db", help="Override path to telemetry.db")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    args = parser.parse_args(argv)

    if args.db:
        db_path = Path(args.db)
    else:
        base = os.getenv("DEEPSEARCH_TELEMETRY_DIR", "./.cache")
        db_path = Path(base) / "telemetry.db"

    count = populate(db_path, args.seed)
    print(f"✓ Wrote {count:,} synthetic rows to {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
