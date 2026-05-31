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

### Fixed — status.py no longer lists a declined backlog row as "next" (2026-06-01, B27)
- `scripts/status.py` `next_backlog()` now skips `Declined` rows (a recorded
  won't-do is not actionable work), in addition to `DONE`/struck rows — B10 had
  been surfacing as the "Next backlog" item. The empty-backlog message also
  changed from the misleading "(none parsed)" to "(no open items — backlog
  clear)". `next_backlog()` is now text-injectable for deterministic tests.
- Tests: `tests/test_scripts.py::TestStatusReaders::test_next_backlog_excludes_declined`.

### Added — Operations Rule 6: extraction-length drift alert (2026-06-01, B6)
- `evals/telemetry_diff.py` now flags a `⚠ Rule 6` finding when `read_article`'s
  average successful-extraction token count drifts ≥ ±10% between two snapshots
  (with a ≥5-extraction-per-snapshot sample guard). This catches **silent
  trafilatura/readability behaviour drift** — e.g. a dependency bump that quietly
  extracts more boilerplate or truncates body — which single-snapshot telemetry
  and even dogfooding can miss in the wild.
- Codified as Operations Rule 6 (`docs/METHODOLOGY.md` §4) with a response
  playbook in `docs/MAINTENANCE.md`. Tests: `TestExtractionDriftRule6`.

### Added — telemetry_diff.py: before/after release comparison (2026-06-01, B4)
- `evals/telemetry_diff.py --before A.db --after B.db` diffs two telemetry
  snapshots and reports per-tool + overall deltas (success rate, tokens/call,
  latency) plus error-code churn, with regression findings (success-rate drop,
  new error codes). `--json` for machine output. Answers "did this release help
  or hurt?" — which the single-snapshot `analyze_telemetry.py` cannot.
