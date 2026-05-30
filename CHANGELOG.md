# Changelog

All notable changes to **DeepSearch-MCP** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Maintenance rule:** every code change that affects user-visible behavior,
> tool I/O, error contract, or operational characteristics MUST add an entry
> here under `## [Unreleased]` before the change is merged.

---

## [1.0.0] — 2026-05-29

First release-ready version. All six development phases complete.
204/204 tests pass; 0 ruff errors; full operational tooling in place.

### Added

#### Phase 0 — Foundation
- `evals/eval_judge.py`: 0–10 quality scorer with three axes
  (noise ratio, Markdown structure, content density).
- 16-test `tests/test_judge.py` suite covering scoring edge cases.

#### Phase 1 — Clean Room extraction
- `tools/read_article` MCP tool with a 3-stage pipeline:
  trafilatura → readability-lxml fallback → cleaner sanitization.
- `core/http.py`: `curl_cffi` stealth fetcher with `impersonate="chrome131"`,
  exponential backoff, and structured `FetchError` codes.
- `core/extractor.py`: BeautifulSoup pre-scan to preserve code-block
  language annotations that trafilatura v2 strips.
- `utils/cleaner.py`: `deduplicate_blocks()` removes the duplicate
  content trafilatura emits for `<article>` / `<main>` landmarks.
- 5-category extraction gauntlet (News / Blog / TechDocs / Wiki / Recipe-SEO);
  average quality score ≥ 8.5 / 10.

#### Phase 2 — Shield & Cache
- `tools/search_web` MCP tool wrapping `duckduckgo-search` v8
  (sync API → `asyncio.to_thread`).
- `core/cache.py`: aiosqlite-backed response cache.
  Search results: 24 h TTL; article content: 7 d TTL.
- `core/errors.py`: `StructuredError` model + 5 error codes
  (`BLOCKED_403`, `RATE_LIMITED`, `TIMEOUT`, `EMPTY_CONTENT`, `CONN_ERROR`).
- Chaos-engineering tests: every DDGS exception path maps to a structured
  error JSON, never a traceback.

#### Phase 3 — Navigator (lateral thinking)
- `tools/suggest_queries` MCP tool.
  - DDG `/ac/` autocomplete + `_VIEWPOINT_TEMPLATES`
    (criticism / alternatives / primary sources / temporal).
  - Proper-noun entity extraction from context snippets.
- `utils/date_parser.py`: URL-path and article-body date fallback
  (`extract_date_from_url`, `extract_date_from_text`, `best_effort_date`).
- "Stuck Agent" simulation tests verify echo-chamber breakage.
- Few-Shot docstrings on all three tools.

#### Phase 4 — Field Operations
- `evals/simulate_research.py`: end-to-end ReAct loop simulator
  with both `--demo` (offline) and live modes.
- `read_article` rejects non-HTML resources with
  `UNSUPPORTED_FORMAT` (URL-extension + Content-Type guards).
- First `README.md` covering Quick Start and MCP client config
  (Claude Desktop, Claude Code, Cursor, VS Code).

#### Phase 5 — Adversarial Dogfooding
- Smart quoting in `suggest_queries`: topics with ≥3 words are rendered
  bare (no quote-wrapping), fixing the "0-hit composability" bug.
- `errors.sanitize_error_text()`: strips raw URLs and truncates to
  ≤ 200 chars; never leak Bing-internal query-string noise to the agent.
- `errors.is_transient_conn_error()` detects DNS / timeout / reset patterns;
  affected `CONN_ERROR` and `TIMEOUT` rows now return `retryable=True`.
- `structured_error(hint_override=…, retryable_override=…)`:
  tool-specific recovery hints from the same error code.
- `_strip_redundant_h1()` in `core/extractor.py`: removes a body H1 that
  duplicates the frontmatter `title:` (≈ 5–10 % token savings per article).
- 27 new regression tests under `TestSmartQuoting`,
  `TestErrorSanitization`, `TestTransientErrorDetection`,
  `TestSearchWebContextAwareHints`, `TestH1Deduplication`.

