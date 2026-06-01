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

### Rule 6 — `read_article` extraction length drifts ≥ ±10 % between releases → behaviour drift (B6)
- **Trigger:** `evals/telemetry_diff.py --before A --after B` prints a `⚠ Rule 6`
  line (avg success tokens moved ≥ `EXTRACTION_DRIFT_PCT`, with ≥ `DRIFT_MIN_SAMPLES`
  successful extractions in each snapshot).
- **Cause:** usually a silent `trafilatura` / `readability-lxml` behaviour change
  (a dependency bump quietly extracting more boilerplate, or truncating body).
  Telemetry stores token counts but not bodies, so this is the only *aggregate*
  way to catch it — dogfooding sees it on the corpus, this sees it in the wild.
- **Patch (in order):** (1) `python evals/dogfood_regression.py` — did goldens
  drift? If yes, locate the extractor/cleaner change. (2) Spot-check a few real
  extractions for new noise or truncation. (3) If a dependency moved, pin/revert
  it in `pyproject.toml` and record the trap in `docs/LESSONS.md`.

---

## 5. Open Improvement Backlog

Priority order. When trigger 5 fires (§1), pick the topmost item.
When you discover a new improvement opportunity but don't have time to act, **add it
here** — the backlog's existence is what prevents "what do I do next?" paralysis.

> **Date convention (B2 — feeds the MTTI metric in `scripts/status.py`).** This
> backlog *is* the project's alert→patch ledger. A **reactive** row (a problem
> found while using the tool) carries `disc:YYYY-MM-DD` = when it was first
> flagged; a closed row carries `DONE YYYY-MM-DD` = when the patch landed.
> `status.py` computes MTTI = mean(`DONE` − `disc`) over closed reactive rows,
> plus the age of the oldest still-open flag. **Proactive / process items**
> (e.g. B1/B2/B4/B6 — planned enhancements, not discovered bugs) deliberately
> carry **no** `disc:` and are excluded — MTTI measures *responsiveness to
> discovered problems*, not roadmap pace. Always add `disc:` to a new reactive
> row, and never edit a closed row's dates afterward.