- Carries the same cold-start guard: if either snapshot is below the row floor,
  the diff is labelled PROVISIONAL (don't act on a thin-data swing).
- Tests: `tests/test_telemetry_diff.py`.

### Added — story_cluster corroboration signal on search results (2026-06-01, B19)
- New `SearchResult.story_cluster` field: an integer id grouping results that
  report the **same story across different outlets**. It links paraphrased
  headlines that share ≥2 significant title tokens (e.g. the DuckDuckGo +30%
  installs story that ran across 8 outlets with varied headlines), which the
  stricter `near_duplicate` (title-Jaccard ≥ 0.6) misses.
- **Deliberately a corroboration signal, not a skip flag:** unlike
  `near_duplicate`, same-cluster results are worth reading across — the id tells
  the agent they corroborate one event and are *not* N independent sources. A
  loose false grouping is therefore low-harm. `near_duplicate` is unchanged.
- Tests: `tests/test_search.py::TestB19StoryClusters`.

### Added — search_web freshness signal via URL-derived published_date (2026-06-01, B14)
- `search_web` results now carry a best-effort `published_date` **derived from
  the result URL path** (news URLs embed `/YYYY/MM/DD/`), instead of always
  `null`. Applies to both the DDGS and HTML-fallback paths and reuses the
  existing `date_parser.best_effort_date`. Gives agents a recency signal on
  time-sensitive research (schedules, breaking news).
- **Precision:** the snippet body is intentionally NOT mined — a ~30-word
  excerpt's first date is too unreliable for a recency filter, so `published_date`
  stays `null` unless the URL itself carries a date. `null` ≠ "old".
- Tests: `tests/test_search.py::TestB14FreshnessSignal`.

### Changed — search_web hints escalate on a backend outage (2026-05-31, B13)
- `search_web` error hints no longer push "retry / broaden / check spelling" as
  if rewording could fix a backend outage. Base `CONN_ERROR` / `TIMEOUT` hints
  now hedge ("if searches keep failing it's the backend, not your query — switch
  strategy"), and the tool tracks consecutive live-search failures: once 3 in a
  row fail, the hint escalates to *"N searches in a row have failed — the backend
  is unavailable, stop rewording, switch strategy"* and `retryable` flips to
  `false` to break reword-and-retry loops. A single success resets the streak.
- Existing single-failure behavior (retryable timeouts/DNS errors) is unchanged;
  the escalation only triggers on a sustained run of failures.
- Tests: `tests/test_search.py::TestB13OutageEscalation`.

### Added — Cross-agent instruction pointers (2026-05-31)
- `AGENTS.md` (Codex / Cursor / Gemini / the cross-tool standard) and
  `.github/copilot-instructions.md` (GitHub Copilot) now point every AI agent at
  `CLAUDE.md` as the **single source of truth**, instead of duplicating rules.
  The pointers are static (they never need editing), so there is no two-file
  sync burden: rules are maintained only in `CLAUDE.md`. Each pointer surfaces
  the non-negotiables an external agent is most likely to skip (Prime
  Directives, the 5-box Definition of Done, the BLOCKING Documentation Sync
  rule, and running `python scripts/verify.py`).

### Changed — suggest_queries reserves slots for echo-chamber angles (2026-05-31, B11)
- `suggest_queries` now **caps live autocomplete at 3 phrases** and reserves the
  8-result window for its viewpoint-shifting differentiators. The reserved tier
  (`{topic} 2025 OR 2026`, `criticism`, `alternatives`, `site:github.com`) is
  guaranteed to survive — so **≥1 criticism and ≥1 primary-source query always
  reach the agent**, even when autocomplete returns a full set of (often noisy)
  phrases. Previously, 4 autocomplete phrases pushed both `site:github` and
  `site:arxiv` past the cap, gutting the tool's echo-chamber-breaking mission
  (real autocomplete for a person is tabloid noise: "net worth", "husband").
- Autocomplete still leads the list when present (unchanged ordering contract).
- Tests: `tests/test_suggest.py::TestReservedSlotsB11`.

### Fixed — Intermittent test-teardown warning silenced (2026-05-31, B8)
- `tests/test_telemetry.py` gained an autouse fixture that awaits
  `telemetry.drain()` in teardown, so the `@track` decorator's fire-and-forget
  aiosqlite write can never race the event-loop teardown into an intermittent
  `PytestUnhandledThreadExceptionWarning`. Test-only change; no runtime behavior
  change. Pinned by `TestDrainSafety::test_drain_clears_a_pending_write`.

### Added — Extraction gauntlet expanded 5 → 10 site categories (2026-05-31, B3)
- The `eval_judge` extraction gauntlet (`tests/test_extractor.py`) now covers
  **10** site categories instead of 5: added forum Q&A (Stack Overflow), academic
  preprint (arXiv), government policy notice, corporate press release, and
  e-commerce product — each with realistic 2026-era chrome (vote rails, cite
  boxes, datelines, add-to-cart, "customers also bought"). Widens the regression
  net to far more of the web an agent actually reads.
- Gauntlet average holds at **8.72/10 ≥ 8.5 gate**; every category clears the
  7.0 per-category floor. (Internal test-corpus change; no runtime behavior
  change.)

### Added — MTTI (mean time to improvement) metric in status.py (2026-05-31, B2)
- `scripts/status.py` now prints an **MTTI** line derived from the backlog
  (`docs/METHODOLOGY.md` §5), the project's real alert→patch ledger. A reactive
  row carries `disc:YYYY-MM-DD` (flagged) and, once closed, `DONE YYYY-MM-DD`
  (patched); MTTI = mean/median of `DONE − disc` over closed reactive rows, plus
  the age of the oldest still-open flag. Proactive/process items (no `disc:`)
  are excluded by design.
- **Reframed off the literal backlog text** ("add `patch_landed_at` column to
  `telemetry` schema"): a per-call telemetry event has no "patch", and alerts
  are recomputed statelessly (never persisted), so there is nothing to attach a
  landing time to. The backlog is the only continuous ledger that pairs a
  discovery with a fix.
- **Finding: MTTI ≈ 0 days** — this agent fixes flagged issues in the same
  session, so the live, actionable signal is the **oldest open flag's age**
  (currently 2d), not the closed average.
- Tests: `tests/test_scripts.py::TestBacklogMTTI`.

### Fixed — eval_judge no longer over-rates thin/empty extractions (2026-05-31, B26)
- `eval_judge.score_markdown` previously awarded the full 4/4 noise score to any
  body that merely lacked noise patterns — so a near-empty failed extraction
  (`"# Title / Loading…"`) scored a misleading **5.0/10**. Added a
  content-sufficiency gate: the noise reward is now scaled by
  `min(1, len(body)/150)`, so "absence of noise" can't read as "clean" when
  there is no content to judge.
- **Effect (measured via `calibrate_judge.py`):** the thin fragment drops
  **5.0 → 1.59** (consumer rating 1.0) and the judge↔consumer correlation rises
  **r 0.79 → 0.932**. Real articles are unaffected (hundreds+ of chars ⇒ factor
  1.0), so the ≥8.5 Gauntlet gate region is byte-identical — confirmed by the
  golden fixtures and the code-heavy sample scoring exactly as before.
- Tests: `tests/test_judge.py::TestThinContentGate`.

### Added — eval_judge calibration harness (2026-05-31, B1)
- `evals/calibrate_judge.py` measures the Pearson correlation between the cheap
  `eval_judge` heuristic (noise/structure/density → 0–10) and the **consumer's**
  holistic usability rating, over 11 labeled samples (the 4 real golden fixtures
  as high anchors + 7 crafted real-world failure modes). Reframed off the
  backlog's *human*-rating target: the consumer of `read_article` output is the
  LLM agent, so that is the correct (and unblocked) ground truth.
- **Result: r = 0.79, and the 8.5 Gauntlet gate region is well-calibrated** —
  the golden fixtures score 8.5–9.25 vs. a consumer 8.5–9.0, so the gate
  genuinely means "good". Surfaced a low-range miscalibration (a thin/empty
  extraction scores 5.0 because the noise axis rewards *absence* of noise even
  with no content) — recorded as backlog B26; the gate region itself is fine.
- No change to runtime tool behavior or the gate; this validates the gate's
  proxy. Tests: `tests/test_judge.py::TestPearson` / `TestCalibrationSet` /
  `TestCalibrationResult`.

### Fixed — Programming-language Wikipedia infoboxes stripped (2026-05-31, B25)
- `read_article` now strips the leading Wikipedia **programming-language /
  software infobox** (e.g. Rust's `Paradigms / Designed by / First appeared /
  Stable release / Typing discipline / Filename extensions` table) instead of
  leaking it into the article body. Surfaced by the first `scripts/research.py`
  run (Rust). Added the two keys *unique* to a language infobox — `typing
  discipline`, `filename extension` — to the position+marker chrome gate.
- **Precision preserved:** deliberately did *not* add `paradigm` / `first
  appeared` / `stable release`, since those are the column headers of
  "Comparison of programming languages" tables; adding them would risk stripping
  a legitimate leading comparison table (same caution as the B18 company keys).
- Tests: `TestLeadingWikiChrome::test_strips_programming_language_infobox` and
  `::test_preserves_language_comparison_table`. Verified live on the real Rust
  article (now opens with prose, 0 infobox keys in the first 1500 chars).

### Added — One-command research digest (2026-05-31): workload reduction
- `scripts/research.py "<topic>"` runs the full Deep Research loop in one call:
  multi-search → triage (authoritative-first, drop `near_duplicate`, dedup by
  host) → read the top N → print a synthesis-ready digest (each source's tier,
  title, snippet, and a residual-noise flag) + lateral query ideas. It only
  orchestrates the existing tools — no new retrieval logic.
- **Why:** the agent had hand-written the *same* throwaway orchestration script
  six times across the 2026-05 dogfooding runs (`.scratch_meta.py`,
  `.scratch_mitoma.py`, `.scratch_ddg.py`, `.scratch_kyocho.py`,
  `.scratch_sv.py`, `.scratch_altman.py`). This replaces ~40 lines of
  per-task plumbing with `python scripts/research.py "topic" [--recent] [--region jp-jp]`.
- Tests: `tests/test_scripts.py::TestResearchTriage` (the pure triage logic).

### Changed — Analyst / research sources recognized (2026-05-31, B24)
- `source_tier` now tags major industry analyst / research / consulting domains
  `authoritative`: Gartner, Forrester, IDC, Deloitte, McKinsey, BCG, PwC,
  Accenture, IEEE Computer Society (computer.org), Crunchbase, HBR, Pew
  Research. Motivated by the non-AI SV-trends run, where Deloitte / Crunchbase /
  computer.org reports were indistinguishable from SEO blogs (all `unknown`).
- **Deliberately excluded** `forbes.com` / `inc.com` / `entrepreneur.com`:
  they run large *contributor* networks where quality is per-author, not
  per-domain, so the domain can't certify the article (same precision principle
  as refusing to guess `low_quality`). Tests pin both the inclusions and the
  exclusions.

### Added — Search-operator guidance (2026-05-31, B23)
- `search_web` docstring (the agent's prompt) now documents that DuckDuckGo
  operators pass through verbatim — `-term` (exclude), `"phrase"`, `site:`,
  `OR` — with an explicit recipe for "NOT about X" / "X以外" requests
  (`… -X -"X spelled out"`) and a caveat that excluding a *dominant* topic
  surfaces long-tail / low-relevance pages. Motivated by a "non-AI Silicon
  Valley trends" run where the agent didn't know `-AI` was supported.
- Regression tests pin the contract: operators reach the DDGS call verbatim
  (`test_search_operators_pass_through_verbatim`) and survive into the
  fallback URL (`test_operators_survive_url_encoding`). No behavior change —
  the operators always passed through; they were just undocumented.

### Fixed — Near-duplicate detection for CJK titles (2026-05-30, B22)
- `near_duplicate` (B16) was a silent no-op for Japanese/Chinese results:
  `_title_tokens` used `[a-z0-9]+`, so a CJK title produced ~no tokens →
  Jaccard always 0. Now CJK runs emit **character bigrams** (no morphological
  analyzer / new dependency needed); Latin word-tokenization is unchanged.
  Verified: the real 辺地共聴 subsidy listicles (repeated across 6+ aggregators)
  now score J≈0.71 → flagged, while different Japanese topics score J≈0.27 →
  kept. English behavior identical (EN dup 0.64, EN diff 0.0). Tests:
  `tests/test_search.py::{TestTitleTokens,TestJapaneseNearDuplicate}`.

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