#### Phase 6 — Day 2 Operations
- `core/telemetry.py`: SQLite-backed `@track(tool_name, primary_input)`
  decorator. Records `(timestamp, tool_name, input_summary, status,
  tokens_approx, latency_ms, domain)` via fire-and-forget
  `asyncio.create_task`. Strong-ref `_pending_tasks` set prevents GC.
- `evals/analyze_telemetry.py` CLI with 3 reports
  (failure hotspots / token inefficiency / error patterns) +
  auto-generated SUGGESTED ACTIONS.
- `evals/generate_dummy_telemetry.py`: seeded synthetic data generator
  for analyzer regression testing.
- `core/extractor.py`: `_DOMAIN_PREPROCESSORS` mechanism for site-specific
  noise stripping. Initial adapters for `substack.com` (subscription
  widgets) and `medium.com` (member-only walls).
- `tests/conftest.py`: `DEEPSEARCH_TELEMETRY=0` by default so test runs
  never pollute the live telemetry DB.
- 28 telemetry tests + 10 domain-adapter regression tests.

### Changed

- `eval_judge.py` now counts frontmatter `title:` as an implicit H1 for
  heading-levels structure scoring, so H1 deduplication does not fight
  the quality scorer.
- `_VIEWPOINT_TEMPLATES` in `tools/suggest.py` reordered to put the
  `"{topic} 2025 OR 2026"` freshness query at position 0.
- Tool docstrings rewritten with quantitative USE-WHEN triggers
  ("last 2+ rounds returned same sources") and the alternative tool
  named in DO-NOT-USE-WHEN clauses.
- `search_web`'s empty-query error switched from `CONN_ERROR` to
  `EMPTY_CONTENT` (more semantically correct).
- DDGS `RuntimeWarning` ("duckduckgo_search → ddgs") is now suppressed.

### Fixed

- **C1 (Phase 5):** `suggest_queries` no longer wraps long topics in
  quotes, which previously guaranteed zero search hits when the agent
  fed the output back into `search_web`.
- **B1 (Phase 5):** error messages no longer leak raw Bing URLs with
  query-string filters.
- **B2 (Phase 5):** `search_web` error hints no longer say "check URL
  validity" — the agent passed a query, not a URL.
- **B3 (Phase 5):** DNS / timeout failures now signal `retryable=true`
  so the agent retries instead of permanently abandoning the source.
- **D1 (Phase 5):** redundant body H1 stripped when it duplicates
  frontmatter title.

### Operational

- Five **Operations Rules** in `CLAUDE.md` Lessons Learned describe how
  to act on each analyzer alert (domain adapter, cache TTL, jitter,
  impersonate rotation, agent-loop detection).

---

## [Unreleased]

### Changed — Non-US/UK authoritative TLDs (2026-05-30, B21)
- `core/source_quality.py` `_AUTH_TLDS` extended beyond `.gov`/`.gov.uk`/`.edu`
  to national government & academic TLDs: `.go.jp`/`.lg.jp` (Japan),
  `.gov.au`/`.govt.nz`, `.gc.ca`/`.canada.ca`, `.gouv.fr`/`.bund.de`/
  `.admin.ch`/`.europa.eu`, `.gov.in`/`.gov.sg`/`.gov.br`/`.gov.za`/`.gov.cn`,
  `.go.kr`/`.gob.mx`/`.gob.es`, plus `.ac.kr`/`.edu.sg`. All registration-
  restricted, so precision stays high; the geographic `.<pref>.jp` municipal
  pattern is deliberately excluded (not gov-exclusive). Now **soumu.go.jp
  (総務省) is tagged `authoritative`** (it was `unknown`).
- Fixed a matching edge case: a trusted suffix that is itself a full domain
  (`canada.ca`, `europa.eu`) or a host equal to the suffix (`www.gov.in` →
  `gov.in`) now matches (`host == suffix OR host.endswith(suffix)`).