| # | Improvement | Expected impact | Blocked on |
|---|-------------|-----------------|------------|
| ~~**B1**~~ | ~~Calibrate `eval_judge` scores against ratings (Pearson correlation)~~ | — | **✅ DONE 2026-05-31** — `evals/calibrate_judge.py`. Reframed off the (mis-specified) *human* target: the consumer is the **LLM**, so calibrated against agent-as-consumer holistic ratings on 11 samples (4 real golden fixtures + 7 spread). **Finding: r=0.79; the 8.5 gate region is well-calibrated (fixtures 8.5–9.25 vs consumer 8.5–9).** Low-range miscalibration spun out as B26. |
| ~~**B2**~~ | ~~Measure MTTI (mean time to improvement) per alert~~ | — | **✅ DONE 2026-05-31** — reframed off the literal "telemetry column": a per-call event has no patch, and alerts aren't persisted (stateless recompute). The real alert→patch ledger is **this backlog**. Added a `disc:`/`DONE` date convention + `status.py mtti()` computing closed-MTTI and oldest-open-flag age. **Finding: MTTI ≈ 0 days — fixes are same-session; the live signal is open-flag age.** |
| ~~**B3**~~ | ~~Expand the adversarial fixture corpus from 5 to 10+ sites~~ | — | **✅ DONE 2026-05-31** disc:2026-05-29 — Gauntlet 5→**10** categories: added forum Q&A, academic preprint, government notice, corporate press release, e-commerce product (`tests/test_extractor.py`). Avg holds at **8.72 ≥ 8.5**; all 10 clear the 7.0 floor. Honest scoping: hand-written fixtures are a **regression net** across categories, not a discovery tool (that's `live_check`/dogfooding). |
| ~~**B4**~~ | ~~Telemetry diff report between two `telemetry.db` snapshots~~ | — | **✅ DONE 2026-06-01** — `evals/telemetry_diff.py --before A --after B`: per-tool + overall deltas (success rate, tokens/call, latency) and error-code churn, with regression notes (success-rate drop, new error code) and a PROVISIONAL banner below the row-confidence floor. Answers "did this release help or hurt?" that a single snapshot can't. Unblocks B6. Pinned by `tests/test_telemetry_diff.py`. |
| ~~**B5**~~ | ~~Add a "noise leak hint" check to `analyze_telemetry.py`~~ | — | **✅ DONE 2026-05-29 (relocated)** — see note below |
| ~~**B6**~~ | ~~Operations Rule 6 — flag ±10 % extraction length variance between releases~~ | — | **✅ DONE 2026-06-01** — `telemetry_diff.extraction_length_drift()` flags `read_article` avg-success-token swings ≥ ±`EXTRACTION_DRIFT_PCT` (10%) with a ≥ `DRIFT_MIN_SAMPLES` guard; surfaced in the diff and codified as **Operations Rule 6** (§4) + a MAINTENANCE playbook. Built on B4. Pinned by `TestExtractionDriftRule6`. |
| ~~**B7**~~ | ~~Auto-propose a candidate `_NOISE_LINE_RE` regex from each auditor finding~~ | — | **✅ DONE 2026-05-29 (reframed)** — see note below |
| ~~**B8**~~ | ~~Intermittent `PytestUnhandledThreadExceptionWarning` in `test_telemetry.py` (fire-and-forget write races loop teardown)~~ | — | **✅ DONE 2026-05-31** disc:2026-05-29 — added an **autouse** fixture in `test_telemetry.py` that `await telemetry.drain()`s in teardown, so no fire-and-forget aiosqlite write outlives its test (regardless of whether the test body drains). Pinned by `TestDrainSafety` (deterministic: a slow write is provably pending, then drain clears it). Warning is nondeterministic → pin the invariant, not the symptom. |
| ~~**B9**~~ | ~~Strip "Part of a series on" / infobox nav-template tables~~ | — | **✅ DONE 2026-05-30** — `strip_leading_wiki_chrome`: removes a *leading* table carrying a high-precision infobox/nav marker. Mid-article + unmarked + prose-first bodies untouched (no baseline drift). disc:2026-05-30 |
| ~~**B10**~~ | ~~Capture a few representative *live* pages as permanent regression fixtures~~ | — | **Declined 2026-05-30:** full-page snapshots bloat the repo and would golden-freeze the unfixed B9 leak; strip logic is unit-tested + `live_check` covers integration. (Struck so `status.py` no longer lists a declined row as "next" — see B27.) |
| ~~**B11**~~ | ~~`suggest_queries` live autocomplete crowds out the primary-source templates under the 8-cap~~ | — | **✅ DONE 2026-05-31** disc:2026-05-30 — autocomplete share **capped at `_AC_BUDGET=3`** and the echo-chamber differentiators (`temporal / criticism / alternatives / site:github`) moved to a **reserved tier** that always lands within the 8-result window. Guarantees ≥1 criticism + ≥1 primary-source survive even with 4 noisy AC phrases. AC still leads (back-compat). Pinned by `TestReservedSlotsB11`. |
| ~~**B12**~~ | ~~Workflow single point of failure: search down ⇒ whole loop dies~~ | — | **✅ DONE 2026-05-30** — `_ddg_html_fallback` scrapes `html.duckduckgo.com` directly when the bing-routed library fails. Verified live: search (and the Sam Altman task) now works where it was fully dead. disc:2026-05-30 |
| ~~**B13**~~ | ~~`search_web` CONN_ERROR hint pushes reword/broaden — futile during a backend outage~~ | — | **✅ DONE 2026-05-31** disc:2026-05-30 — base hints now *hedge* ("if searches keep failing it's the backend, not your query — switch strategy"), and `search_web` tracks consecutive live-search failures: at `_OUTAGE_THRESHOLD=3` the hint escalates to "N in a row failed — stop rewording, switch strategy" and flips `retryable→False` to break reword loops. A success resets the streak. Pinned by `TestB13OutageEscalation`. |
| ~~**B14**~~ | ~~"Recent / time-sensitive" queries have no freshness signal: `published_date` always null (DDGS)~~ | — | **✅ DONE 2026-06-01** disc:2026-05-30 — `search_web` now derives `published_date` best-effort from the **URL path** (news URLs embed `/YYYY/MM/DD/`) via the existing `date_parser.best_effort_date`, on both the DDGS and HTML-fallback paths. Snippet body deliberately **not** mined (too unreliable for a recency filter). Docstring documents it as an approximate freshness signal. Pinned by `TestB14FreshnessSignal`. |
| ~~**B15**~~ | ~~No source-quality signal — agent can't tell a content farm from Reuters~~ | — | **✅ DONE 2026-05-30** — `source_tier` (`authoritative`/`unknown`) on every result via `core/source_quality.py`. High-precision allowlist; does NOT guess `low_quality`. Verified live on a Llama 4 search. disc:2026-05-30 |
| ~~**B16**~~ | ~~Near-duplicate results waste reads~~ | — | **✅ DONE 2026-05-30** — `near_duplicate` flag (conservative Jaccard ≥ 0.6). **Mark, never remove** — count = corroboration. Cluster primary prefers authoritative (B15 synergy). disc:2026-05-30 |
| ~~**B17**~~ | ~~The trust signal points at sources we can't read (Reuters fails)~~ | — | **✅ DONE 2026-05-30** — `core/http.py` rotates fingerprint chrome131→safari17_0 on 401/403. Diagnosed: Reuters 401 to Chrome, 200 to Safari. `read_article` now fetches Reuters. (Also fixed 401→BLOCKED_403 mis-mapping.) disc:2026-05-30 |
| ~~**B18**~~ | ~~B9 misses company/website/org infoboxes (DuckDuckGo leaks)~~ | — | **✅ DONE 2026-05-30** — added company/website markers ("type of site", "area served", "key people", "number of employees", "current status", "traded as"). Excluded "headquarters"/"founder"/"launched" (can be comparison-table columns). DDG now opens with prose. disc:2026-05-30 |
| ~~**B20**~~ | ~~Mojibake on non-UTF-8 pages (soumu.go.jp Shift_JIS → garbage)~~ | — | **✅ DONE 2026-05-30** — `decode_html` detects charset (header → `<meta>` → detector → utf-8) and decodes from bytes. soumu.go.jp now reads as clean Japanese (0 mojibake). disc:2026-05-30 |
| ~~**B21**~~ | ~~`source_tier` allowlist is US/UK-centric (.go.jp tagged unknown)~~ | — | **✅ DONE 2026-05-30** — `_AUTH_TLDS` extended to JP/FR/DE/EU/IN/KR/etc. government & academic TLDs (geographic `.<pref>.jp` excluded). soumu.go.jp now `authoritative`. disc:2026-05-30 |
| ~~**B22**~~ | ~~B16 tokenizer is ASCII-only → near_duplicate broken for Japanese~~ | — | **✅ DONE 2026-05-30** — `_title_tokens` emits CJK character bigrams (no morphological-analyzer dep). 辺地共聴 listicles now flagged (J≈0.71); EN unchanged. disc:2026-05-30 |
| ~~**B23**~~ | ~~Exclusion / negative-intent queries undocumented (agent didn't know `-AI` works)~~ | — | **✅ DONE 2026-05-31** — `search_web` docstring now documents `-term`/`"phrase"`/`site:`/`OR` pass-through + a "NOT about X" recipe + dominant-topic caveat. Pass-through pinned by tests. disc:2026-05-31 |
| ~~**B24**~~ | ~~`source_tier` misses major analyst / tech-press firms (Deloitte/Gartner/Crunchbase `unknown`)~~ | — | **✅ DONE 2026-05-31** — added Gartner/Forrester/IDC/Deloitte/McKinsey/BCG/PwC/Accenture/computer.org/Crunchbase/HBR/Pew. Excluded Forbes/Inc. (per-author contributor networks). disc:2026-05-31 |
| ~~**B19**~~ | ~~B16 misses loose same-story clusters (paraphrased headlines, Jaccard < 0.6)~~ | — | **✅ DONE 2026-06-01** disc:2026-05-30 — added `story_cluster` (new `SearchResult` field): links results sharing ≥2 significant title tokens (transitive union) and exposes the group id. Routed to a **corroboration signal, NOT `near_duplicate`** — loose same-story coverage from independent outlets is worth reading across; a false grouping is therefore low-harm. near_duplicate (skip) left untouched. Pinned by `TestB19StoryClusters`. |
| ~~**B25**~~ | ~~B9 misses software / programming-language infoboxes (Rust language infobox leaked)~~ | — | **✅ DONE 2026-05-31** — added `typing discipline` + `filename extension` (unique language-infobox keys) to `_WIKI_CHROME_MARKERS`. Excluded `paradigm`/`first appeared`/`stable release` (they double as "Comparison of programming languages" table columns). Verified live: real Rust Wikipedia article now opens with prose, 0 infobox leak. disc:2026-05-31 |
| ~~**B26**~~ | ~~`eval_judge` over-rates thin/empty extractions (`"# Title / Loading…"` scored 5.0/10)~~ | — | **✅ DONE 2026-05-31** — content-sufficiency gate on the noise axis: `noise_score *= min(1, total_chars/150)`, so "no noise" can't read as "clean" when there's no content. thin fragment **5.0→1.59** (consumer 1.0); calibration **r 0.79→0.932**. Gate region byte-identical (fixtures + code_heavy unchanged), so ≥8.5 untouched. The remaining low-range *under*-ratings (content-with-noise) are intentional gate behavior, left as-is. disc:2026-05-31 |
| ~~**B27**~~ | ~~`status.py` lists a *Declined* row (B10) as the "next" backlog item~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — `next_backlog()` now skips `Declined` rows (not just `DONE`/struck), checks the whole row line, and is text-injectable for deterministic tests; empty-backlog message changed from "(none parsed)" to "(no open items — backlog clear)". B10 struck for consistency. Surfaced by reading status.py output after the backlog was consumed. Pinned by `test_next_backlog_excludes_declined`. |
| ~~**B30**~~ | ~~No single "how good is DeepSearch-MCP right now" benchmark — quality was scattered across gauntlet/calibration/dogfood~~ | — | **✅ DONE 2026-06-01** — `evals/benchmark.py` = **DeepSearch Quality Score (DQS, 0–100)**: a fixed, offline, deterministic battery composing validated measures (extraction 40% / cleanliness 20% / robustness 25% / diversity 15%). Baseline **92.9/100**. Tracked release-over-release (§6); regression floor pinned by `tests/test_benchmark.py`. Proxy over fixtures — north-star, not a dogfooding substitute. (User-requested; proactive, no `disc:`.) |
| ~~**B31**~~ | ~~`dogfood_audit` byline heuristic false-positives on prose ("By declaring…")~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — surfaced by the DQS cleanliness sub-score (1 gauntlet fixture flagged). `re.IGNORECASE` made the byline `[A-Z]` match any letter, so any "by <word>" prose tripped METADATA_STUB. Scoped that alternative to case-sensitive `(?-i:By\s+[A-Z])`; real bylines ("By Jane Doe") still flag. **DQS 92.9→94.9** (cleanliness 90→100). Pinned by `test_by_lowercase_prose_not_flagged`. |
| ~~**B28**~~ | ~~`story_cluster` (B19) collapses a single-topic search into ONE mega-cluster~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — two mechanisms: (1) `_mark_story_clusters(results, query=)` **excludes the query's own tokens** (shared by construction); (2) a **dominance cap** drops any cluster covering ≥60% of a result set of ≥4 (topic homogeneity ≠ a story). Live re-run proved query-exclusion *alone* insufficient (ubiquitous non-query words "august"/"compliance" still chained all 8) → the cap is the backstop. EU run now: 10/10 `None` (was 8/8 cluster-1); genuine same-event subsets still cluster. Pinned by `TestB28QueryAwareClustering` (real EU titles + dominance + subset + back-compat). |
| ~~**B29**~~ | ~~`suggest_queries` primary-source templates are dev-centric (`site:github`), useless for policy/legal/gov topics~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — the guaranteed primary-source angle is now **domain-adaptive** (`_primary_source_template`): policy/legal/gov topics (word-level signal match, so "React" ≠ "act") get `site:.gov OR site:europa.eu OR site:.int`; everything else keeps `site:github.com`. Verified live: "EU AI Act enforcement" → official sources; "React Server Components" → github. B11 reserve/cap guarantees still hold. Pinned by `TestB29DomainAdaptivePrimarySource`. (Signal list will grow with real usage — B25 discipline. The "0-authoritative nudge" variant left for a future cycle.) |
| ~~**B32**~~ | ~~`suggest_queries` viewpoint templates are English-only — useless for non-English topics~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — `_topic_lang` detects a CJK topic and swaps the **word-based** angles to Japanese (`批判`/`代替案`/`問題点 デメリット`/`比較`); site:/year angles stay language-agnostic. Verified live: "日本 新興 ガジェット メーカー" → 批判/代替案/比較; English topics unchanged. B11 reserve/cap + B29 primary-source adaptivity still hold. Japanese-first (the observed need; extends with usage — B25 discipline). Pinned by `TestB32LanguageAdaptiveTemplates`. |
| ~~**B33**~~ | ~~CJK bigram clustering (B22/B28) over-links on low-entropy bigrams~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — diagnosed: a false JP cluster came from coincidental bigram overlap (テッ/ック ⊂ テック⊂マテック) + generic words. Two fixes: (1) **weight** shared tokens — Latin word 1.0, CJK ≤2-char bigram 0.5 (needs ~4 bigrams, not 2); (2) **pure-digit tokens (years/counts) carry 0 weight** — a 2nd live run linked 3 unrelated "2025年最新…" listicles via `2025`+`最新`. Verified live: JP run 8/8(false)→0 clusters; genuine JP same-story still clusters; English unchanged. Pinned by `TestB33CjkClusterWeighting`. |
| ~~**B34**~~ | ~~Lift DQS extraction (87.2) by rewarding section depth in `eval_judge`'s structure axis~~ | — | **Investigated & declined 2026-06-01:** the change raised the gauntlet 8.72→9.12 (DQS→91.2) but `calibrate_judge` showed it **lowered** judge↔consumer correlation (r 0.932→0.925) — it traded 2 under-ratings for 2 over-ratings = Goodhart. Reverted; left a guardrail NB in `eval_judge.py` + a LESSONS entry. The headroom is honest signal, not a calibration defect. |
| ~~**B35**~~ | ~~0 authoritative is the NORM on real DDG results — the tool gives no active path to authority~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — added `suggest.authority_query(topic)` (renders the B29/B36 domain-appropriate primary-source query). Surfaced two ways: (1) `search_web` docstring now prescribes the recovery workflow — *all-unknown ⇒ call `suggest_queries` and run its `site:`-authority angle*; (2) `research.py` digest prints the concrete authority query when `n_auth == 0`. Reaches gov/pubmed/arxiv directly when DDG buries the primary under SEO. Pinned by `TestB35AuthorityQuery` + `TestResearchAuthorityNudge`. |
| ~~**B36**~~ | ~~B29 primary-source detection covers only dev + policy — medical/science topics get `site:github`~~ | — | **✅ DONE 2026-06-01** disc:2026-06-01 — `_primary_source_template` extended: medical signals → `pubmed/nih.gov/who.int`, science signals → `arxiv/.edu` (policy → medical → science → dev, first match wins; science words chosen to NOT overlap dev). **Known limit (documented + tested):** a bare proper-noun topic ("semaglutide long-term effects" — no generic medical word) still defaults to dev — keyword detection can't list every drug/gene name (B25). Pinned by `TestB36MedicalSciencePrimarySource`. |

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
| Monthly | Re-read this file. Pick one Backlog item and start a cycle. Check `status.py` MTTI: an open flag aging past ~1 week is a prioritization smell. Record the **DQS** (`python evals/benchmark.py`) and compare to last month — a drop is a quality regression to chase. | Maintainer |
| Quarterly | Re-tag every entry in `docs/LESSONS.md`. Drop `[STALE]`. Check dependencies for major-version bumps. | Maintainer |

The audit cadence is not optional. A methodology you never re-read is just a snapshot.
