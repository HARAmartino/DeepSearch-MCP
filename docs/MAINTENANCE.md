# Maintenance Runbook — DeepSearch-MCP

The operational complement to [ARCHITECTURE.md](ARCHITECTURE.md).
Whoever (or whatever AI agent) maintains this server after release should
start here.

---

## Table of Contents

1. [Daily ops cadence](#daily-ops-cadence)
2. [Reading `telemetry.db` — SQL recipes](#reading-telemetrydb--sql-recipes)
3. [Responding to analyzer alerts](#responding-to-analyzer-alerts)
4. [Responding to auditor findings (semantic probe)](#responding-to-auditor-findings-semantic-probe)
5. [Updating dependencies](#updating-dependencies)
6. [Cache hygiene](#cache-hygiene)
7. [Test gate before any merge](#test-gate-before-any-merge)
8. [Incident playbook](#incident-playbook)

---

## Daily ops cadence

| Cadence | Command | Purpose |
|---------|---------|---------|
| Once (activation) | `DEEPSEARCH_TELEMETRY_DIR=.cache_live python scripts/collect_telemetry.py` | Seed `telemetry.db` with real traffic to start the aggregate probe |
| Daily   | `python evals/analyze_telemetry.py` | Scan for new alerts (aggregate probe) |
| Weekly  | `uv run python evals/dogfood_regression.py` | Catch extraction drift from golden baselines |
| Monthly | `uv run python evals/dogfood_research.py` (reads the STEP 4 audit) | Surface *new* residual noise (fixture-based semantic probe) |
| Monthly | `python scripts/live_check.py` — **read the output by hand** | Real-usage probe: run the tools on the live web; fixtures only contain noise you already know |
| Monthly | `pip list --outdated` + read CHANGELOG of `duckduckgo-search`, `trafilatura`, `curl_cffi` | Catch API drift early |
| Quarterly | `uv run python -m pytest tests/ -q` against a fresh `uv sync` | Confirm pinned versions still work |

---

## Reading `telemetry.db` — SQL recipes

Path: `${DEEPSEARCH_TELEMETRY_DIR:-./.cache}/telemetry.db` (SQLite 3).

Open with:
```bash
sqlite3 -header -column $DEEPSEARCH_TELEMETRY_DIR/telemetry.db
```

> Most of what's below is also surfaced automatically by
> `evals/analyze_telemetry.py`. Use the raw SQL when you need an ad-hoc
> question that the canned reports don't answer.

### Top-5 failing domains

```sql
SELECT
    domain,
    COUNT(*) AS total,
    SUM(CASE WHEN status IN ('BLOCKED_403','EMPTY_CONTENT','UNSUPPORTED_FORMAT','TIMEOUT')
             THEN 1 ELSE 0 END) AS failures,
    ROUND(100.0 * SUM(CASE WHEN status IN ('BLOCKED_403','EMPTY_CONTENT','UNSUPPORTED_FORMAT','TIMEOUT')
                            THEN 1 ELSE 0 END) / COUNT(*), 1) AS failure_pct
FROM telemetry
WHERE tool_name = 'read_article' AND domain IS NOT NULL
GROUP BY domain
HAVING COUNT(*) >= 3
ORDER BY failure_pct DESC, total DESC
LIMIT 5;
```

### Highest-token-cost successful reads (potential noise leak)

```sql
SELECT
    domain,
    ROUND(AVG(tokens_approx), 0) AS avg_tokens,
    MAX(tokens_approx) AS max_tokens,
    COUNT(*) AS samples
FROM telemetry
WHERE tool_name = 'read_article'
  AND status = 'success'
  AND domain IS NOT NULL
GROUP BY domain
HAVING COUNT(*) >= 5 AND AVG(tokens_approx) > 2500
ORDER BY avg_tokens DESC
LIMIT 10;
```

### Error spike in the last 24 h

```sql
SELECT
    tool_name,
    status,
    COUNT(*) AS occurrences
FROM telemetry
WHERE status != 'success'
  AND timestamp > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day')
GROUP BY tool_name, status
ORDER BY occurrences DESC;
```

### Latency p50 / p95 per tool (last 7 days)

```sql
WITH ranked AS (
    SELECT
        tool_name,
        latency_ms,
        NTILE(100) OVER (PARTITION BY tool_name ORDER BY latency_ms) AS pct
    FROM telemetry
    WHERE timestamp > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days')
)
SELECT
    tool_name,
    MAX(CASE WHEN pct = 50 THEN latency_ms END) AS p50_ms,
    MAX(CASE WHEN pct = 95 THEN latency_ms END) AS p95_ms
FROM ranked
GROUP BY tool_name;
```

### Agent-loop detection (same input ≥ 10× in an hour)

```sql
SELECT
    input_summary,
    tool_name,
    COUNT(*) AS calls,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM telemetry
WHERE timestamp > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 hour')
GROUP BY input_summary, tool_name
HAVING COUNT(*) >= 10
ORDER BY calls DESC;
```

A hit here means an agent (not the server) is stuck. Capture the
`input_summary` and add it as a "DO NOT USE WHEN" example in the relevant
tool's docstring. See **Operations Rule 5** in `CLAUDE.md`.

---

## Responding to analyzer alerts

`evals/analyze_telemetry.py` prints a `🛠 SUGGESTED ACTIONS` section.
Every suggestion maps to one of the **Operations Rules** in `CLAUDE.md`.
Below is the workflow for each.

> **Cold-start guard.** Below `MIN_ROWS_FOR_CONFIDENCE` (50) total rows the
> report prints a **LOW CONFIDENCE** banner and labels every action
> **PROVISIONAL**. Do **not** patch off provisional alerts — a 3-sample
> failure rate is noise. Let **real traffic** accumulate until the banner
> clears, then act. "No alerts" on thin data means "not enough data yet", not
> "healthy".
>
> **Representativeness guard.** Row count is not enough: if a tool is ≥90% one
> non-success status (e.g. a blocked backend → 100% `CONN_ERROR`), verdicts
> stay PROVISIONAL *no matter how many rows*. The banner says "more rows will
> NOT fix skew — fix the systemic failure first." **Do not** clear LOW
> CONFIDENCE by re-running `collect_telemetry.py` against a contrived battery;
> that manufactures false confidence. The collector is for *bootstrapping the
> pipeline*, not for fabricating a health verdict — only organic traffic earns
> a real one.

### Alert: `Add a domain adapter for <hostname>` (Rule 1)

**Pre-condition.** Failure rate ≥ 15 % over ≥ 3 calls, surfaced by
`failure_hotspots()`.

1. Pick a sample failing URL from telemetry:
   ```sql
   SELECT input_summary, status, timestamp
   FROM telemetry
   WHERE domain = 'NEW_DOMAIN' AND status != 'success'
   ORDER BY timestamp DESC LIMIT 5;
   ```
2. Fetch one such URL by hand (`curl -A "Mozilla/5.0…"`) and open it in
   a browser DevTools "Elements" panel.
3. Identify the CSS selectors of the noise / paywall / subscribe widget.
4. Add a preprocessor in `src/deepsearch_mcp/core/extractor.py`:
   ```python
   def _newdomain_preprocess(html: str) -> str:
       soup = BeautifulSoup(html, "lxml")
       for sel in ["div.paywall", "div.subscribe-box", ...]:
           for el in soup.select(sel):
               el.decompose()
       return str(soup)

   _DOMAIN_PREPROCESSORS["newdomain.com"] = _newdomain_preprocess
   ```
5. Add a regression test under `tests/test_extractor.py` modelled on
   `TestSubstackAdapter` (fixture HTML, assert noise gone + prose
   preserved, subdomain routing, non-target passthrough).
6. Run the gauntlet (`uv run pytest tests/test_extractor.py -q`) to confirm
   no regression on other domains.
7. Add a `CHANGELOG.md` entry under `## [Unreleased] > Added`.

### Alert: `Investigate noise on <domain>` (Rule 2)

**Pre-condition.** Average ≥ 3000 tokens per successful article.

1. Pick a high-token sample:
   ```sql
   SELECT input_summary, tokens_approx FROM telemetry
   WHERE domain = 'NOISY_DOMAIN' AND status = 'success'
   ORDER BY tokens_approx DESC LIMIT 3;
   ```
2. Fetch + diff the extraction output against the actual article body.
3. Two fix paths:
   - **Generic noise** (e.g. "Sign up for our weekly newsletter"):
     add the phrase as a regex in `utils/cleaner.py` `_NOISE_PATTERNS`.
   - **Site-specific noise**: add a `_DOMAIN_PREPROCESSORS` adapter (Rule 1).
4. Re-score with `evals/eval_judge.py` to confirm density/structure
   didn't drop.

### Alert: `search_web is rate-limited heavily` (Rule 3)

**Pre-condition.** `RATE_LIMITED` ≥ 30 % of `search_web` errors.

1. **First.** Confirm we aren't being noisy: are agents calling
   `search_web` redundantly? Run the agent-loop SQL above. If yes,
   patch the agent's prompt, not the server.
2. **Second.** Extend the cache TTL: `core/cache.py` `TTL_SEARCH`
   `86_400` → `172_800` (48 h). Add a CHANGELOG entry.
3. **Third.** Widen the request jitter: `tools/search.py`
   `_JITTER_MIN, _JITTER_MAX` `0.5, 1.5` → `1.0, 3.0`.
4. **Last resort.** Diversify by region: temporarily randomize
   `region` across `("wt-wt", "us-en", "uk-en", "jp-jp")` in
   the calling agent's prompt.

### Alert: `403 wall on read_article` (Rule 4)

**Pre-condition.** `BLOCKED_403` ≥ 50 % of `read_article` errors.

1. Check current curl_cffi-supported impersonate targets:
   ```bash
   uv run python -c "from curl_cffi.requests import BrowserType; \
                     print([b.name for b in BrowserType])"
   ```
2. Pick a newer Chrome target (e.g. `chrome146`) and update
   `_IMPERSONATE` in `core/http.py`.
3. **Mandatory regression check.** Run
   `uv run pytest tests/test_extractor.py::TestGauntletScores -q` —
   if the average drops below 8.5/10, revert: a newer fingerprint
   sometimes triggers different anti-bot logic.
4. Update CLAUDE.md `Lessons Learned > curl_cffi v0.x` with the
   new target's compatibility notes.

### Alert: agent-loop detected (Rule 5)

This is a *client-side* problem, not a server bug.

1. Identify the `input_summary` that's repeating.
2. Trace it back to the agent's task / prompt.
3. Add the failing pattern as a `Bad (…) → use Y instead` Few-Shot
   example in the relevant tool's docstring.
4. **Do not** add server-side rate-limiting on identical inputs —
   the cache already handles legitimate repeats for free, and a
   stricter limit would harm well-behaved agents.

### Alert: `read_article extraction length ... Rule 6` (extraction drift)

Surfaced by the **inter-release** diff, not the single-snapshot analyzer:

```bash
# capture a snapshot per release (e.g. copy ./.cache/telemetry.db aside), then:
python evals/telemetry_diff.py --before before/telemetry.db --after ./.cache/telemetry.db
```

A `⚠ Rule 6` line means `read_article`'s average successful-extraction token
count moved ≥ 10 % between the two snapshots — usually **silent extractor
drift**, not a real content change.

1. Run `python evals/dogfood_regression.py`. If goldens drifted, the extractor
   or cleaner changed — locate and review the diff.
2. If goldens are clean, spot-check a handful of live extractions: is the body
   gaining boilerplate (length ↑) or getting truncated (length ↓)?
3. If a dependency moved (`trafilatura`, `readability-lxml`, `lxml`), pin or
   revert it in `pyproject.toml` and add a dated `[ACTIVE]` entry to
   `docs/LESSONS.md` describing the trap.
4. The alert needs ≥ 5 successful extractions per snapshot; below that it stays
   silent (a 1-sample average is noise, not drift).

---

## Responding to auditor findings (semantic probe)

`evals/dogfood_audit.py` runs as STEP 4 of `dogfood_research.py` (and as a
standalone CLI: `python evals/dogfood_audit.py output.md`). It prints a
`SUSPECTED NOISE` shortlist — lines that survived the cleaner but match a
broad noise heuristic. **Findings are advisory: the auditor proposes, you
dispose.** Workflow when it flags a line:

1. **Triage.** Genuine noise, or a false positive (real prose that tripped a
   heuristic)? If false positive, tighten `dogfood_audit.py` (raise
   `_MAX_SUSPECT_WORDS`, narrow a regex) and add a guard test — *do not*
   touch the cleaner.
2. **Classify the noise.**
   - **Generic phrase** (appears across many sites, e.g. "affiliate links"):
     add a regex to `utils/cleaner.py` `_NOISE_LINE_RE`. Prefer this.
   - **Site-specific DOM** (a widget on one domain): add a
     `_DOMAIN_PREPROCESSORS` adapter instead (Rule 1).
   For the generic-phrase case, get a vetted candidate + blast-radius check:
   ```bash
   python scripts/propose_noise_regex.py "View all 23 comments"
   ```
   It prints a generalized candidate (counts → `\d+`) and **fails if the
   pattern would match any already-clean prose** in the fixtures — paste it
   only when it reports "safe to add". You still own the judgment; the tool
   owns the verification.
3. **Test first.** Add a failing extractor test (`TestDogfoodingNoisePatterns`
   in `tests/test_extractor.py`) containing the noise line, then patch.
4. **Prove the loop closed.** Re-run `dogfood_research.py`; the audit count
   for that fixture must drop to 0. Record the before/after count.
5. **Re-baseline.** If the patched output changed a golden, run
   `python evals/dogfood_regression.py --update` and review the diff.
6. **Two-tier reminder.** Full-sentence noise (affiliate / sponsorship /
   legal) → auditor STRONG tier (length-independent). Short labels (CTA,
   byline stub) → SOFT tier (short-line-only). Mis-tiering either lets long
   noise through or false-positives on prose.

---

## Updating dependencies

> **Prime Directive 3 — Fact-Check First.** Library APIs (especially
> `duckduckgo-search`) drift. **Never** rely on memorized API shapes.

### `duckduckgo-search`

Before upgrading:
1. `pip show duckduckgo-search` for the current pin.
2. Check the upstream release notes / GitHub.
3. Run the integration tests **with a real network** — chaos-mocked
   tests will not catch backend-rename breakage:
   ```bash
   uv run pytest tests/test_search.py -q -k "TestSearchWebTool"
   ```
4. The library is mid-rename to `ddgs`. If the import path moves,
   update `tools/search.py` accordingly and bump the
   `[project] dependencies` pin in `pyproject.toml`.

### `trafilatura`

1. Re-run the Phase 1 gauntlet:
   ```bash
   uv run pytest tests/test_extractor.py::TestGauntletScores -q
   ```
2. If any category drops below 7.0, the new version may have
   regressed the `<article>`/`<main>` deduplication. Pin to the
   prior minor version and open an upstream issue.

### `curl_cffi`

1. Check `BrowserType` enum members for new impersonate targets.
2. The default `chrome131` has been stable; only update if `BLOCKED_403`
   rate exceeds 50 % (Operations Rule 4).

### Source-quality allowlist (`core/source_quality.py`)

`_AUTH_DOMAINS` is a **curated, high-precision** allowlist — it is fine for it
to be incomplete (the default is `unknown`, not "bad"). When a clearly
authoritative source keeps showing up tagged `unknown` in real runs, add its
registrable domain (e.g. `nature.com`, not `www.nature.com`). **Never** add a
domain you are not confident is authoritative, and **never** add a "low quality"
denylist — that path defames legitimate small sites (see the B15 lesson).

### Python itself

`requires-python = ">=3.11"`. Code uses `X | None` syntax + `asyncio.to_thread`,
neither available before 3.10. Bumping the minimum to 3.12 is fine
(no syntax requires it yet); going below 3.11 will break.

---

## Cache hygiene

Both caches (`cache.db`, `telemetry.db`) live under `./.cache/` by default
(or `DEEPSEARCH_CACHE_DIR` / `DEEPSEARCH_TELEMETRY_DIR`).

### Purge expired search/article cache entries

```python
# One-shot:
uv run python -c "import asyncio; from src.deepsearch_mcp.core.cache import cache_purge_expired; print(asyncio.run(cache_purge_expired()))"
```

### Rotate telemetry monthly (optional)

```sql
-- Archive last 30 d → keep DB lean
ATTACH DATABASE 'telemetry-archive.db' AS arc;
CREATE TABLE arc.telemetry AS
    SELECT * FROM telemetry
    WHERE timestamp < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-30 days');
DELETE FROM telemetry
    WHERE timestamp < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-30 days');
VACUUM;
```

---

## Test gate before any merge

**One command** runs the full gate (pytest + ruff + dogfood_regression) with a
single exit code — so you cannot forget one:

```bash
python scripts/verify.py          # or: .venv/bin/python scripts/verify.py
```

To orient before you start (live test count, gate status, next backlog item):

```bash
python scripts/status.py
```

If you changed `core/extractor.py` or `utils/cleaner.py`, additionally
re-run the gauntlet and confirm average ≥ 8.5, and the E2E smoke:
```bash
.venv/bin/python -m pytest tests/test_extractor.py::TestGauntletScores -v
.venv/bin/python evals/simulate_research.py --demo
```

> Note: `uv run …` is the documented form, but the agent tool-shell often
> lacks `uv` on PATH. `scripts/verify.py` auto-detects `.venv/bin/` and works
> either way — prefer it over hand-typing the three commands.

---

## Incident playbook

### "All `search_web` calls return `CONN_ERROR`"

1. Is the host's DNS resolving? `dig duckduckgo.com`.
2. Is DDG up? `curl -I https://duckduckgo.com/html/`.
3. If both are healthy, the DDGS library may have a backend outage.
   The error is `retryable=True` (Phase 5 fix), so agents will retry
   on their own. Confirm normal operation resumes within 10–15 min.

### "Telemetry DB grew to >100 MB"

That's about 1 M rows. Either rotate (see *Cache hygiene*) or expand
`DEEPSEARCH_TELEMETRY_DIR` to a partition with more space.
Tool latency is **not** affected — writes are fire-and-forget and
each row is < 1 KB.

### "Tool returns `BLOCKED_403` for a site that worked yesterday"

1. The site updated its anti-bot rules. Try `chrome146` (Rule 4).
2. If still blocked, the site may now require login. Add an entry to
   `CHANGELOG.md > Known Limitations` and tell agents (via the tool
   docstring) to look elsewhere.

### "Agent reports the server is hallucinating"

The server never generates text. Either:
- The agent fed the tool output to an LLM that hallucinated downstream
  (not our problem).
- Or the agent confused `search_web` snippets with `read_article` full
  text. Verify the schema (`title, url, body, published_date`) matches
  the agent's prompt.