### Fixed — Charset-aware decoding / mojibake (2026-05-30, B20)
- `read_article` no longer returns mojibake for non-UTF-8 pages.
  `core/http.py::decode_html` decodes the raw bytes using the *declared* charset
  — HTTP `Content-Type` → HTML `<meta charset>` → detector
  (`charset_normalizer`) → utf-8 — instead of curl_cffi's utf-8 default.
  Diagnosed live on **soumu.go.jp** (総務省): the page is `Shift_JIS` with no
  HTTP charset header, so it had been decoding to garbage
  ("\| ����\\\\���� \|"). Now it reads as clean Japanese (0 mojibake chars).
- `Shift_JIS` is mapped to `cp932` (a tolerant superset). Defensive: a
  non-bytes `.content` (test mock) falls back to `resp.text`; a bogus declared
  charset falls back to utf-8 without crashing.
- This unblocks Japanese government / legacy sites — the *primary* authoritative
  sources for Japanese-policy research, which had been unreadable. Tests:
  `tests/test_http.py::TestDecodeHtml`.

### Fixed — Leading Wikipedia chrome (2026-05-30, B9)
- `read_article` no longer opens real Wikipedia articles with the infobox /
  "Part of a series on" nav template dumped as a messy leading markdown table
  ("Sam Altman | | |---|---| | Born | … |"). `utils/cleaner.py
  ::strip_leading_wiki_chrome` removes a **leading** table (before the first
  prose sentence) that carries a high-precision infobox/nav marker.
- **Safety:** it strips *only* the leading region and *only* with a known
  marker — a legit leading data table **without** a marker, a prose-first body,
  and any mid-article table are all left untouched (verified by tests + the
  dogfood golden baselines, which did not drift). Verified live: Sam Altman,
  Mitoma, and LLM articles now open with real prose.
