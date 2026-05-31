# DeepSearch-MCP

**An LLM-optimized web research server built on the [Model Context Protocol](https://modelcontextprotocol.io/).**

DeepSearch-MCP is not a search wrapper — it is a **cognitive filter** for autonomous agents. It strips noise from web pages, handles adversarial bot protection, and guides agents out of research dead-ends, letting them focus on reasoning rather than parsing.

> **Philosophy:**
> 1. *Context is Gold.* Every token your agent reads should carry signal, not navigation bars.
> 2. *Agentic Resilience.* Every error returns a structured hint, never a traceback. The agent always knows what to do next.

---

## Why DeepSearch-MCP?

Standard MCP search servers return raw HTML text, burning 40–70% of context window on noise. DeepSearch-MCP solves three failure modes:

| Problem | Standard Server | DeepSearch-MCP |
|---------|----------------|----------------|
| **Context Pollution** | Nav bars, cookie banners, ads in output | `trafilatura` extraction → clean Markdown only |
| **Fragility (403/429)** | Python traceback crashes agent | Structured JSON hint → agent recovers autonomously |
| **Research Dead-Ends** | Agent re-reads same 3 SEO articles | `suggest_queries` breaks echo chambers with criticism/alternative angles |
| **Day 2 Decay** | No way to know which sites are failing | Built-in `telemetry.db` + analyzer flags hotspots automatically |

---

## Quick Start

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`

### Install

```bash
# Clone the repository
git clone https://github.com/your-username/DeepSearch-MCP.git
cd DeepSearch-MCP

# Create virtual environment and install dependencies
uv sync

# Verify installation
uv run python -m pytest tests/ -q
```

### Run a demo simulation

```bash
uv run python evals/simulate_research.py --demo
```

This runs a 4-step ReAct research loop (MCP trends topic) with pre-set data — no network required.

For a live run with real DuckDuckGo searches:

```bash
uv run python evals/simulate_research.py
```

---

## MCP Client Configuration

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/DeepSearch-MCP",
        "run",
        "python",
        "-m",
        "deepsearch_mcp.server"
      ]
    }
  }
}
```

Restart Claude Desktop after saving. You should see the three tools available in the tool picker.

### Claude Code (CLI)

```bash
claude mcp add deepsearch -- uv --directory /absolute/path/to/DeepSearch-MCP run python -m deepsearch_mcp.server
```

### Cursor / VS Code (`.cursor/mcp.json` or `.vscode/mcp.json`)

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/DeepSearch-MCP",
        "run",
        "python",
        "-m",
        "deepsearch_mcp.server"
      ]
    }
  }
}
```

### Using `python` directly (without `uv`)

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "/absolute/path/to/DeepSearch-MCP/.venv/bin/python",
      "args": ["-m", "deepsearch_mcp.server"],
      "env": {
        "DEEPSEARCH_CACHE_DIR": "/tmp/deepsearch-cache"
      }
    }
  }
}
```

---

## Tools

### `search_web` — DuckDuckGo search with caching

Searches DuckDuckGo and returns structured results. Results are cached for 24 hours — repeated identical queries are free and instant.

```
Parameters:
  query        Keywords (not full sentences). Max 500 chars.
  region       Country code: 'us-en', 'jp-jp', 'wt-wt' (global default).
  timelimit    'd'=day, 'w'=week, 'm'=month, 'y'=year. None=all time.
  max_results  1–50. Default 10.

Returns: JSON array of {title, url, body, published_date, score,
                        source_tier, near_duplicate, story_cluster}
```

`source_tier` flags curated-trusted domains; `near_duplicate` flags a near-identical
earlier result (skip re-reading); `story_cluster` is an id grouping the *same story*
across outlets (a corroboration signal — read 1–2 per cluster, count them as one source).

`published_date` is a best-effort freshness signal **derived from the result URL**
(news URLs embed the date, e.g. `/2026/05/28/`); it is `null` when the URL carries
no date (most non-news pages) — `null` does not mean "old". Treat it as approximate.

**Best practice:** Use `timelimit="y"` when researching current events to filter
stale content; use `published_date` to spot/sort recent items within the results.

