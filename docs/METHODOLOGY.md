# Self-Improvement Methodology — DeepSearch-MCP

**How an agent (human or LLM) decides what to improve next, and how to verify the improvement is real.**

This document is the meta-process layer above the Build-Eval-Learn workflow in `CLAUDE.md`.
Read it when you are about to make a change but are unsure where to start, or when you want
to know whether your in-progress improvement is "done".

> **Quick rule:** if you are not sure why you are touching the code, run §1 (Trigger
> Hierarchy) top-to-bottom and stop at the first match.

---

## Table of Contents

1. [Trigger Hierarchy — what to improve next](#1-trigger-hierarchy)
2. [Definition of Done — when an improvement is complete](#2-definition-of-done)
3. [Anti-Patterns — mistakes to avoid](#3-anti-patterns)
4. [Operations Rules — telemetry alert → patch mapping](#4-operations-rules-telemetry-alert--patch-mapping)
5. [Open Improvement Backlog](#5-open-improvement-backlog)
6. [Audit Cadence](#6-audit-cadence)

---

## 1. Trigger Hierarchy

When the user says "improve" / "次に何ができる?" or you finish a task and want to know what to
do next, walk this table top-to-bottom and act on the **first** matching row. One cycle = one
theme; do not parallelize.

| # | Trigger | Detection | Response |
|---|---------|-----------|----------|
| 1 | Test or lint failure | `uv run pytest tests/ -q` / `uv run ruff check src/ tests/ evals/` | Fix immediately. Merge-blocking. |
| 2 | Dogfooding regression | `uv run python evals/dogfood_regression.py` | Locate cause; either fix the code or, if change was intentional, `--update` baselines. |
| 3 | Telemetry alert | `uv run python evals/analyze_telemetry.py` | Apply the matching Operations Rule from §4. |
| 4 | `[STALE]` lesson tag | Quarterly audit of `docs/LESSONS.md` | Remove the entry; clean up any code/tests that referenced it. |
| 5 | Open Improvement Backlog | §5 of this file | Pick the highest-priority item and start a new cycle. |
| 6 | (empty) | — | Refactor, dependency bump, or documentation audit. |

**Autonomous mode:** when invoked without specific instructions, run triggers 1 → 6
in order. Report which trigger matched and what you intend to do **before** writing code.

---

## 2. Definition of Done

A self-improvement task is complete only when **all five** boxes are checked. Anything less
is incomplete work, regardless of how it feels.

- [ ] **Measurable.** Before/after can be compared with a number (tokens, score,
      failure rate, latency). No vibes.
- [ ] **Regression-tested.** A test exists that would have failed before the patch
      and passes after. Run it both ways to prove.
- [ ] **Gates green.** `pytest -q` + `ruff check` + `dogfood_regression.py` all pass.
- [ ] **Docs synced.** The relevant entries in `CLAUDE.md` §4 (Documentation Sync) are
      satisfied: CHANGELOG, README/ARCHITECTURE/MAINTENANCE as needed.
- [ ] **Lesson extracted.** The change is generalized into a single rule in `docs/LESSONS.md`
      tagged `[ACTIVE]`. If you cannot generalize, the bug fix is too narrow — broaden it
      or note explicitly why.

---

## 3. Anti-Patterns

Each of these has cost time in past sessions. Re-read this list whenever you start an
improvement cycle.

- ❌ **Multiple improvements in flight at once.** You lose the ability to attribute
  which patch helped. One cycle, one theme.
- ❌ **"Obviously correct" fix with no test.** Future-you will not remember why it was
  obvious. Write the test even when the fix is one line.
- ❌ **Code before test.** During the Dogfooding cycle the four noise leaks were
  patched correctly only after we wrote failing tests against the fixtures first.
  Inverting the order works less reliably.
- ❌ **Trusting aggregate metrics alone.** `eval_judge` and telemetry catch
  **frequency** issues. Semantic noise (specific ad copy, brand-named CTAs) only
  surfaces through dogfooding inspection. Run both probes. The semantic probe is
  now **systematic, not eyeball-only**: `evals/dogfood_audit.py` flags suspected
  residual noise as a shortlist (STEP 4 of `dogfood_research.py`). Still review
  its findings by hand — the auditor proposes, the human disposes — but a clean
  auditor run is the floor, not the ceiling.
- ❌ **Append-only Lessons Learned.** Stale knowledge actively misleads new
  contributors. The quarterly audit (§6) is not optional.
- ❌ **Mistaking fixtures for real usage.** Hand-written HTML fixtures only
  contain noise you already anticipated, so a Check that runs solely on them is
  self-referential — it confirms, never surprises. The 2026-05-30 real-web pass
  found two bugs (auditor false-positive on a comma; Wikipedia citation leak)
  in minutes that the fixture corpus had never exposed. Run `scripts/live_check.py`
  against the live web periodically and **read the output as a user**; fold
  findings back into fixtures/patterns.

---

## 4. Operations Rules (telemetry alert → patch mapping)

Each rule responds to one of the `🛠 SUGGESTED ACTIONS` lines printed by
`evals/analyze_telemetry.py`. Detailed step-by-step playbooks for each rule live in
[MAINTENANCE.md](MAINTENANCE.md) §"Responding to analyzer alerts".

### Rule 1 — Domain failure rate ≥ 15 % → add a domain adapter
- **Trigger:** "EXTRACTION FAILURE HOTSPOTS" shows `⚠️` for a domain.
- **Patch:** add a new entry to `_DOMAIN_PREPROCESSORS` in `core/extractor.py` that
  decomposes the offending DOM selectors before trafilatura runs.
- **Match key:** `hostname == suffix` OR `hostname.endswith("." + suffix)`.
- **Reference impl:** `_substack_preprocess` and `_medium_preprocess` (Phase 6).
- **Test requirement:** mirror `tests/test_extractor.py::TestSubstackAdapter` — (a) noise
  removed, (b) prose preserved, (c) other domains unaffected, (d) subdomains route.

### Rule 2 — Average tokens ≥ 3000 / article → investigate residual noise
- **Trigger:** "TOKEN INEFFICIENCY" shows `⚠️` for a successful-status domain.
- **Patch:** inspect a sample, then either add a regex to `utils/cleaner.py`
  `_NOISE_LINE_RE` (generic phrase) or add a domain preprocessor (site-specific DOM).
- **False-positive risk:** legitimately long articles (Wiki etc.). Spot-check samples
  before adding a pattern.

### Rule 3 — `search_web` `RATE_LIMITED` ≥ 30 % of errors → tighten cache / jitter
- **Trigger:** "ERROR PATTERN ANALYSIS" shows `(search_web, RATE_LIMITED)` at ≥ 30 %.
- **Patch (in order):**
  1. `core/cache.py` `TTL_SEARCH` 86 400 → 172 800 (48 h).
  2. `tools/search.py` `_JITTER_MIN, _JITTER_MAX` 0.5, 1.5 → 1.0, 3.0.
  3. Last resort: rotate `region` parameter at the agent layer.
- **Note:** `RATE_LIMITED` is already `retryable=True`; agents recover, but a high
  rate signals systemic noise.

### Rule 4 — `read_article` `BLOCKED_403` ≥ 50 % of errors → add an impersonate target
- **Trigger:** `(read_article, BLOCKED_403)` ≥ 50 %.
- **Note:** `core/http.py` already auto-rotates `chrome131` → `safari17_0` on a
  block (B17). A *persistent* high BLOCKED_403 rate means **both** fingerprints
  are blocked — add a third target to `_IMPERSONATE_TARGETS` (e.g. a newer
  Chrome/Firefox build) rather than swapping the primary.
- **Patch:** append to `_IMPERSONATE_TARGETS`; confirm the build exists via
  `python -c "from curl_cffi.requests import BrowserType; print([b.name for b in BrowserType])"`.
- **Regression check:** `pytest tests/test_extractor.py::TestGauntletScores` must
  keep avg ≥ 8.5/10. Newer fingerprints sometimes trigger different anti-bot logic.

### Rule 5 — Same `input_summary` repeats ≥ 10× per hour → agent-side loop
- **Trigger:** agent-loop SQL in `MAINTENANCE.md` returns hits.
- **Patch:** **do not change the server.** The cache already deduplicates legitimate
  repeats. Add the failing pattern as a `Bad (…) → use Y instead` Few-Shot example
  in the offending tool's docstring so future agents are warned.

---

## 5. Open Improvement Backlog

Priority order. When trigger 5 fires (§1), pick the topmost item.
When you discover a new improvement opportunity but don't have time to act, **add it
here** — the backlog's existence is what prevents "what do I do next?" paralysis.

| # | Improvement | Expected impact | Blocked on |
|---|-------------|-----------------|------------|
| **B1** | Calibrate `eval_judge` scores against human ratings (10 articles, Pearson correlation) | Verifies the 8.5 threshold actually means "good", not "good on these 3 axes" | Human availability for scoring |
| **B2** | Add `patch_landed_at` column to `telemetry` schema | Measures MTTI (mean time to improvement) per alert | Next schema migration |
| **B3** | Expand the adversarial fixture corpus from 5 to 10+ sites | Better representativeness; catches patterns earlier than dogfooding does | Monthly review window — *partially advanced 2026-05-29: added `zdnet` dogfood fixture (affiliate/social-rail noise)* |
| **B4** | Telemetry diff report between two `telemetry.db` snapshots | Quantifies inter-release improvement / regression | Two consecutive releases of data |
| ~~**B5**~~ | ~~Add a "noise leak hint" check to `analyze_telemetry.py`~~ | — | **✅ DONE 2026-05-29 (relocated)** — see note below |
| **B6** | Operations Rule 6 — flag ±10 % extraction length variance between releases | Catches silent trafilatura/readability behavior drift independently of dogfooding | B4 done first |
| ~~**B7**~~ | ~~Auto-propose a candidate `_NOISE_LINE_RE` regex from each auditor finding~~ | — | **✅ DONE 2026-05-29 (reframed)** — see note below |
| **B8** | Silence the intermittent `PytestUnhandledThreadExceptionWarning` in `test_telemetry.py` (fire-and-forget aiosqlite write races with event-loop teardown) — await `telemetry.drain()` in an autouse fixture | Clean test output; no benign-warning fatigue | — (discovered 2026-05-29, benign, prod unaffected) |
| ~~**B9**~~ | ~~Strip "Part of a series on" / infobox nav-template tables~~ | — | **✅ DONE 2026-05-30** — `strip_leading_wiki_chrome`: removes a *leading* table carrying a high-precision infobox/nav marker. Mid-article + unmarked + prose-first bodies untouched (no baseline drift). |
| **B10** | Capture a few representative *live* pages (wiki w/ citations, code docs) as permanent regression fixtures | Pins real-world patterns so `live_check` findings don't regress | Pages change — snapshot HTML, don't fetch live in tests. **Declined 2026-05-30: full-page snapshots bloat the repo and would golden-freeze the unfixed B9 leak; strip logic is unit-tested + live_check covers integration.** |
| **B11** | `suggest_queries`: now that live autocomplete works, its 4 phrases crowd out the primary-source templates (`site:github`, `site:arxiv`) under the 8-cap — undercutting the echo-chamber mission. Reserve slots so ≥1 criticism + ≥1 primary-source template always survive | Keeps the tool's lateral-thinking differentiator when autocomplete is live | — (surfaced 2026-05-30 once the dead autocomplete was fixed). **Reinforced by the Sam Altman research run: real autocomplete = "net worth / husband / sister / age" — tabloid noise, actively harmful for research.** |
| ~~**B12**~~ | ~~Workflow single point of failure: search down ⇒ whole loop dies~~ | — | **✅ DONE 2026-05-30** — `_ddg_html_fallback` scrapes `html.duckduckgo.com` directly when the bing-routed library fails. Verified live: search (and the Sam Altman task) now works where it was fully dead. |
| **B13** | `search_web` CONN_ERROR hint says "retry / broaden query / check spelling" — but a durable backend outage is fixed by none of those. The agent wastes turns rewording. Hint should hedge toward "if every search fails, the backend may be down — switch strategy" for systemic failures | Stops agents looping on reword-and-retry during an outage | — (Sam Altman run; relates to the skew guard: 100%-failing tool = systemic, not per-query) |
| **B14** | "Recent / time-sensitive" queries have no freshness signal: `published_date` is always null (DDGS), so an agent can't filter for recency on time-critical research | Time-sensitive Deep Research (schedules, breaking news) is better supported | — (Sam Altman "recent schedule" run; reconfirmed Meta run) |
| ~~**B15**~~ | ~~No source-quality signal — agent can't tell a content farm from Reuters~~ | — | **✅ DONE 2026-05-30** — `source_tier` (`authoritative`/`unknown`) on every result via `core/source_quality.py`. High-precision allowlist; does NOT guess `low_quality`. Verified live on a Llama 4 search. |
| ~~**B16**~~ | ~~Near-duplicate results waste reads~~ | — | **✅ DONE 2026-05-30** — `near_duplicate` flag (conservative Jaccard ≥ 0.6). **Mark, never remove** — count = corroboration. Cluster primary prefers authoritative (B15 synergy). |
| ~~**B17**~~ | ~~The trust signal points at sources we can't read (Reuters fails)~~ | — | **✅ DONE 2026-05-30** — `core/http.py` rotates fingerprint chrome131→safari17_0 on 401/403. Diagnosed: Reuters 401 to Chrome, 200 to Safari. `read_article` now fetches Reuters. (Also fixed 401→BLOCKED_403 mis-mapping.) |
| ~~**B18**~~ | ~~B9 misses company/website/org infoboxes (DuckDuckGo leaks)~~ | — | **✅ DONE 2026-05-30** — added company/website markers ("type of site", "area served", "key people", "number of employees", "current status", "traded as"). Excluded "headquarters"/"founder"/"launched" (can be comparison-table columns). DDG now opens with prose. |
| ~~**B20**~~ | ~~Mojibake on non-UTF-8 pages (soumu.go.jp Shift_JIS → garbage)~~ | — | **✅ DONE 2026-05-30** — `decode_html` detects charset (header → `<meta>` → detector → utf-8) and decodes from bytes. soumu.go.jp now reads as clean Japanese (0 mojibake). |
| ~~**B21**~~ | ~~`source_tier` allowlist is US/UK-centric (.go.jp tagged unknown)~~ | — | **✅ DONE 2026-05-30** — `_AUTH_TLDS` extended to JP/FR/DE/EU/IN/KR/etc. government & academic TLDs (geographic `.<pref>.jp` excluded). soumu.go.jp now `authoritative`. |
| **B22** | **B16 tokenizer is ASCII-only.** `_title_tokens` uses `[a-z0-9]+`, so a pure-Japanese (CJK / any non-Latin) title yields ~no tokens → `near_duplicate` is broken for Japanese results (the 辺地共聴 subsidy listicles repeated across 6+ aggregators, undetected). Use a Unicode word pattern (`\w` with re.UNICODE) | Dedup works for non-English research | — (辺地共聴 run, 2026-05-30) |
| **B19** | **B16 misses loose same-story clusters.** The "DuckDuckGo +30% installs after Google AI" story ran across 8+ sources (TechCrunch/Breitbart/Futurism/BI/9to5mac/MacRumors/Cybernews) but none were flagged `near_duplicate` — the headlines vary enough that title-Jaccard < 0.6. Consider clustering on shared entities/keywords, not just title overlap | Loose-but-real story clusters are surfaced as corroboration | — (DuckDuckGo run; intentional B16 conservatism, but a real miss) |

> **B5 post-mortem (a methodology bug we fixed).** B5 was specified to live in
> `analyze_telemetry.py`. That is architecturally impossible: `telemetry.db`
> stores no response bodies — only a status, a token *count*, and a truncated
> input summary (privacy/size design). The analyzer has nothing to scan.
> The noise-leak detector must live where bodies exist: the **dogfooding path**.
> It now ships as `evals/dogfood_audit.py` (`audit_markdown()`), wired into
> `evals/dogfood_research.py` as STEP 4. Lesson: **a backlog item can encode a
> wrong architectural assumption; validate feasibility against the data model
> before estimating, not after.**

> **B7 reframe (built the useful half, not the obvious half).** B7 read
> "auto-propose a regex." But generating a regex string is *not* an agent's
> bottleneck — an LLM writes one in seconds. The error-prone, tedious part is
> proving the pattern is **not too broad** (a `_NOISE_LINE_RE` alternative that
> matches real prose silently eats article content). So `scripts/propose_noise_regex.py`
> is a **safety preview**: it generalizes a candidate (numbers → `\d+`, no
> trailing-`\b`-after-punctuation), confirms it matches the offending line, and
> reports its **blast radius** across the live fixtures — flagging any prose it
> would remove. The agent keeps the judgment (noise vs prose, generic vs DOM);
> the tool removes the verification toil. Lesson: **when automating an agent's
> task, automate the part the agent is bad at (mechanical verification), not
> the part it is good at (generation).**

---

## 6. Audit Cadence

| Interval | Action | Owner |
|----------|--------|-------|
| Daily | Run `analyze_telemetry.py`. Zero ignored alerts. | Operator / on-call |
| Weekly | Run `dogfood_regression.py`. Investigate any drift. | Maintainer |
| Monthly | Re-read this file. Pick one Backlog item and start a cycle. | Maintainer |
| Quarterly | Re-tag every entry in `docs/LESSONS.md`. Drop `[STALE]`. Check dependencies for major-version bumps. | Maintainer |

The audit cadence is not optional. A methodology you never re-read is just a snapshot.