- **B18 (same day):** extended the markers to **company / website / org
  infoboxes** ("Type of site", "Area served", "Key people", "Number of
  employees", "Current status", "Traded as") after the DuckDuckGo article still
  leaked its infobox. Deliberately excludes generic words ("Headquarters",
  "Founder", "Launched") that can be *columns* in a legit company comparison
  table — verified that such a table is preserved.

### Added — Near-duplicate flagging (2026-05-30, B16)
- `search_web` results carry a `near_duplicate` flag: `true` when a result's
  title closely matches an earlier one (same story/listicle). Conservative
  Jaccard (≥ 0.6 on significant title tokens) so it only catches high-confidence
  matches. **Key design call: mark, never remove.** Near-duplicates are kept —
  their *count* is corroboration (in the Mitoma run, 6 independent sources
  saying "out of the squad" was a reliability signal, not waste). The agent
  skips *re-reading* dups, not seeing them.
- Integrates with B15: the cluster **primary** (kept `near_duplicate=false`)
  prefers an `authoritative` source — so a wire-service copy outranks the SEO
  rewrites of the same story. Verified live (a "best open-source LLM" search
  flagged the clearest rewrite, kept the authoritative copy primary).
- Same-story-*different-angle* results (moderate overlap) are deliberately
  **not** flagged — they carry distinct corroboration. Tests in
  `tests/test_search.py` (`TestMarkNearDuplicates`, `TestTitleTokens`, `TestJaccard`).

### Fixed — Anti-bot fingerprint rotation (2026-05-30, B17)
- `core/http.py` now rotates the TLS impersonation fingerprint on a 401/403
  block: `chrome131` → `safari17_0`. Diagnosed live — Reuters returns **401 to
  chrome131/124/120 but 200 to safari17_0**. Rotation fires only on block
  statuses (cheap, no retry); genuine network errors surface immediately
  without being multiplied across fingerprints.
- `read_article` now **successfully fetches Reuters** (verified live: the
  jp.reuters.com Mitoma article and reuters.com/technology), so the
  `source_tier=authoritative` signal (B15) no longer steers the agent toward a
  source it can't read.
- Secondary fix: a **401 anti-bot block now maps to `BLOCKED_403`** (it was
  mis-mapped to `CONN_ERROR`, implying a network failure rather than a block).
- Tests: `tests/test_http.py` (rotation, all-blocked, no-rotate-on-success,
  no-multiply-on-network-error, 401→BLOCKED_403).

### Added — Source-quality signal (2026-05-30, B15)
- `search_web` results now carry a `source_tier` field: **`authoritative`**
  (curated allowlist of wire services / reputable tech press / academic+primary
  sources / official company blogs, plus `.gov`/`.edu`/`.ac.uk` TLDs) or
  **`unknown`** (everything else). New `core/source_quality.py::classify_source`
  (subdomain-aware, `www`-stripping, lookalike-domain-safe).
- **Honest scope:** we tag `authoritative` with high precision but never guess
  `low_quality` — a content farm and a legit small blog are structurally
  identical, so a confident "low quality" label would defame real sites.
  "Absence of authoritative" is the signal. Verified live: a real "Llama 4"
  search tagged `ai.meta.com`, `wikipedia.org`, `huggingface.co` authoritative
  and the 5 SEO blogs `unknown` — the agent now reads primary sources first.
- The `search_web` docstring RETURNS documents the field and how to use it.

### Added — Search resilience (2026-05-30, B12): direct-DDG fallback
- `search_web` now survives a dead primary backend. The `duckduckgo-search`
  library proxies every backend through `bing.com`; when bing is unreachable
  (regional block / outage) the whole tool died with `CONN_ERROR`. On any DDGS
  failure, `_ddg_html_fallback` now scrapes DuckDuckGo's **own** endpoint
  (`html.duckduckgo.com`) directly via the stealth `fetch`, parsing
  `div.result` → `result__a`/`result__snippet` and decoding the `uddg=`
  redirect to the real URL. **Verified live: search — and the originally-blocked
  "Sam Altman recent schedule" research task — now works where it was fully
  dead.** Tests mock at the `fetch` boundary (`TestDdgHtmlFallback`,
  `TestSearchWebFallbackWiring`, `TestDecodeDdgHref`).

### Fixed — test isolation
- `tests/conftest.py` now points `DEEPSEARCH_CACHE_DIR` at a throwaway temp dir.
  A live `search_web` run caches real results in `./.cache`; without isolation
  those leaked into error-path tests expecting a cache miss → flaky,
  order-dependent failures. Tests no longer read or pollute the real cache.

### Fixed — Dead autocomplete (2026-05-30, found by running the real search tool)
- `suggest_queries` autocomplete had **never worked**: `_fetch_autocomplete`
  called `https://duckduckgo.com/ac/` with **no `?q=` query parameter**, so the
  topic was never sent — it silently returned `[]` and fell back to templates
  forever. The "real user search patterns" feature was dead since Phase 3.
  Fix: `_autocomplete_url()` builds `?q=<urlencoded topic>` (and deliberately
  omits `&type=list`, which returns an OpenSearch shape the parser can't read).
  Verified live: now returns real phrases (`vector database llm`,
  `python asyncio gather`, …).
- The Stuck Agent tests **mocked `_fetch_autocomplete` itself**, so they stayed
  green while the real function was broken. Added `TestAutocompleteRequest`
  which mocks `fetch` (the boundary) and asserts the topic reaches the URL —
  the test that would have caught it.
- Tightened the helper's `except (FetchError, Exception)` (redundant) to
  `except Exception` with a comment that best-effort enrichment degrades to
  templates on any failure.

### Added — Real-usage Check (2026-05-30): tools vs the live web
- `scripts/live_check.py` — runs the **real** `read_article` over curated live,
  diverse pages (code docs / spec / wiki / product docs), audits each, and
  prints samples to read critically. Makes "actually use it on the real web"
  a one-command habit instead of an ad-hoc afterthought. Not a gate (the web
  is non-deterministic); a periodic probe whose findings become fixtures /
  cleaner patterns. *Self-authored fixtures only contain noise you already
  thought of — the loop's Check was self-referential until this.*
- `utils/cleaner.py::strip_reference_markers` + `TestCitationMarkers` — strips
  Wikipedia-style inline citation superscripts (`[1]`, `[12]`) from prose,
  while **preserving** array indices in code (`arr[1]`, `items[0]`, fenced and
  inline). Found by reading a real Wikipedia extraction.
- Editorial-annotation stripping (`_EDITORIAL_RE`): `[citation needed]`,
  `[update]`, `[note 1]`, `[dubious – discuss]`, etc. — via an **allow-list**,
  not a blanket `[word]` strip, so real NLP tokens `[MASK]` / `[UNK]` / `[CLS]`
  (content!) survive. Found inspecting real LLM/Transformer wiki pages; the
  `[MASK]`-vs-`[citation needed]` distinction is exactly the nuance a
  self-authored fixture could never contain.

### Fixed — Real-usage Check
- `evals/dogfood_audit.py` false positive: the social-count heuristic's
  `[\d.,]+` matched a bare comma, so real prose ("…concurrency, like") flagged
  as ENGAGEMENT_BAIT. Now requires a leading digit (`\d[\d.,]*`). Found on the
  first live run against `docs.python.org`.
- Inline citation markers no longer pollute extracted prose (see above).

---

### Added — Aggregate-half activation (2026-05-30)
- `scripts/collect_telemetry.py` — bootstraps the dormant *aggregate* probe by
  driving the **real** tools over a curated battery (success / 403 / 5xx / DNS /
  unsupported-format outcomes) so `telemetry.db` fills with production-shaped
  data, then hands off to `analyze_telemetry.py`. First real run (9 rows)
  surfaced `httpbin.org` as a genuine 403 hotspot and the blocked DDGS→bing
  backend as `search_web` 100% CONN_ERROR — the aggregate probe working as
  intended.
- `tests/test_analyze_telemetry.py` — 8 tests pinning the new cold-start verdict
  logic; `tests/test_scripts.py` gained collector smoke tests.

### Changed — Aggregate-half activation
- `evals/analyze_telemetry.py` cold-start hardening: below
  `MIN_ROWS_FOR_CONFIDENCE` (50) rows the report prints a **LOW CONFIDENCE**
  banner, labels alerts **PROVISIONAL**, and states that "no alerts" is *not
  yet* "healthy". Motivated by the real 9-row run, where the old code
  confidently recommended a domain adapter off 3 samples.
- `evals/analyze_telemetry.py` **representativeness guard** (`tool_skew`): a
  tool that is ≥90% one non-success status (e.g. a dead backend → 100%
  `CONN_ERROR`) keeps verdicts PROVISIONAL *regardless of row count*. Closes the
  "re-run the collector to cross 50 rows → false green" trap that
  `collect_telemetry.py` would otherwise have created. (Declined to manufacture
  rows to clear LOW CONFIDENCE — that would game the guard rather than earn the
  verdict.)

---

### Added — Backlog B7 (2026-05-29): regex safety-preview proposer
- `scripts/propose_noise_regex.py` — turns an auditor finding into a *vetted*
  cleaner pattern. Reframed from the backlog's "auto-write a regex" (low value;
  an LLM writes regex easily) to a **safety preview**: it generalizes a
  candidate (numeric counts → `\d+`; no trailing-`\b`-after-punctuation), and
  reports the candidate's **blast radius** across the live fixtures, *failing
  if it would match any already-clean prose* — the cleaner's worst failure mode
  (silently eating content). The agent keeps the judgment; the tool removes the
  verification toil.
- `evals/dogfood_audit.py` gained `matched_signal()` (exposes the matched
  substring, not just the line) so the proposer can generalize around the
  salient phrase.
- `tests/test_scripts.py` / `tests/test_dogfood_audit.py` extended (number
  generalization, trailing-`\b` guard, blast-radius flags prose, `matched_signal`).

---

### Added — Agent DX cycle (2026-05-29): orientation, gate, docs map
- `scripts/status.py` — one-call live orientation for the maintaining agent
  (test count, lint state, golden-fixture count, lesson tag tally, last audit
  date, next open backlog item). **Computed, never stored** — a committed
  `STATUS.md` would itself drift, recreating the staleness problem it solves.
- `scripts/verify.py` — the single merge gate (pytest + ruff +
  dogfood_regression + docs-link check) with one exit code, so an agent cannot
  forget one. Environment-robust: auto-detects `.venv/bin/` rather than
  assuming `uv` is on PATH.
- `scripts/docs_map.py` — *generated* documentation map (each doc's role +
  purpose) plus an integrity checker: dead relative-link detection (fails
  `--check`, gated by `verify.py`) and orphan detection (warns; intentionally
  standalone docs are allow-listed). On first run it caught two real issues —
  `ROADMAP.md` / `BASELINE.md` were orphaned, and `ROADMAP.md`'s header still
  read "Phase 0 (Initialization)".
- `tests/test_scripts.py` — 23 tests covering the gate runner, status readers,
  and docs-map parsing/integrity.
- `CLAUDE.md` gained a top-of-file **🧭 Orientation** block pointing the next
  agent at `status.py` / `verify.py` / `docs_map.py` before it trusts a stale
  mental model.

### Changed — Agent DX cycle
- `docs/MAINTENANCE.md` "Test gate before any merge" now points at
  `scripts/verify.py` instead of three separately-typed `uv run …` commands
  (net fewer commands; one source of truth). Documents the `uv`-not-on-PATH
  caveat.
- `docs/ROADMAP.md` header de-staled ("Phase 0 (Initialization)" →
  "Day 2 Operations (post-v1.0.0)") and linked from `CLAUDE.md` §6 so it is
  no longer an orphan.
- `CLAUDE.md` §6 Quick-Reference gained rows for `ROADMAP.md` and `docs_map.py`.

---

### Added — Dogfooding cycle 2 (2026-05-29): Noise-Leak Auditor
- `evals/dogfood_audit.py` — the systematic CHECK step of the dogfooding loop.
  `audit_markdown()` scans post-cleaner extraction output for residual noise
  the cleaner missed, replacing the old "human reads the whole body and hopes
  to notice" step with a reproducible shortlist. Two-tier heuristics: STRONG
  signals (affiliate / sponsor / legal) fire at any line length; SOFT signals
  (promo CTA / metadata stub / engagement counts) fire only on short lines so
  real prose is spared. Wired into `dogfood_research.py` as STEP 4.
- `tests/test_dogfood_audit.py` — 24 tests (strong/soft tiers, structural
  skipping, false-positive guards, real-fixture integration).
- New `zdnet` dogfood fixture + golden baseline (affiliate disclosure +
  social-share rail), advancing backlog item B3.
- Cleaner regression tests `test_affiliate_disclosure_stripped` /
  `test_paid_partnership_stripped` in `tests/test_extractor.py`.

### Changed — Dogfooding cycle 2
- `utils/cleaner.py` `_NOISE_LINE_RE`: 4 new alternatives for affiliate /
  sponsorship disclosures (`affiliate links`, `may earn a commission`,
  `this article/post contains affiliate`, `paid partnership/promotion`).
  These are full sentences, so the auditor's STRONG (length-independent)
  tier was required to surface them — the length-gated heuristic and the
  human eyeball had both missed the 16-word disclosure line.
- `docs/METHODOLOGY.md`: backlog B5 marked DONE + relocated (with post-mortem
  on why it was mis-specified for `analyze_telemetry.py`), B3 advanced,
  B7 added; §3 anti-pattern updated to note the semantic probe is now
  systematic (auditor proposes, human disposes).

### Fixed — Dogfooding cycle 2
- ZDNet-style review articles no longer leak the affiliate-disclosure
  sentence ("This article may contain affiliate links…"). Measured: the
  auditor reported 1 suspected line before the patch, 0 after.

---

### Added — Dogfooding cycle 1
- `evals/dogfood_research.py` — repeatable dogfooding harness that runs the
  three tools through a realistic 2026 research scenario (AI agent framework
  hegemony + MCP standardization) and persists real telemetry rows for
  SRE analysis. Uses inline HTML fixtures + mocked `fetch` for the
  network-restricted parts so the entire `@track` pipeline is exercised
  end-to-end.
- 10 regression tests under `TestDogfoodingNoisePatterns` in
  `tests/test_extractor.py` covering the noise patterns observed in the
  first dogfooding session (`estimated reading time`, `listen to this
  article`, `continue reading to …`, `by signing up`, `get the latest
  … inbox`, `tags:`, `posted in:` and a control test that confirms
  clean prose is preserved).

### Changed — Dogfooding cycle 1
- `utils/cleaner.py` `_NOISE_LINE_RE`: 11 new regex alternatives covering
  2026-style article boilerplate that the v1 set missed. Tested directly
  against TechCrunch and LangChain-blog-style fixtures used in the
  dogfooding session. The full Phase 1 Gauntlet quality average remains
  ≥ 8.5 (verified by `test_dogfooding_gauntlet_quality_maintained`).

### Fixed — Dogfooding cycle 1
- TechCrunch-style articles no longer leak "Estimated reading time:
  8 minutes", "Listen to this article on the … Podcast", or the
  "Written by … — Senior Correspondent" byline duplicating the
  frontmatter author field.
- LangChain-blog-style articles no longer leak the "Continue reading
  to see …" lazy-load gate or "Tags: …" / "Posted in: …" footers.
- Newsletter consent gates ("By signing up, you agree to our Terms")
  and "Get the latest … in your inbox" CTAs are now stripped.

### Documentation hygiene

- **CLAUDE.md slimmed 485 → 160 lines** (66 % reduction). The file was violating
  its own Prime Directive 1 — Lessons Learned and Operations Rules were
  reloaded into every agent session even when irrelevant. Now CLAUDE.md
  contains only the always-needed material (Prime Directives, Tech Stack,
  Implementation Standards, Build-Eval-Learn workflow, anti-patterns) plus
  a Quick-Reference index pointing to the dedicated docs below.
- **`docs/LESSONS.md`** (new) — every Lessons Learned entry moved here with
  an index table at the top. Status tags (`[ACTIVE]` / `[HISTORICAL]` /
  `[STALE]`) preserved.
- **`docs/METHODOLOGY.md`** (new) — Self-Improvement Methodology (Trigger
  Hierarchy, Definition of Done, Anti-Patterns, Operations Rules 1–5,
  Open Improvement Backlog, Audit Cadence) consolidated in one place.
  Read this when starting an improvement cycle.

### Methodology (improvement of the improvement process)

- **Dogfooding regression harness** (`evals/dogfood_regression.py` +
  `tests/test_dogfood_regression.py` + `evals/dogfood_baseline/`):
  every previously-validated extraction is now a golden file. CI fails
  with a unified diff if any current run drifts. Mutation-tested by
  intentionally disabling a cleaner pattern and confirming the harness
  catches the regression. Converts dogfooding from one-shot anecdote
  into a permanent gate.
- **Lessons Learned status tags** (`[ACTIVE]` / `[HISTORICAL]` / `[STALE]`):
  every entry in `CLAUDE.md > Lessons Learned` now carries a tag and
  the section has an audit policy (quarterly cadence). Prevents stale
  knowledge from misleading future agents.
- **Self-Improvement Methodology section in CLAUDE.md**: codifies the
  trigger hierarchy for "what to improve next", a 5-item Definition of
  Done, 5 anti-patterns from past sessions, an Open Improvement Backlog
  (6 candidate projects), and an audit cadence. Replaces ad-hoc
  user-driven improvement with self-directed loop selection.

<!--
  Maintainers: copy the following template when starting work
  ---
  ## [Unreleased]
  ### Added
  ### Changed
  ### Deprecated
  ### Removed
  ### Fixed
  ### Security
-->

[1.0.0]: https://github.com/your-username/DeepSearch-MCP/releases/tag/v1.0.0
[Unreleased]: https://github.com/your-username/DeepSearch-MCP/compare/v1.0.0...HEAD