### `read_article` — Clean Markdown extraction

Fetches a URL and returns only the article body as clean Markdown with YAML frontmatter. Handles anti-bot protection via TLS fingerprinting. Rejects PDFs, images, and archives before making a network call.

```
Parameters:
  url            Full URL of the article to read.
  include_links  Include hyperlinks in output (default: false, saves tokens).

Returns: YAML frontmatter + Markdown body (truncated at ~16,000 chars)
```

**Best practice:** Only call with specific article URLs found via `search_web`. Do not use for homepages, category pages, or search result listings.

### `suggest_queries` — Echo-chamber breaker

Generates 3–8 diverse search queries when research has stalled. Combines DuckDuckGo autocomplete (real user patterns) with viewpoint-shifting templates: criticism, alternatives, primary sources (arxiv/GitHub), and temporal freshness.

```
Parameters:
  topic    The core concept being researched (not a full question).
  context  Optional: paste 1–3 search snippets already seen.
           Helps avoid repeating queries and enables entity drill-down.

Returns: JSON array of query strings, ready to pass to search_web.
```

**Best practice:** Call this when results are all from the same source or perspective, or before starting a deep research loop to pre-plan query diversity.

---

## Agent Best Practices

```
Research Loop Pattern (ReAct):
  1. search_web("your topic", timelimit="y") → get URLs
  2. read_article(url) for top 2-3 results → extract content
  3. IF results feel one-sided → suggest_queries("topic", context=snippets)
  4. search_web(suggested_query) → explore new angle
  5. Repeat until sufficient coverage across multiple source types
```

**Token budget awareness:**
- `search_web` snippets: ~10–50 tokens per result (safe to read all)
- `read_article` full content: ~500–4,000 tokens per article (read selectively)
- `suggest_queries`: ~50 tokens (always cheap to call)

**Error recovery:**
All tools return structured JSON errors, never raw tracebacks:
```json
{
  "status": "error",
  "code": "BLOCKED_403",
  "message": "HTTP 403 Forbidden for url: https://...",
  "hint": "Access denied. Try a different source.",
  "retryable": false
}
```

When `retryable: true` (rate limit), wait 60 seconds before retrying.
When `retryable: false`, skip the URL and try the next result.

---

## Configuration

Environment variables (optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEARCH_CACHE_DIR` | `./.cache` | SQLite cache directory |
| `DEEPSEARCH_TIMEOUT` | `10` | HTTP timeout in seconds per attempt |
| `DEEPSEARCH_TELEMETRY` | `1` | Set to `0` to disable telemetry recording |
| `DEEPSEARCH_TELEMETRY_DIR` | `./.cache` | Directory for `telemetry.db` |

---

## Operations (Day 2)

Every tool call records a row to `telemetry.db` (tool_name, status, tokens, latency, domain).
Run the analyzer to surface domains/queries that need attention:

```bash
# Print the report (failure hotspots, token inefficiency, error patterns)
uv run python evals/analyze_telemetry.py

# Machine-readable JSON
uv run python evals/analyze_telemetry.py --json

# Generate synthetic data to evaluate the analyzer itself
uv run python evals/generate_dummy_telemetry.py
```

The analyzer auto-suggests actions like *"Add a domain adapter for substack.com (38% failure rate)"*.
See [docs/MAINTENANCE.md](docs/MAINTENANCE.md) for the full SRE runbook.

---

## Troubleshooting

### `curl_cffi` build error on install

`curl_cffi` requires a C compiler. On macOS:
```bash
xcode-select --install
```
On Linux (Ubuntu/Debian):
```bash
apt-get install build-essential libcurl4-openssl-dev
```
Alternatively, use a pre-built wheel:
```bash
pip install curl-cffi --prefer-binary
```

### DuckDuckGo rate limit (429 / RATE_LIMITED)

DuckDuckGo rate-limits aggressive querying. Built-in mitigations:
- Random 0.5–1.5s jitter between requests
- 24-hour result cache (repeated queries are free)

If you hit rate limits in a heavy research session, wait 60 seconds before retrying. Using `timelimit` and `region` parameters reduces effective query frequency.

### "duckduckgo_search has been renamed to ddgs" warning

This `RuntimeWarning` from the upstream library is expected and suppressed internally. It does not affect functionality.

### Site returns 403 / BLOCKED_403

Many sites block automated access. Options:
1. Search for a cached or mirrored version of the article
2. Use `suggest_queries` to find alternative sources on the same topic
3. Look for the content on GitHub, arXiv, or official documentation sites

### `read_article` on a PDF URL returns UNSUPPORTED_FORMAT

This is correct behavior. `read_article` detects non-HTML resources (PDFs, images, archives) by URL extension and `Content-Type` header, and returns a structured error before making an unnecessary network call. Use `search_web` to find an HTML version of the document instead.

### Content is truncated at 16,000 characters

This is intentional — the limit protects your agent's context window. For very long documents, request a specific anchored URL (e.g., a documentation section) for targeted content.

---

## Development

```bash
# Run all tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Run quality eval (demo mode, no network)
uv run python evals/simulate_research.py --demo

# Run quality eval (live network)
uv run python evals/simulate_research.py
```

### Test Coverage

| Phase | File | Tests | Scope |
|-------|------|-------|-------|
| 0 | `test_judge.py` | 16 | eval_judge quality scorer |
| 1, 4, 5, 6 | `test_extractor.py` | 58 | Extraction gauntlet, noise removal, UNSUPPORTED_FORMAT, H1 dedup, domain adapters (substack/medium) |
| 2, 5 | `test_search.py` | 48 | search_web, cache, chaos engineering, error sanitization, transient detection |
| 3, 5 | `test_suggest.py` | 54 | suggest_queries, Stuck Agent simulation, smart quoting, date parser |
| 6 | `test_telemetry.py` | 28 | Telemetry decorator, helpers, schema, failure safety |
| **Total** | | **204** | |

---

## Project Structure

```
DeepSearch-MCP/
├── src/deepsearch_mcp/
│   ├── server.py           # FastMCP entry point
│   ├── tools/
│   │   ├── search.py       # search_web tool
│   │   ├── extractor.py    # read_article tool
│   │   └── suggest.py      # suggest_queries tool
│   ├── core/
│   │   ├── http.py            # curl_cffi stealth fetcher (chrome131 impersonation)
│   │   ├── extractor.py       # trafilatura + readability-lxml pipeline
│   │   ├── models.py          # Pydantic schemas
│   │   ├── errors.py          # Structured error responses
│   │   ├── cache.py           # SQLite cache with TTL (aiosqlite)
│   │   ├── telemetry.py       # @track decorator → telemetry.db (Day 2 ops)
│   │   └── source_quality.py  # authoritative/unknown source tier (B15)
│   └── utils/
│       ├── cleaner.py      # Markdown noise removal + dedup + citation strip
│       └── date_parser.py  # ISO 8601 normalization + URL/body fallback
├── scripts/                # status.py · verify.py · docs_map.py ·
│                           # collect_telemetry.py · live_check.py ·
│                           # propose_noise_regex.py · research.py
├── evals/
│   ├── eval_judge.py             # Quality scorer (0–10, 3 axes)
│   ├── calibrate_judge.py        # B1: judge-vs-consumer correlation check
│   ├── simulate_research.py      # E2E ReAct loop simulation
│   ├── analyze_telemetry.py      # Day 2 ops: usage analysis + alerts
│   ├── telemetry_diff.py         # B4: before/after release diff of two telemetry.db
│   ├── dogfood_research.py       # real-tool research harness + noise audit
│   ├── dogfood_regression.py     # golden-baseline extraction regression
│   ├── dogfood_audit.py          # residual-noise auditor
│   └── generate_dummy_telemetry.py # synthetic data for analyzer testing
├── tests/                  # 339 tests across all phases
└── docs/
    ├── CONCEPT.md          # Architecture rationale
    ├── SPEC.md             # Detailed technical specification
    ├── ROADMAP.md          # Development roadmap with phase gates
    ├── ARCHITECTURE.md     # System data flow (Mermaid diagrams)
    └── MAINTENANCE.md      # SRE runbook + telemetry SQL recipes
```

---

## License

MIT
