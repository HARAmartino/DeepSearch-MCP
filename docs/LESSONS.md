# Lessons Learned — DeepSearch-MCP

**Dynamic knowledge base of bugs, surprises, and library quirks discovered during development.**

This file is the long-term memory of the project. It is **not** loaded into the agent's
context by default — read it only when:
- A bug touches an area you don't recognize.
- A test fails in a way that looks like a known library quirk.
- You're about to bump a major dependency version.
- You're doing the quarterly audit (see [METHODOLOGY.md](METHODOLOGY.md) §5).

---

## How to read this file

Each entry carries one status tag:

| Tag | Meaning |
|-----|---------|
| `[ACTIVE]` | Code still depends on this. Removing the lesson risks the bug returning. |
| `[HISTORICAL]` | True at the time, but no longer load-bearing — kept as context. |
| `[STALE]` | No longer true (library bumped, design changed). Slated for deletion at next audit. |

**Maintenance rules:**
- Append new findings as new dated entries; do not edit existing ones in place.
- Tag every entry at write time. Re-tag during the quarterly audit.
- Stale entries become noise the same way nav bars do — Prime Directive 1 applies
  to documentation just as much as to extraction output.

**Audit cadence:** quarterly, or whenever a dependency bumps a major version.
**Last audit:** 2026-05-29 (post-Dogfooding cycle).

---

## Index

| Date | Tag | Title |
|------|-----|-------|
| 2026-06-01 | [ACTIVE] | [Exclude the signal shared by construction before clustering — and let the live run, not fixtures, be the verdict](#2026-06-01-active-exclude-the-signal-shared-by-construction-before-clustering--and-let-the-live-run-not-fixtures-be-the-verdict) |
| 2026-06-01 | [ACTIVE] | [An orientation tool must show only ACTIONABLE state — and its edge cases hide until the happy path is exhausted](#2026-06-01-active-an-orientation-tool-must-show-only-actionable-state--and-its-edge-cases-hide-until-the-happy-path-is-exhausted) |
| 2026-06-01 | [ACTIVE] | [Detect silent drift with a metric you already store + a sample-size guard so it can't cry wolf](#2026-06-01-active-detect-silent-drift-with-a-metric-you-already-store--a-sample-size-guard-so-it-cant-cry-wolf) |
| 2026-06-01 | [ACTIVE] | [A single snapshot describes; a diff judges — build the before/after view for release questions](#2026-06-01-active-a-single-snapshot-describes-a-diff-judges--build-the-beforeafter-view-for-release-questions) |
| 2026-06-01 | [ACTIVE] | [Match the signal's mechanism to its meaning — "skip" vs "corroborate" are opposite affordances](#2026-06-01-active-match-the-signals-mechanism-to-its-meaning--skip-vs-corroborate-are-opposite-affordances) |
| 2026-06-01 | [ACTIVE] | [Derive a missing signal from the highest-precision source you have, not every source](#2026-06-01-active-derive-a-missing-signal-from-the-highest-precision-source-you-have-not-every-source) |
| 2026-05-31 | [ACTIVE] | [An error hint must scale with evidence — a recovery action futile at scale shouldn't be the advice](#2026-05-31-active-an-error-hint-must-scale-with-evidence--a-recovery-action-futile-at-scale-shouldnt-be-the-advice) |
| 2026-05-31 | [ACTIVE] | [Enrichment must not crowd out the differentiator — cap the optional input, reserve slots for the mission](#2026-05-31-active-enrichment-must-not-crowd-out-the-differentiator--cap-the-optional-input-reserve-slots-for-the-mission) |
| 2026-05-31 | [ACTIVE] | [Fire-and-forget work needs a drain barrier in tests — put it in the gating (autouse) fixture](#2026-05-31-active-fire-and-forget-work-needs-a-drain-barrier-in-tests--put-it-in-the-gating-autouse-fixture) |
| 2026-05-31 | [ACTIVE] | [Hand-written fixtures are a regression net, not a discovery tool — expand them for breadth](#2026-05-31-active-hand-written-fixtures-are-a-regression-net-not-a-discovery-tool--expand-them-for-breadth) |
| 2026-05-31 | [ACTIVE] | [Measure a meta-metric off the ledger you already maintain, not a new empty store](#2026-05-31-active-measure-a-meta-metric-off-the-ledger-you-already-maintain-not-a-new-empty-store) |
| 2026-05-31 | [ACTIVE] | [Changing a gate's scorer: prove the gate region is byte-identical, fix only the broken range](#2026-05-31-active-changing-a-gates-scorer-prove-the-gate-region-is-byte-identical-fix-only-the-broken-range) |
| 2026-05-31 | [ACTIVE] | [Calibrate the quality proxy against the real consumer — and trust it only where the gate lives](#2026-05-31-active-calibrate-the-quality-proxy-against-the-real-consumer--and-trust-it-only-where-the-gate-lives) |
| 2026-05-31 | [ACTIVE] | [Curated marker lists extend 3+ times — incompleteness is structural, not a bug](#2026-05-31-active-curated-marker-lists-extend-3-times--incompleteness-is-structural-not-a-bug) |
| 2026-05-31 | [ACTIVE] | [If you hand-write the same orchestration scaffold N times, bake it into a command](#2026-05-31-active-if-you-hand-write-the-same-orchestration-scaffold-n-times-bake-it-into-a-command) |
| 2026-05-31 | [ACTIVE] | [Document the capabilities the agent can't discover — the docstring is the API](#2026-05-31-active-document-the-capabilities-the-agent-cant-discover--the-docstring-is-the-api) |
| 2026-05-30 | [ACTIVE] | [The stack was UTF-8/English-centric — non-English usage broke 3 things](#2026-05-30-active-the-stack-was-utf-8english-centric--non-english-usage-broke-3-things) |
| 2026-05-30 | [ACTIVE] | [Strip noise by position + marker, not by type — leading Wikipedia chrome](#2026-05-30-active-strip-noise-by-position--marker-not-by-type--leading-wikipedia-chrome) |
| 2026-05-30 | [ACTIVE] | [Dedup by marking, not removing — duplicates are corroboration](#2026-05-30-active-dedup-by-marking-not-removing--duplicates-are-corroboration) |
| 2026-05-30 | [ACTIVE] | [One TLS fingerprint is not enough — rotate on a block](#2026-05-30-active-one-tls-fingerprint-is-not-enough--rotate-on-a-block) |
| 2026-05-30 | [ACTIVE] | [Real search returns what ranks, not what's authoritative](#2026-05-30-active-real-search-returns-what-ranks-not-whats-authoritative) |
| 2026-05-30 | [ACTIVE] | [Search resilience — bypass the library when it has a single backend](#2026-05-30-active-search-resilience--bypass-the-library-when-it-has-a-single-backend) |
| 2026-05-30 | [ACTIVE] | [Real research run (Sam Altman) — search is the loop's lifeline](#2026-05-30-active-real-research-run-sam-altman--search-is-the-loops-lifeline) |
| 2026-05-30 | [ACTIVE] | [A mock of the unit-under-test hid a feature that never worked](#2026-05-30-active-a-mock-of-the-unit-under-test-hid-a-feature-that-never-worked) |
| 2026-05-30 | [ACTIVE] | [Fixtures are not real usage — the Check was self-referential](#2026-05-30-active-fixtures-are-not-real-usage--the-check-was-self-referential) |
| 2026-05-30 | [ACTIVE] | [Aggregate activation — "no data" is not "healthy"](#2026-05-30-active-aggregate-activation--no-data-is-not-healthy) |
| 2026-05-29 | [ACTIVE] | [Automate what the agent is bad at, not what it's good at](#2026-05-29-active-automate-what-the-agent-is-bad-at-not-what-its-good-at) |
| 2026-05-29 | [ACTIVE] | [Agent DX — ground truth is one command, not prose](#2026-05-29-active-agent-dx--ground-truth-is-one-command-not-prose) |
| 2026-05-29 | [ACTIVE] | [Noise-Leak Auditor — systematizing the dogfooding CHECK step](#2026-05-29-active-noise-leak-auditor--systematizing-the-dogfooding-check-step) |
| 2026-05-29 | [ACTIVE] | [Dogfooding Session — Real-World Cleaner Audit](#2026-05-29-active-dogfooding-session--real-world-cleaner-audit) |
| 2026-05-28 | [ACTIVE] | [Phase 6 — Day 2 Operations (Self-Healing PDCA)](#2026-05-28-active-phase-6--day-2-operations-self-healing-pdca) |
| 2026-05-28 | [ACTIVE] | [Phase 5 — Adversarial Dogfooding (4 Prime Lessons)](#2026-05-28-active-phase-5--adversarial-dogfooding-4-prime-lessons) |
| 2026-05-28 | [ACTIVE] | [Phase 4 — 非HTML検出の設計判断](#2026-05-28-active-phase-4--非html検出の設計判断) |
| 2026-05-28 | [ACTIVE] | [Phase 3 — suggest_queries の設計判断](#2026-05-28-active-phase-3--suggest_queries-の設計判断) |
| 2026-05-28 | [ACTIVE] | [aiosqlite — 正しい使用パターン](#2026-05-28-active-aiosqlite--正しい使用パターン) |
| 2026-05-28 | [ACTIVE] | [duckduckgo-search v8 — 追加の重要な制約 (Phase 2)](#2026-05-28-active-duckduckgo-search-v8--追加の重要な制約phase-2-判明) |
| 2026-05-28 | [ACTIVE] | [eval_judge — スコアリング改善 (Phase 1)](#2026-05-28-active-eval_judge--スコアリング改善phase-1-で適用) |
| 2026-05-28 | [HISTORICAL] | [curl_cffi v0.15 — 最新 impersonate ターゲット](#2026-05-28-historical-curl_cffi-v015--最新-impersonate-ターゲット) |
| 2026-05-28 | [ACTIVE] | [trafilatura v2 — 3つの重要な制約](#2026-05-28-active-trafilatura-v2--3つの重要な制約) |
| 2026-05-28 | [ACTIVE] | [eval_judge.py — ノイズ検出はライン密度に依存](#2026-05-28-active-eval_judgepy--ノイズ検出はライン密度に依存する) |
| 2026-05-28 | [ACTIVE] | [duckduckgo-search v8 — DDGS is Synchronous](#2026-05-28-active-duckduckgo-search-v8--ddgs-is-synchronous) |
| 2026-05-28 | [HISTORICAL] | [Project Initialization](#2026-05-28-historical-project-initialization) |

---

### [2026-06-01] [ACTIVE] Exclude the signal shared by construction before clustering — and let the live run, not fixtures, be the verdict

- **Context (B28).** `story_cluster` (B19) grouped results by shared title
  tokens. In a topic search, *every* result shares the query terms by
  construction (DDG returns matches), so the whole set collapsed into one useless
  cluster — a live "EU AI Act enforcement 2026" run put 8/8 in cluster 1.
- **Rule 1.** **A feature that matches by shared signal must first remove the
  signal shared *by construction*.** The query tokens carry zero discrimination
  value within a result set whose membership was *defined* by them. Subtract them
  before comparing.
- **But that alone was not enough — and the live run, not my tests, exposed it.**
  Query-exclusion passed a synthetic test I wrote, yet the live re-run STILL
  showed 8/8 in one cluster: the real titles shared ubiquitous *non-query* topic
  words ("august", "compliance") that re-chained everything. My fixture was
  unrepresentative *again* (the recurring trap). **Rule 2: when a heuristic ships
  with an "verify live" caveat, the live run is the test — and a green synthetic
  test is not permission to skip it.**
- **The robust backstop is mechanism-agnostic.** Rather than chase every way
  tokens can over-link, suppress the *outcome*: a cluster covering a majority of
  a sizable result set conveys no differentiation, so don't emit it — regardless
  of *why* it formed. This kills the mega-cluster whatever the shared tokens are.
  (DF down-weighting was still rejected: it would un-cluster a small/pure
  same-event set, whose entities are ubiquitous *because* it's one event. The
  dominance cap only triggers on majorities of ≥4-result sets, so the event case
  is safe.)
- **The cache masked the first re-verification.** `search_web` caches the full
  output JSON (incl. `story_cluster`), so the post-fix re-run returned the *stale*
  pre-fix values and looked unchanged. **When live-verifying a change to enriched
  output, clear the cache (fresh `DEEPSEARCH_CACHE_DIR`) or you're testing the old
  code.**
- **Mechanism / tests:** `tools/search.py::_mark_story_clusters(results, query=)`
  + `_STORY_MAX_CLUSTER_FRAC`/`_STORY_DOMINANCE_MIN_N`; `TestB28QueryAwareClustering`
  (homogeneous set suppressed, query-token isolation, subset preserved,
  small-event still clusters, back-compat). Verified live: EU run 8/8→0 clusters.

### [2026-06-01] [ACTIVE] An orientation tool must show only ACTIONABLE state — and its edge cases hide until the happy path is exhausted

- **Context (B27).** `status.py`'s "Next backlog" surfaced **B10**, a row that had
  been *Declined* (a recorded won't-do). The filter skipped `DONE`/struck rows
  but not `Declined` ones, so a non-actionable decision was offered as the next
  thing to work on.
- **Two-layer lesson.** (1) **A "what to do next" tool must filter to *actionable*
  state, and "resolved" has more than one shape** — done, struck, *and declined*
  are all "not work to pick up". Enumerate every resolved state, not just the
  common one. (2) **The bug only appeared once the backlog was fully consumed** —
  while open items existed, the declined row was never the *top* item, so it
  never showed. Edge-case behaviour of your own tooling (empty list, only-resolved
  list) stays invisible until the happy path runs out; dogfood those end states
  deliberately rather than waiting to stumble on them.
- **Also fixed the empty-state message.** "(none parsed — see §5)" conflated
  *parse failure* with *nothing open*. A cleared backlog now says "(no open
  items — backlog clear)" — don't let a success state read like an error.
- **Testability.** Made `next_backlog(text=None)` injectable (same pattern as
  B2's `mtti` / `parse_backlog_dates`) so filtering is tested on a controlled
  fixture, not on the live backlog — which had become empty and silently broke
  the old "expects ≥1 open item" assertion.
- **Mechanism / tests:** `scripts/status.py::next_backlog` +
  `tests/test_scripts.py` (`test_next_backlog_excludes_declined`, injected-text
  open/done/struck/declined fixture).

### [2026-06-01] [ACTIVE] Detect silent drift with a metric you already store + a sample-size guard so it can't cry wolf

- **Context (B6).** Extractor regressions can be *silent*: a `trafilatura` bump
  starts including boilerplate or truncating body, and nothing errors. Telemetry
  stores token counts (not bodies), so the aggregate `read_article` extraction
  length is a free, already-collected proxy for "are we extracting the same
  amount of text?". A ≥±10% release-over-release swing flags the drift.
- **Rule.** **To catch silent behaviour drift, diff a cheap proxy you already
  record against a baseline — but gate it on sample size.** The danger of any
  "alert on % change" metric is the small-n false alarm: a 1–2 sample average
  swings wildly. Require a minimum sample in *both* snapshots (here ≥5 successful
  extractions) before the alert can fire; below that, stay silent rather than cry
  wolf. (Same spirit as the analyzer's `MIN_ROWS_FOR_CONFIDENCE` cold-start guard
  and the B13 `_OUTAGE_THRESHOLD` — an alert is only as trustworthy as its n.)
- **Scope the proxy to the thing you mean.** "Extraction length" is specifically
  `read_article` *successful* token counts — not all tools, not error rows (whose
  tiny token counts would dilute the signal). Pick the exact population the metric
  is supposed to describe.
- **Mechanism / tests:** `evals/telemetry_diff.py::extraction_length_drift`
  (`EXTRACTION_DRIFT_PCT`, `DRIFT_MIN_SAMPLES`) + `TestExtractionDriftRule6`;
  Operations Rule 6 in `METHODOLOGY.md` §4 + `MAINTENANCE.md` playbook.

### [2026-06-01] [ACTIVE] A single snapshot describes; a diff judges — build the before/after view for release questions

- **Context (B4).** `analyze_telemetry.py` reports on *one* `telemetry.db` — it
  describes the current state but can't answer the question releases actually
  raise: *did this change make things better or worse?* That needs a before/after
  **diff** of two snapshots (success rate, tokens/call, latency, error-code mix).
- **Rule.** **A metric reported in isolation describes; the same metric diffed
  against a baseline judges.** When the decision is "ship/rollback" or "did my
  patch help", build the comparison view, don't make a human eyeball two separate
  reports. Deltas + a short list of regressions (success-rate drop, a brand-new
  error code) turn raw numbers into a verdict.
- **Carry the guards forward, don't re-derive trust.** The diff reuses the same
  cold-start `MIN_ROWS_FOR_CONFIDENCE` guard as the single-snapshot analyzer: a
  diff over thin data is a thin-data swing, not a signal. A new tool that sits on
  an existing metric should inherit that metric's honesty guards (PROVISIONAL),
  not silently present low-confidence deltas as fact.
- **Mechanism / tests:** `evals/telemetry_diff.py` (`snapshot_metrics`,
  `diff_snapshots`, `build_diff`) + `tests/test_telemetry_diff.py`. Unblocks B6
  (extraction-length drift is an alert layered on this diff).

### [2026-06-01] [ACTIVE] Match the signal's mechanism to its meaning — "skip" vs "corroborate" are opposite affordances

- **Context (B19).** B19 was filed as "B16 misses loose same-story clusters —
  flag them too." The obvious reading: extend `near_duplicate` to looser
  matches. But `near_duplicate` means **"don't re-read this"** — and a loose
  same-story cluster from *independent outlets* is exactly what you DO want to
  read across (it corroborates the event). Routing loose clusters into a skip
  flag would have destroyed the corroboration value B19's own "expected impact"
  line asked to *surface*.
- **Rule.** **Before reusing an existing flag for a new case, check that its
  *affordance* (what it makes the agent do) matches the new case's intent.** The
  same underlying detection (similar titles) can warrant opposite actions: a
  near-identical reprint → skip; a paraphrased same-story from another outlet →
  read for corroboration but discount independence. So B19 got a *separate*
  signal — `story_cluster` (a group id), not another `near_duplicate=true`.
- **Precision risk scales with the affordance.** Because `story_cluster` says
  "read across, just don't double-count," a false grouping is **low-harm** (the
  agent still reads them). That let me use a looser threshold (≥2 shared
  significant tokens) than `near_duplicate`'s strict Jaccard ≥ 0.6 — a looseness
  that would be unacceptable for a skip flag. Pick the threshold for the cost of
  being wrong, which depends on the affordance.
- **Offline-validation caveat.** The ≥2-token threshold was tuned on synthetic
  paraphrase sets (the real 8-outlet example isn't captured) — per the
  "fixtures aren't real usage" lesson, treat the precision as provisional and
  re-check `story_cluster` groupings during live dogfooding.
- **Mechanism / tests:** `core/models.py` (`story_cluster` field) +
  `tools/search.py` (`_mark_story_clusters`, `_STORY_MIN_SHARED`, union-find) +
  `tests/test_search.py::TestB19StoryClusters`.

### [2026-06-01] [ACTIVE] Derive a missing signal from the highest-precision source you have, not every source

- **Context (B14).** DDGS never returns `published_date`, so time-sensitive
  research had no recency signal. Two derivation sources were available per
  result: the **URL path** (news embeds `/YYYY/MM/DD/` — high precision) and the
  **snippet body** (a ~30-word excerpt — low precision: its first date might be
  a citation, an event, "back in 2019", anything).
- **Rule.** When backfilling a missing field, **use the highest-precision source
  and stop — don't add lower-precision sources for "more coverage".** A wrong
  value here is worse than a null: a bogus `published_date` makes a recency
  *filter* discard good results or trust stale ones. So search derives from the
  URL only and leaves `published_date` null otherwise; `null` explicitly does
  not mean "old". (Contrast `read_article`, which *does* mine the body — there
  the body is the full article, and the date usually leads it: precision is
  high, so the extra source is justified. Same helper, different inputs.)
- **Reuse the tested helper, vary the inputs.** `best_effort_date(raw, url,
  body)` already existed; search passes only `raw, url`, read_article passes all
  three. No new parsing code, and the precision decision is just which arguments
  you feed it.
- **Mechanism / tests:** `tools/search.py` (`best_effort_date(raw=published,
  url=href)` on DDGS + fallback paths) + `tests/test_search.py::TestB14FreshnessSignal`
  (dated URL → date; undated URL → null; **dated snippet body → still null**).

### [2026-05-31] [ACTIVE] An error hint must scale with evidence — a recovery action futile at scale shouldn't be the advice

- **Context (B13).** `search_web`'s `CONN_ERROR`/`TIMEOUT` hints told the agent to
  "retry / broaden / check spelling / reword". For *one* flaky failure that's
  fine, but during a backend **outage** every one of those is futile — the agent
  burns turns rewording a query that was never the problem.
- **Rule.** **A structured error hint is a recovery instruction; make it scale
  with the evidence.** The same error code can warrant opposite advice depending
  on whether it's a one-off or systemic. Two-part fix: (1) even the base hint
  *hedges* ("if searches keep failing it's the backend, not your query"); (2) the
  tool keeps a cheap **consecutive-failure counter** and, past a threshold,
  escalates to "stop rewording — switch strategy" and flips `retryable→False` to
  break the retry loop. A single success resets the streak.
- **Put the systemic signal where the action is.** The telemetry skew guard
  already knows "a 100%-failing tool is systemic" — but that's offline analysis.
  The agent acts on the *hint*, in the moment, so the per-session call site needs
  its own lightweight streak counter. Don't make the consumer infer systemic-ness
  it can't see; encode it in the response it actually reads.
- **Shared mutable state ⇒ reset fixture.** The counter is module-global, so
  chaos tests that trip it would bleed streaks into each other. A module-level
  autouse reset fixture isolates them (same pattern as the B8 telemetry drain).
- **Mechanism / tests:** `tools/search.py` (`_consecutive_failures`,
  `_note_search_outcome`, `_OUTAGE_THRESHOLD`, `_map_ddgs_exception(..., consecutive_failures)`)
  + `tests/test_search.py::TestB13OutageEscalation` (+ autouse `_reset_search_failure_streak`).

### [2026-05-31] [ACTIVE] Enrichment must not crowd out the differentiator — cap the optional input, reserve slots for the mission

- **Context (B11).** `suggest_queries` mixes DDG autocomplete ("real user
  patterns") with viewpoint-shifting templates (criticism / alternatives /
  primary sources). Once live autocomplete actually worked (it had been dead),
  its 4 phrases filled the 8-result window and pushed the `site:github` /
  `site:arxiv` templates off the end — silently gutting the tool's whole reason
  to exist (breaking echo chambers). Worse, autocomplete for a *person* is
  tabloid noise ("net worth", "husband", "age").
- **Rule.** When a feature blends a **mission-critical** signal with an
  **opportunistic/enrichment** one, the enrichment must be **capped** and the
  mission signal must have **reserved capacity** — never let "whatever the API
  returned" displace the thing the tool is *for*. Here: cap autocomplete at
  `_AC_BUDGET=3` and put the differentiators in a reserved tier sized so
  `capped_enrichment + reserved ≤ window`, guaranteeing they always survive.
- **The trap is "more data is better".** A working data source (autocomplete)
  felt like pure upside, so it was placed first and uncapped. But *relevance to
  the query* ≠ *value to the mission*: the most popular related searches are
  often the least useful for escaping an echo chamber. An input being good is
  not a reason to let it consume the whole budget.
- **Back-compat kept deliberately.** Autocomplete still *leads* the list (an
  existing test pins this) — the fix capped its *share*, it didn't reorder. A
  reserve can be added without inverting a documented contract.
- **Mechanism / tests:** `tools/suggest.py` (`_RESERVED_TEMPLATES`,
  `_EXTRA_TEMPLATES`, `_AC_BUDGET`, capped+reserved merge) +
  `tests/test_suggest.py::TestReservedSlotsB11`.

### [2026-05-31] [ACTIVE] Fire-and-forget work needs a drain barrier in tests — put it in the gating (autouse) fixture

- **Context (B8).** `@track` schedules its DB write with
  `asyncio.create_task(...)` and returns immediately (correct: telemetry must
  never add latency). In tests, a tracked call whose write isn't awaited leaves
  an aiosqlite background-thread write racing pytest-asyncio's loop teardown →
  intermittent `PytestUnhandledThreadExceptionWarning`. Benign in prod (the OS
  reaps the process), but noisy and fatigue-inducing in CI.
- **Rule.** **Any fire-and-forget background work needs exactly one deterministic
  drain point per test, and it belongs in the autouse/gating fixture, not in
  each test body.** Per-test manual drains rot: the moment one test legitimately
  doesn't assert on the side effect, it skips the drain and the race returns.
  An autouse teardown that drains makes the guarantee structural. (Keep manual
  drains only where the test must read the side effect *within* its body —
  there the autouse teardown runs too late.)
- **Scoping gotcha.** Under `asyncio_mode = "auto"`, an autouse *async* fixture
  defined in the test module coexists fine with the module's *sync* tests
  (verified: all 29 pass). Defining it in the module (not a shared conftest)
  keeps the drain local to the tests that create tasks — no cross-module cost.
- **Testing a nondeterministic symptom.** The warning fires only on a teardown
  race, so a "fails-before" assertion on the warning itself is flaky. Pin the
  **invariant the fix relies on** instead: make the write provably slow so a
  task is genuinely pending, then assert `drain()` clears `_pending_tasks`.
- **Mechanism / tests:** `tests/test_telemetry.py` (`_drain_telemetry_after_test`
  autouse fixture; `TestDrainSafety::test_drain_clears_a_pending_write`);
  relies on `core/telemetry.py::drain()` + the `_pending_tasks` strong-ref set.

### [2026-05-31] [ACTIVE] Hand-written fixtures are a regression net, not a discovery tool — expand them for breadth

- **Context (B3).** Expanded the extraction gauntlet from 5 to 10 site
  categories (forum Q&A, academic, government, press release, e-commerce). The
  tension: anti-pattern #6 says hand-written fixtures "only contain noise you
  already anticipated", so a gauntlet can't *discover* new noise (only
  `live_check`/dogfooding does that).
- **Rule — know what each test is FOR.** A hand-written fixture corpus is a
  **regression net**: it pins "the cleaner still handles category X well" so a
  future refactor can't silently break forum/academic/gov/press/commerce
  extraction. That value scales with **category breadth**, not with cleverer
  noise. So expand the gauntlet to cover more *real research surfaces*; don't
  pretend it substitutes for live dogfooding (keep both — §6 cadence).
- **Concrete extraction note surfaced while writing fixtures.** trafilatura
  renders a **single-line** `<pre><code>` as *inline* code, not a fenced block,
  and inline `<code>x</code>` tokens mid-sentence fragment the surrounding prose
  onto separate lines (hurting density). Multi-line code blocks render as proper
  fenced ```blocks. Implication: realistic code fixtures should use multi-line
  snippets — and an agent reading a terse Q&A page may see code as inline spans.
- **Gate discipline.** Adding diverse categories pulled the average toward the
  gate (8.5 exactly at first). Rather than weaken the gate, I made the weakest
  fixture (a trivial single-line-code Q&A) *more realistic* (multi-line code, as
  real Stack Overflow answers have), which lifted it honestly to a 8.72 average.
  Give a gate margin by improving representativeness, never by lowering the bar.
- **Mechanism / tests:** `tests/test_extractor.py` (`GAUNTLET_FIXTURES` now 10;
  `TestGauntletScores::test_new_categories_meet_floor`,
  `test_corpus_has_at_least_ten_categories`).

### [2026-05-31] [ACTIVE] Measure a meta-metric off the ledger you already maintain, not a new empty store

- **Context (B2).** The backlog asked to "add a `patch_landed_at` column to the
  `telemetry` schema" to measure MTTI (mean time to improvement). Investigation:
  a per-call telemetry *event* has no "patch", and alerts are recomputed
  statelessly on every `analyze_telemetry` run (never persisted) — so there is
  no `alert_first_seen` to subtract from, and nothing would ever populate a new
  table. Building it = dead infra (cf. the "no data is not healthy" lesson).
- **Rule.** **Before adding a new store/schema for a metric, ask what *already*
  records the events you'd measure.** Here the project's real, continuously
  maintained alert→patch ledger is the **backlog** itself (`METHODOLOGY §5`):
  every reactive row is a discovered problem, every DONE is a landed fix. Adding
  a `disc:`/`DONE` date convention + a parser in `status.py` measures MTTI from
  *real* data with **zero new write-friction** and no second source of truth to
  drift. A metric that rides the artifact you already keep accurate is honest by
  construction; a metric that needs a new manually-populated store will sit at
  "no data" and lie.
- **Honest negative finding.** The computed MTTI is **≈ 0 days** — this agent
  fixes flagged issues in the same session it finds them. A meta-metric that
  comes out trivial is still worth shipping: it (a) records the true baseline so
  a future *regression* (a lingering item) becomes visible, and (b) redirected
  the useful signal to **oldest-open-flag age**, which actually feeds "what to
  do next" (Trigger Hierarchy §5). Don't suppress a true-but-boring result.
- **Reframing precedent.** Same shape as B1 (calibrate against the *LLM*
  consumer, not a human) and B23 — a literally-specified backlog item was
  *mis-specified*; implementing its **intent** beat implementing its letter.
- **Mechanism / tests:** `scripts/status.py` (`parse_backlog_dates`, `mtti`,
  `mtti_line`) + `tests/test_scripts.py::TestBacklogMTTI`; convention documented
  in `docs/METHODOLOGY.md` §5 header.

### [2026-05-31] [ACTIVE] Changing a gate's scorer: prove the gate region is byte-identical, fix only the broken range

- **Context (B26).** B1 calibration showed `eval_judge` over-rated thin/empty
  extractions (a `"# Title / Loading…"` fragment scored 5.0/10 — "no noise" read
  as "clean"). Fixing it means editing `score_markdown`, which **is the ≥8.5
  Gauntlet merge gate** — a careless change could silently shift what passes.
- **Rule.** When you modify the function behind a gate, the change must be
  **localized to the broken range and leave the gate's operating region
  provably unchanged.** Don't just check "tests still pass" — show the gate
  region is *byte-identical*. Here: scale the noise reward by
  `min(1, len(body)/150)`, which is 1.0 for any real article (hundreds+ chars)
  and only bites near-empty bodies. Evidence: the 4 golden fixtures + the
  code-heavy sample scored *exactly* the same before/after, while the thin
  fragment dropped 5.0→1.59 and overall judge↔consumer r rose 0.79→0.932.
- **Corollary.** A calibration harness (`calibrate_judge.py`) isn't just a
  one-time report — it's the **regression instrument** that proves a scorer
  change improved the low range without disturbing the gate. Re-run it as the
  "before/after" check whenever you touch the scorer.
- **Left deliberately unfixed.** The remaining low-range divergences are
  *under*-ratings of content-that-contains-noise (paywall CTA, ad line). That is
  intentional gate behavior — penalizing noise is the whole point — so chasing
  those would weaken the gate, not improve it. Know which divergences to fix and
  which to leave.
- **Mechanism / tests:** `evals/eval_judge.py` (`_MIN_CONTENT_CHARS`,
  content-sufficiency gate) + `tests/test_judge.py::TestThinContentGate`.

### [2026-05-31] [ACTIVE] Calibrate the quality proxy against the real consumer — and trust it only where the gate lives

- **Finding (B1).** `eval_judge`'s 3-axis heuristic (noise/structure/density →
  0–10) gates the Gauntlet at ≥ 8.5. Calibrating it against the **consumer's**
  holistic rating (`evals/calibrate_judge.py`, 11 samples) gave **Pearson
  r = 0.79** — and, crucially, the **gate region is well-calibrated**: every
  high-quality anchor lands 8.5–9.25 vs. a consumer 8.5–9.0. So the 8.5 gate
  genuinely means "good", which was the open question.
- **Reframing that mattered.** The backlog said "calibrate against *human*
  ratings (blocker: human availability)". Wrong target: the consumer of
  `read_article` is the **LLM agent**, not a human. Calibrating against the
  agent-as-consumer is both *more correct* (it's who actually reads the output)
  and *unblocked*. **Rule: calibrate a quality proxy against whoever actually
  consumes the output — for an LLM tool, that's the LLM, not a person.**
- **Two real miscalibrations, both in the LOW range (→ B26).** (1) A near-empty
  `"# Title / Loading…"` fragment scores **5.0/10** because the noise axis pays
  a full 4/4 for *absence of noise* even with no content — **empty reads as
  clean.** (2) Clean-but-unstructured/short prose is under-rated (no headings
  ⇒ −1.5). **A single 0–10 number hides axis-level divergence; "well-calibrated"
  is range-specific — verify the region your gate actually uses, and don't
  assume it generalizes to the rest of the scale.**
- **Self-reference guard.** I wrote both the samples and the ratings, so this
  risks the "fixtures aren't real usage" trap. Mitigations: 4 of 11 samples are
  *real* golden fixtures; ratings were set on a written rubric *before* reading
  heuristic scores; and the worst divergence (thin_fragment, Δ +4.0) is reported
  honestly rather than massaged away. The value is in the *divergences*, not the
  headline r.
- **Mechanism / tests:** `evals/calibrate_judge.py` (`calibrate`, `pearson`,
  `load_samples`) + `tests/test_judge.py` (`TestPearson`, `TestCalibrationSet`,
  `TestCalibrationResult` — pins r ≥ 0.6 and the gate-region trustworthiness).

### [2026-05-31] [ACTIVE] Curated marker lists extend 3+ times — incompleteness is structural, not a bug

- **Finding (B25).** The leading-Wikipedia-chrome marker list needed extending a
  **third** time: person/sports (B9) → company/website (B18) → programming
  language (B25, after a Rust run leaked the language infobox). Each extension
  was triggered by a *new domain* of real research, not by a coding mistake.
- **Rule (reinforces the [position + marker] entry below).** When the same
  curated list (here `_WIKI_CHROME_MARKERS`; cf. `source_quality` allowlist)
  needs extending on *every new content domain*, treat its incompleteness as
  **structural, not a defect** — budget for "real usage will add markers" rather
  than chasing completeness up front. The thing that keeps each extension *safe*
  is the orthogonal gate (leading-position), not the list being exhaustive.
- **Precision discipline that held again.** Only added keys **unique** to a
  language infobox (`typing discipline`, `filename extension`); deliberately
  excluded `paradigm` / `first appeared` / `stable release` because those are
  exactly the *columns* of "Comparison of programming languages" tables — adding
  them would risk stripping a legit leading comparison table. Same exclusion
  logic as B18's `headquarters`/`founder`.
- **Mechanism / tests:** `utils/cleaner.py::_WIKI_CHROME_MARKERS` +
  `tests/test_extractor.py::TestLeadingWikiChrome`
  (`test_strips_programming_language_infobox`,
  `test_preserves_language_comparison_table`). Verified live: the real Rust
  Wikipedia article now opens with prose, 0 infobox keys in the first 1500 chars.

### [2026-05-31] [ACTIVE] If you hand-write the same orchestration scaffold N times, bake it into a command

- **Finding.** Across the 2026-05 dogfooding runs (Sam Altman, Meta LLM, Mitoma,
  DuckDuckGo, 辺地共聴, Silicon Valley, Rust) the agent re-authored the *same*
  throwaway `.scratch_*.py` six times: multi-search → triage by `source_tier` →
  drop `near_duplicate` → dedup by host → read top N → print snippets. Identical
  plumbing every time. That per-task scaffolding is a recurring tax on the
  maintaining agent, and re-writing it by hand also re-introduces small bugs.
- **Rule.** **Reducing the agent's own per-task plumbing is a first-class
  usability win, not a side quest.** When you notice you've written substantially
  the same orchestration code more than ~3 times, promote it to a reusable
  command (`scripts/research.py "<topic>" [--region jp-jp] [--recent] [--read N]`)
  whose docstring is the API. The command must *only orchestrate existing tools*
  (search_web / read_article / suggest_queries + the noise auditor) — no new
  retrieval logic — so it can't drift from the real pipeline. Extract the one
  non-trivial pure function (`triage`) and unit-test it; leave the network I/O
  to the tools that already have coverage.
- **Guard.** The win is "less typing for the agent," not "more abstraction." If
  the scaffold isn't actually repeated, don't build the command — premature
  tooling is the same anti-pattern as premature optimization.
- **Mechanism / tests:** `scripts/research.py` (`triage` pure fn + thin async
  `run`) + `tests/test_scripts.py::TestResearchTriage` (authoritative-first,
  near-dup skip, one-per-host, capped-at-read_n). Import-smoke only for `run`
  (it hits the network). Surfaced B25 on first real use (Rust Wikipedia infobox
  chrome leak), proving the command also doubles as a dogfooding harness.

### [2026-05-31] [ACTIVE] Document the capabilities the agent can't discover — the docstring is the API

- **Finding (B23).** A "non-AI Silicon Valley trends" run stalled because the
  agent didn't know DuckDuckGo's `-term` exclusion (and `site:`/`"phrase"`/`OR`)
  passed straight through `search_web`. The capability *existed and worked* —
  it was simply never written in the tool's docstring, which (per CLAUDE.md) is
  the agent's only "API reference".
- **Rule.** **An undocumented capability does not exist to the agent.** A tool's
  docstring is its API: if the agent can't see a feature there, it won't use it,
  no matter how well it works. When you find yourself surprised an agent didn't
  use a supported affordance, the bug is usually missing docs, not missing code.
  (Pure-docstring fixes still need a regression test — here, that the operators
  reach the backend verbatim — so the documented contract can't silently rot.)
- **Mechanism / tests:** `tools/search.py` docstring + `tests/test_search.py`
  (`test_search_operators_pass_through_verbatim`, `test_operators_survive_url_encoding`).

### [2026-05-30] [ACTIVE] The stack was UTF-8/English-centric — non-English usage broke 3 things

- **One Japanese research run ("片地/辺地共聴", government policy) exposed three
  English/ASCII assumptions baked in across the stack:**
  1. **Encoding (B20, fixed).** `read_article` returned **mojibake** for
     `soumu.go.jp` (総務省) — a `Shift_JIS` page with no HTTP charset header.
     curl_cffi defaulted to utf-8. Fix: `decode_html` detects charset from
     bytes (header → `<meta>` → `charset_normalizer` → utf-8). The *primary*
     authoritative source for the query had been unreadable garbage.
  2. **Source tier (B21, fixed).** `.go.jp` / `.lg.jp` (Japanese government)
     tagged `unknown` — the `_AUTH_TLDS` allowlist was `.gov`/`.gov.uk` only.
     Extended to JP/FR/DE/EU/IN/KR/… gov + academic TLDs.
  3. **Dedup (B22, fixed).** `_title_tokens` used `[a-z0-9]+`, so Japanese
     titles tokenized to ~nothing → `near_duplicate` silently no-op on CJK.
     Now emits CJK character bigrams.
- **All three closed (2026-05-30).** One Japanese run → three fixes (B20/B21/B22).
  Each was a latent "works in English/UTF-8 only" assumption; none had an error
  message — they failed *silently* (garbage text, `unknown` tags, no-op dedup).
- **Rule.** **"Works" usually means "works in English/UTF-8".** Charset,
  trusted-domain lists, and tokenizers all encode a default locale. Real
  non-English usage is the only thing that surfaces these — and a *primary
  authoritative source rendered as garbage* is a silent, severe failure
  (no error code, just unusable text). Test with a non-Latin, non-UTF-8 target.
- **Mechanism / tests:** `core/http.py::decode_html`,
  `tests/test_http.py::TestDecodeHtml`. (B21/B22 recorded for follow-up.)

### [2026-05-30] [ACTIVE] Strip noise by position + marker, not by type — leading Wikipedia chrome

- **The risk (B9, deferred twice for it).** Wikipedia infoboxes / "Part of a
  series on" nav templates leak as a messy *leading* markdown table. The naive
  fix — "strip leading tables" or "strip tables with infobox-ish keys" — would
  also eat **legitimate data tables** (comparison tables, stats, the asyncio
  docs tables). Removing real content is worse than leaving noise.
- **The safe discriminator: position AND marker, both required.** Strip a table
  only if it is (a) in the **leading region** (before the first prose sentence,
  modulo a leading H1) AND (b) carries a **high-precision infobox/nav marker**
  ("part of a series on", "personal information", "date of birth", "notable
  work", "senior career", …). Either signal alone is unsafe; together they are
  high-precision. Mid-article tables (always after prose) and marker-less
  leading tables are never touched.
- **Verified on real articles** (Sam Altman / Mitoma / LLM all now open with
  prose) and with explicit negative tests (prose-first body, leading data table
  without a marker, mid-article table) + zero dogfood-baseline drift.
- **Rule.** **When a noise pattern overlaps with legitimate content, gate on
  *two independent signals*, not one.** A single heuristic strong enough to
  catch the noise is usually strong enough to catch real content too;
  intersecting two weak-alone signals gives precision without collateral.
- **Follow-up (B18, same day).** The marker list was person/sports-centric, so
  the next real research run (DuckDuckGo) immediately leaked a *company*
  infobox. Like the `source_quality` allowlist, **a curated marker/keyword list
  is inherently incomplete — expect real usage to extend it.** Added
  company/website markers (still excluding generic words that double as
  comparison-table columns). The "two-signal" rule held: even the new markers
  are gated by leading-position, so the extension stayed safe.
- **Mechanism / tests:** `utils/cleaner.py::strip_leading_wiki_chrome`,
  `tests/test_extractor.py::TestLeadingWikiChrome`.

### [2026-05-30] [ACTIVE] Dedup by marking, not removing — duplicates are corroboration

- **The naive read of B16** was "collapse the 6 'Mitoma out of squad' results to
  one — they're redundant." That would have been **wrong**: in the very report
  that surfaced B16, the *fact that 6 independent sources said the same thing*
  was the reliability signal I used to mark the claim 🟢 high-confidence.
  **Removing duplicates destroys corroboration.**
- **Fix.** `near_duplicate` is a *flag*, not a filter — results are never
  removed. The agent skips *re-reading* a near-dup (saves a `read_article` call)
  but still sees the count. Detection is conservative (Jaccard ≥ 0.6 on title
  tokens): it catches the clear listicle rewrites but **deliberately keeps
  same-story-different-angle** results (J ≈ 0.3), which carry distinct value.
- **B15 synergy.** Within a duplicate cluster the *primary* (unflagged) prefers
  an `authoritative` source — so a wire-service story outranks the SEO rewrites
  of it. Two signals composing: trust + redundancy.
- **Rule.** **When "deduplicating," ask what the duplicates *mean*.** For
  research, repetition across independent sources is evidence, not noise —
  surface it, don't suppress it. Mark > remove whenever the removed thing
  carries information.
- **Mechanism / tests:** `tools/search.py` (`_mark_near_duplicates`,
  `_title_tokens`, `_jaccard`), `tests/test_search.py::TestMarkNearDuplicates`.

### [2026-05-30] [ACTIVE] One TLS fingerprint is not enough — rotate on a block

- **Context (B17).** B15's `source_tier` steered the agent to read Reuters first
  — but `read_article` failed Reuters with a durable error. Diagnosis across
  fingerprints: `jp.reuters.com` returns **401 to chrome131/124/120 and 200 to
  safari17_0**. The single hardcoded `chrome131` fingerprint was the problem.
- **Fix.** `core/http.py` now tries `_IMPERSONATE_TARGETS = (chrome131,
  safari17_0)` and rotates to the next on a **401/403 block** (only — blocks
  don't retry, so it's cheap; genuine network errors are not multiplied across
  fingerprints). Reuters now reads.
- **Two sharp sub-lessons:**
  1. **Anti-bot is fingerprint-specific.** A site blocking "bots" may just be
     blocking *Chrome's* TLS signature. Diversity (Safari) is a cheap escape
     hatch — don't assume one impersonate target covers the web.
  2. **A 401 from a website is usually anti-bot, not auth.** It was mis-mapped
     to `CONN_ERROR` (implying a network fault); now `BLOCKED_403`. Map the
     *meaning*, not the literal HTTP word.
- **Throughline.** This bug only existed *because* B15 made the agent prefer
  authoritative sources — fixing one gap exposed the next. Real-usage PDCA
  compounds: each working feature reveals the next real friction.
- **Mechanism / tests:** `core/http.py` (`_IMPERSONATE_TARGETS`,
  `_fetch_with_target`), `tests/test_http.py`. Supersedes the load-bearing part
  of the 2026-05-28 `[HISTORICAL] curl_cffi` entry.

### [2026-05-30] [ACTIVE] Real search returns what *ranks*, not what's *authoritative*

- **Meta-LLM research run.** With search finally working, a real query
  ("Meta Llama LLM news 2026") returned **8/8 SEO/content-farm blogs** and zero
  primary sources (Reuters / The Verge / ai.meta.com). The corroboration across
  many independent low-authority blogs gives a *rough* consensus, but the tool
  offers **no source-quality signal** — the agent can't tell a content farm
  from Reuters. Recorded as B15 (source-quality hint) + B16 (near-duplicate
  listicles waste reads).
- **Reconfirmed:** B11 (autocomplete = shallow navigational variants:
  "meta llama 4/3/ai/models", crowding out the `site:` primary-source
  templates) and B14 (no freshness/date on results).
- **Rule.** A web-search tool optimizes for *retrievability*, which SEO games.
  For Deep Research, "found it" ≠ "trustworthy". The *agent* must weight sources
  and corroborate across independent ones — and reports must label
  secondary/unverified claims as such.
- **Fix (B15, 2026-05-30).** `source_tier` on every result. Key design call:
  tag `authoritative` with a **high-precision allowlist** but **never guess
  `low_quality`** — a content farm and a legit small blog are byte-identical in
  structure, so a confident "low quality" label would defame real sites.
  Asymmetric confidence: name what you trust, default everything else to
  `unknown` (≠ bad). **When you can identify the good with precision but not the
  bad, label only the good — don't fabricate a negative verdict you can't
  defend.** (`core/source_quality.py`.)
- **Follow-ups (B21 2026-05-30, B24 2026-05-31).** The allowlist is *expected*
  to grow from real usage: B21 added national-gov TLDs (`.go.jp`…) after a
  Japanese run; B24 added analyst/research firms (Gartner, Deloitte, Crunchbase,
  IEEE CS…). A sharper precision rule emerged in B24: **a domain that runs a
  per-author contributor network (Forbes, Inc.) cannot be certified by its
  domain** — trust attaches to the author, not the host, so such domains stay
  `unknown` even though they're "famous". Domain-level trust requires
  domain-level editorial control.

### [2026-05-30] [ACTIVE] Search resilience — bypass the library when it has a single backend

- **The fix for the SPOF (B12).** The Sam Altman run dead-ended because
  `search_web` failed. Root cause: the installed `duckduckgo-search` proxies
  *all* backends (`auto`/`html`/`lite`) through `https://www.bing.com/search`;
  with bing DNS-blocked, the tool was 100% dead even though `duckduckgo.com`
  was reachable. **A dependency's "options" can be an illusion — verify they're
  actually independent.**
- **The fix.** `_ddg_html_fallback` skips the library entirely and scrapes DDG's
  own `html.duckduckgo.com/html/?q=` via our stealth `fetch`, parsing
  `div.result` and decoding the `uddg=` redirect param. Triggered only when the
  primary library raises, so normal environments are unaffected. Verified live:
  search went from **100% dead → working**, and the originally-blocked research
  task completed with real, source-cited results.
- **Test-isolation bug it exposed [ACTIVE].** Running the live fallback cached
  real results in the shared `./.cache/cache.db`; error-path unit tests (which
  expect a cache miss) then read those cached lists and failed flakily. **Tests
  must not share mutable state with real runs** — `conftest.py` now isolates
  `DEEPSEARCH_CACHE_DIR` to a temp dir. (Also: mock the fallback to `[]` in
  error-mapping tests so they don't make real network calls.)
- **Mechanism / tests:** `tools/search.py::_ddg_html_fallback` / `_decode_ddg_href`,
  `tests/test_search.py::{TestDdgHtmlFallback,TestSearchWebFallbackWiring,TestDecodeDdgHref}`,
  `tests/conftest.py` (cache isolation).

### [2026-05-30] [ACTIVE] Real research run (Sam Altman) — search is the loop's lifeline

- **Task.** "Investigate Sam Altman's recent schedule." A genuine end-to-end
  research use, run through the real tools.
- **Outcome: blocked, honestly.** `search_web` failed (CONN_ERROR — bing
  backend down here), so the loop dead-ended at step 1. `read_article` on
  Wikipedia gave *background* (born 1985, Stanford dropout, OpenAI, spouse) but
  not a *schedule*; "recent" requires live search. **I did not fabricate a
  schedule from training memory** — and that refusal is the system working as
  designed (fact-grounded > confident fabrication).
- **Pain points recorded** (→ backlog B11–B14):
  - **SPOF (B12):** search down ⇒ whole research loop dies; no fallback path.
    `suggest_queries` yields queries (useless without search), `read_article`
    needs URLs the agent can't get.
  - **Misleading hint (B13):** "retry / broaden query" is wrong advice for a
    durable backend outage; the agent loops on rewording.
  - **Autocomplete is tabloid (B11, concrete):** real "Sam Altman" autocomplete
    = "net worth / husband / sister / age" — popularity, not research vectors,
    and it crowds out the lateral templates.
  - **Infobox leak (B9, concrete):** the real Wikipedia article opened with the
    infobox dumped as a broken markdown table ("Sam Altman | | |---|---| | Born
    | …").
  - **No freshness (B14):** `published_date` always null ⇒ can't filter for
    recency on a time-sensitive query.
- **Rule.** **In a tool-chain, the discovery step (search) is a single point of
  failure for the entire workflow — harden it or give the agent a documented
  fallback.** And: a research tool that *can't* fabricate is a feature, not a
  bug — the empty-handed honest answer beats a confident hallucination.

### [2026-05-30] [ACTIVE] A mock of the unit-under-test hid a feature that never worked

- **Discovery.** Asked to run the real search tool: `search_web` is dead here
  (the `duckduckgo-search` library routes *all* backends through `bing.com`,
  which is DNS-blocked — a Prime Directive 3 library-drift note in itself). So
  I ran the other search-family tool, `suggest_queries`, live — and its
  autocomplete returned `[]`. Cause: `_fetch_autocomplete` called
  `https://duckduckgo.com/ac/` **with no `?q=` parameter**. The topic was never
  sent. Autocomplete had returned `[]` since Phase 3 — a **dead feature**.
- **Why no test caught it.** The Stuck Agent tests `@patch`ed
  `_fetch_autocomplete` *itself* to return canned phrases. They asserted the
  merge logic around a function they had replaced — so they were green while
  the real function never worked. **Mocking the unit under test validates your
  mock, not your code.**
- **Rule.** Mock at the **boundary** (the `fetch` call / network), never the
  function whose behavior you are testing. At least one test must exercise the
  real request-building path. (Added `TestAutocompleteRequest`: mocks `fetch`,
  asserts the topic reaches the URL.)
- **Corollary (the session's throughline).** Every real bug this session —
  the auditor comma false-positive, citation/editorial leaks, and now a dead
  autocomplete — was invisible to self-authored fixtures/mocks and obvious the
  instant real tools hit the real web. **Periodic real-usage is not optional
  QA polish; it is the only source of the bugs your test corpus is blind to.**
- **Bonus library-drift note [ACTIVE].** `duckduckgo-search` (installed v8)
  now proxies every backend (`auto`/`html`/`lite`) through `https://www.bing.com/search`.
  "DuckDuckGo search" is bing-backed; a blocked bing host kills all of
  `search_web` regardless of `backend=`. The `/ac/` autocomplete endpoint is
  separate and hits `duckduckgo.com` directly.
- **Mechanism / tests:** `tools/suggest.py::_autocomplete_url` / `_fetch_autocomplete`,
  `tests/test_suggest.py::TestAutocompleteRequest`. Follow-up: B11 (live
  autocomplete now crowds out primary-source templates).

### [2026-05-30] [ACTIVE] Fixtures are not real usage — the Check was self-referential

- **The challenge (from the project owner).** "Are we actually doing the PDCA
  cycle based on *real* usage?" Honest answer: **no.** For many cycles the
  Check (C) ran against **hand-written HTML fixtures** and `--demo` data. Those
  fixtures only ever contained noise *I had already thought of*, so the Check
  could confirm but never *surprise*. `search_web` had never worked here (bing
  backend blocked), and real `read_article` output had never been read
  critically. The loop was rigorous in machinery but self-referential in input.
- **What real usage found in ONE pass** (pointing `read_article` at 4 live
  pages — docs.python.org, PEP-8, Wikipedia, modelcontextprotocol.io):
  1. **Auditor false positive.** The social-count regex `[\d.,]+` matched a
     bare comma, so prose "…structured concurrency, like" flagged as
     ENGAGEMENT_BAIT. Fixtures never had "comma + word", so it never showed.
     Fix: require a leading digit (`\d[\d.,]*`).
  2. **Citation leak.** Real Wikipedia prose carried inline `[1]`/`[12]`
     citation superscripts — context pollution my fixtures never contained.
     Fix: `strip_reference_markers` (fence-aware: prose stripped, code indices
     `arr[1]` preserved).
  3. **Editorial annotations + a content trap.** Pressure-testing whether to
     bother snapshotting real pages (B10) instead surfaced a *better* find:
     `[citation needed]`, `[update]`, `[note 1]`, `[dubious – discuss]` leak as
     noise — BUT the same LLM/Transformer pages contain `[MASK]`, `[UNK]`,
     `[CLS]`, which are **real NLP tokens**. A blanket `[word]` strip would
     destroy content. Fix: an **allow-list** of editorial phrases (`_EDITORIAL_RE`)
     — preserves anything not explicitly known-noise. *Declining B10 and
     verifying why found more value than doing B10 would have.*
- **Rule.** **A self-authored test corpus validates your assumptions, not
  reality. Periodically run the real tools against the live web and *read the
  output as a user*.** Fixtures lock in what you already know; live usage is
  the only source of what you don't. Findings flow back as fixtures/patterns.
- **Institutionalized.** `scripts/live_check.py` makes the real-web Check a
  one-command habit (added to the monthly cadence). Backlog: capture
  representative live pages as permanent fixtures (B10); strip "Part of a
  series on" nav-template tables (B9, seen on Wikipedia).
- **Mechanism / tests:** `scripts/live_check.py`,
  `utils/cleaner.py::strip_reference_markers`,
  `tests/test_extractor.py::TestCitationMarkers`,
  `tests/test_dogfood_audit.py::TestMatchedSignal` (comma false-positive guard).

### [2026-05-30] [ACTIVE] Aggregate activation — "no data" is not "healthy"

- **Context.** The aggregate probe (`analyze_telemetry.py`) had been dormant —
  dev mocks `fetch`, so `telemetry.db` only ever held synthetic rows.
  `scripts/collect_telemetry.py` activates it by driving the *real* tools.
- **Connectivity reality (operational note).** In this environment
  `read_article` (curl_cffi) reaches live sites fine, but `search_web` fails:
  DDGS routes to a **bing** backend whose host is DNS-blocked, so every search
  is `CONN_ERROR`. Useful operational fingerprint: a wall of `search_web`
  CONN_ERROR with healthy `read_article` = the DDGS backend is unreachable, not
  the whole network. (A raw socket to duckduckgo.com:443 can succeed while the
  library's bing backend still fails — don't infer "no network" from a search
  failure alone.)
- **The bug the real run exposed.** With only 9 rows, the analyzer confidently
  printed "add a domain adapter for httpbin.org" off **3 samples**, and its
  empty-state said "✅ healthy". Both over-claim: a 3-sample alert is a
  coin-flip, and "no alerts on thin data" means "can't see one yet", not
  "healthy".
- **Fix (count).** `MIN_ROWS_FOR_CONFIDENCE` (50). Below it the report shows a
  **LOW CONFIDENCE** banner, labels alerts **PROVISIONAL**, and refuses to call
  thin data "healthy". **Rule: a metrics tool must distinguish "no signal" from
  "not enough data to have a signal" — silence on thin data is not health.**
- **Fix (representativeness).** Row *count* alone is not trust: 50 rows of a
  contrived battery — or of a dead backend echoing one error — is still
  unrepresentative. `tool_skew()` flags any tool that is ≥90% one non-success
  status (`SKEW_DOMINANCE`, min `SKEW_MIN_CALLS`); skew keeps verdicts
  PROVISIONAL **regardless of volume** ("more rows will NOT fix skew"). This
  closes the trap I created with `collect_telemetry.py`: re-running the seeder
  to cross the row floor can no longer manufacture false confidence.
  **Rule: gate confidence on representativeness, not just sample size; a
  metric you can satisfy by re-running a generator is gameable by design.**
- **Mechanism / tests:** `evals/analyze_telemetry.py`
  (`MIN_ROWS_FOR_CONFIDENCE`, `tool_skew`, `SKEW_DOMINANCE`),
  `scripts/collect_telemetry.py`, `tests/test_analyze_telemetry.py` (14 tests).

### [2026-05-29] [ACTIVE] Automate what the agent is bad at, not what it's good at

- **The trap (B7 as written).** The backlog said "auto-propose a regex from an
  auditor finding." Building that literally would have been near-worthless:
  generating a regex string is a *core LLM strength* — not where an agent burns
  effort or makes mistakes. Automating it adds surface area for ~zero gain
  (violates the net-complexity rule).
- **Where the agent actually fails.** This session, writing cleaner regexes by
  hand, the real errors were: the trailing-`\b`-after-punctuation trap, and the
  ever-present risk of an **over-broad** pattern that silently eats real prose
  (the cleaner's worst failure mode). Verifying "what else does this pattern
  match?" by hand means grepping every fixture and eyeballing — tedious and
  error-prone. *That* is the automatable part.
- **Reframe.** `scripts/propose_noise_regex.py` became a **safety preview**, not
  an autocomplete: generalize a candidate (numbers → `\d+`, guarded boundaries),
  confirm it matches the offending line, and compute its **blast radius** across
  the live corpus — failing if it would remove any already-clean prose. Judgment
  stays with the agent; verification toil moves to the tool.
- **General rule.** When you set out to "automate an agent's task", first ask
  *which half*. Automate the **mechanical-verification** half (where LLMs are
  weak: exhaustive checking, blast radius, boundary traps). Leave the
  **generative/judgment** half to the agent (where LLMs are strong). Automating
  the strong half is motion without progress.
- **Mechanism / tests:** `scripts/propose_noise_regex.py`,
  `evals/dogfood_audit.py::matched_signal`, tests in `tests/test_scripts.py`
  (`TestCandidateRegex`, `TestBlastRadius`, `TestProposeForLine`).

### [2026-05-29] [ACTIVE] Agent DX — ground truth is one command, not prose

- **Principle clarified by the maintainer.** DeepSearch-MCP is a tool *for*
  LLMs, maintained *by* LLMs. The sole usability metric is the agent's, not a
  human's. So agent-experience friction is a first-class bug, not polish.
- **The friction (self-identified while dogfooding).** An agent's largest
  recurring tax is **re-orientation after context compaction**: "how many
  tests now? are gates green? what's next?" That cost ~5 tool calls across 3
  files. And running the 3 merge gates as separate commands let an agent nearly
  report "green" with one gate unrun.
- **Fix.** `scripts/status.py` (one-call live orientation) and
  `scripts/verify.py` (single-exit-code merge gate). A top-of-file
  **Orientation** block in `CLAUDE.md` (the only always-loaded doc) points the
  next agent at them before it trusts a stale model.
- **Anti-pattern explicitly rejected.** A committed `STATUS.md` was the obvious
  idea — and wrong. A stored status file drifts and becomes the very stale
  artifact it was meant to fix. **Rule: for agent orientation, *compute* ground
  truth on demand; never persist it.** (Same instinct as Prime Directive 1:
  stale context is noise.)
- **Net-complexity rule.** A DX fix must not *grow* the surface area it
  complains about. `verify.py` *replaced* three hand-typed commands in
  `MAINTENANCE.md` (fewer, not more); `status.py` reads existing files rather
  than adding a new one to sync.
- **Docs map > docs consolidation.** With 11 docs, the friction is *routing*
  ("which doc for X?") and *sync-risk* (touch one, dangle a reference).
  Consolidation is high-risk and lossy; a committed map drifts. The fix is a
  *generated* map + integrity checker (`scripts/docs_map.py`): it prints each
  doc's role/purpose and **mechanically** fails on dead relative links (now a
  `verify.py` gate), converting "remember to keep docs in sync" from discipline
  into an enforced check. It earned its keep on run 1 — caught 2 orphaned docs
  and a stale `ROADMAP` header. **Rule: enforce doc integrity mechanically;
  don't rely on the agent remembering to cross-check N files.**
- **Orphan allow-list = signal hygiene, not metric-gaming.** A genuinely
  standalone doc (one-time snapshot like `BASELINE.md`) is allow-listed so the
  orphan warning only fires on *accidental* undiscoverability. A check that
  always warns trains the agent to ignore it (the same alert-fatigue trap as
  benign test warnings).
- **Environment note.** The agent tool-shell often lacks `uv` / `~/.local/bin`
  on PATH even when the login shell has them. Scripts must auto-detect
  `.venv/bin/` (see `_venv_bin`), and docs should not assume `uv run` works.
- **Mechanism / tests:** `scripts/status.py`, `scripts/verify.py`,
  `tests/test_scripts.py` (14 tests).

### [2026-05-29] [ACTIVE] Noise-Leak Auditor — systematizing the dogfooding CHECK step

- **Problem (a methodology gap).** The dogfooding loop's CHECK step was "a human
  reads the whole extraction body and *hopes* to notice leftover noise." Two
  failures: (a) unreproducible — different reviewers catch different things;
  (b) static fixtures = one-shot — once their noise is patched, re-running the
  harness surfaces nothing, so the semantic loop runs dry and *feels* done.
- **Root-cause of the backlog mis-fire (B5).** Backlog item B5 proposed putting
  a "noise leak hint" inside `analyze_telemetry.py`. That is impossible:
  `telemetry.db` stores **no response bodies** — only `(timestamp, tool_name,
  input_summary, status, tokens_approx, latency_ms, domain)`. The analyzer has
  nothing to scan. **Rule:** validate a backlog item against the data model
  *before* estimating it; an aggregate store can never answer a per-line
  semantic question.
- **Solution.** `evals/dogfood_audit.py` (`audit_markdown()`), wired into
  `dogfood_research.py` as STEP 4, lives where bodies exist (the dogfooding
  path). It runs on **post-cleaner** output, so anything it flags is by
  definition a leak the cleaner missed — a candidate for a new
  `_NOISE_LINE_RE` pattern or a domain adapter.
- **Two-tier design (the bug that taught it).** A single-tier, length-gated
  heuristic silently skipped a 16-word affiliate-disclosure sentence because
  "long line = prose." Fixed by splitting into **STRONG** signals
  (affiliate/sponsor/legal — fire at any length, never legitimate prose) and
  **SOFT** signals (promo CTA / metadata stub / engagement counts — fire only
  on short lines, so "we share a common goal…" is spared). **Rule:** a
  noise detector needs *two* sensitivities — some noise is unambiguous at any
  length, some is only noise when it's a short label.
- **Trailing-`\b` regex trap.** The METADATA_STUB alternation ended in `\b`,
  which failed on alternatives ending in punctuation (`Tags:`, `By J`) because
  there is no word boundary between `:`/letter and the following space. The
  `^\s*` anchor already scopes line-starts; drop the trailing `\b`.
- **Validation (Measurable).** New `zdnet` fixture → auditor reported 1
  suspected line (affiliate disclosure) before the cleaner patch, 0 after.
  Other 3 fixtures stayed at 0 (no false positives on real prose).
- **Mechanism / tests:** `evals/dogfood_audit.py` + `tests/test_dogfood_audit.py`
  (24 tests). The auditor *proposes*; the human *disposes* — findings are
  advisory, never auto-applied to the cleaner.

### [2026-05-29] [ACTIVE] Dogfooding Session — Real-World Cleaner Audit
- **Workflow:** `evals/dogfood_research.py` を実 `@track` 経由で実行し、AIエージェントフレームワーク（LangGraph / CrewAI / AutoGen）の調査タスクを実演。実環境を模した HTML フィクスチャ（TechCrunch / LangChain blog 風）+ patched fetch で抽出パスを end-to-end でテスト。
- **発見された4つの未捕捉ノイズ（v1 cleaner では除去できなかった）:**
  1. `Estimated reading time: 8 minutes` — 2026年スタイルの記事メタデータ。
  2. `Listen to this article on the X Podcast` — 音声 CTA（podcast 連携で増加）。
  3. `Written by Maria Santos — Senior AI Correspondent` — frontmatter author と重複するレポーターカード。
  4. `Continue reading to see the production deployment checklist` — lazy-load / paywall ゲート。
- **追加で発見された関連パターン:**
  5. `By signing up, you agree to our Terms` — newsletter 同意ゲート。
  6. `Get the latest in AI delivered to your inbox` — 受信箱訴求 CTA。
  7. `Tags: A, B, C` / `Posted in: X` — 末尾メタフッター。
  8. `Originally published in TechCrunch` — クロスポスト出典表記。
- **Rule (Cleaner v2 patterns):** 上記8パターンを `utils/cleaner.py` の `_NOISE_LINE_RE` に追加。テストは `tests/test_extractor.py::TestDogfoodingNoisePatterns` に格納。Gauntlet 平均は ≥ 8.5/10 を維持。
- **メタ教訓:** `analyze_telemetry.py` は**集計レベル**の問題（失敗率、トークン平均）は捕捉できるが、**個別の意味的ノイズ**（特定の宣伝文句）は捕捉できない。Telemetry 単独では不十分で、**人間（あるいは LLM）による出力の目視検査**が定期的に必要。Day 2 運用には Dogfooding を月次サイクルで組み込むこと。
- **Dogfooding スクリプトの再利用パターン:**
  1. `os.environ["DEEPSEARCH_TELEMETRY"] = "1"` を import 前に設定。
  2. `await telemetry.reset_for_tests()` でセッション開始時に clean DB。
  3. ネットワーク失敗 (`CONN_ERROR`) もそれ自体価値あるテレメトリ — sandbox でも有効。
  4. `patch("...fetch", AsyncMock)` で HTML フィクスチャを差し込み、real extraction pipeline を走らせる。
  5. 終了時に `await telemetry.drain()` で fire-and-forget をフラッシュ。
- **Follow-up automation:** この session で発見した4つのノイズが将来再導入されないよう、`evals/dogfood_regression.py` + `tests/test_dogfood_regression.py` + `evals/dogfood_baseline/` を構築。golden file 方式で extraction 出力を回帰検証する。

### [2026-05-28] [ACTIVE] Phase 6 — Day 2 Operations (Self-Healing PDCA)

これらは Telemetry (`telemetry.db`) で観測された運用パターンから導出された、**自動パッチ適用ルール**。エージェントとしてリリース後の保守を担当する場合、まず `evals/analyze_telemetry.py` を実行し、そのレポート結果に従って [METHODOLOGY.md](METHODOLOGY.md) の Operations Rules でアクションを起こすこと。

**Telemetry スキーマ:** `(timestamp, tool_name, input_summary, status, tokens_approx, latency_ms, domain)` — `core/telemetry.py` の `@track(tool_name, primary_input)` デコレータで自動記録。テスト時は `DEEPSEARCH_TELEMETRY=0` で無効化。

(Operations Rules 1–5 の詳細は [METHODOLOGY.md](METHODOLOGY.md) §3 を参照)

### [2026-05-28] [ACTIVE] Phase 5 — Adversarial Dogfooding (4 Prime Lessons)

これらは Persona A (Critic) のリサーチタスク実行ログから得られた、**エージェント視点での使いにくさ**に関する不変ルール。テストが通っても、これらに違反するコードはエージェントを殺す。

**Lesson 1: Tools must compose. Output of one tool MUST be valid input to the next.**
- **Anti-pattern observed:** `suggest_queries("AI agent memory management RAG")` returns `'"AI agent memory management RAG" criticism'`. Passed to `search_web` → 0 hits (exact-phrase match impossible).
- **Rule:** If a tool builds queries/URLs/identifiers for downstream tools, the output must be **immediately usable** without post-processing by the agent.
- **Mechanism (suggest.py):** `_render_topic()` quote-wraps only topics with ≤2 words; longer topics pass through as bare keywords.
- **Verification:** `tests/test_suggest.py::TestSmartQuoting` (7 regression tests).

**Lesson 2: Error hints must match the input type the tool received.**
- **Anti-pattern observed:** `search_web(query="...")` failure returned `hint: "Check URL validity"`. Agent never passed a URL → confusion → deadlock.
- **Rule:** A tool's error hint is a function of (error_code, **call_context**). The same `CONN_ERROR` from `search_web` and `read_article` must produce **different** hints.
- **Mechanism (errors.py):** `structured_error()` accepts `hint_override` and `retryable_override`. Each tool injects its own context-specific hint at the call site.
- **Verification:** `tests/test_search.py::TestSearchWebContextAwareHints` (5 regression tests).

**Lesson 3: Error messages must be sanitized before they reach the LLM.**
- **Anti-pattern observed:** DDGS raises with a 350-char message containing the raw Bing URL with query params and filters (`https://www.bing.com/search?q=...&filters=ex1%3A%22ez5_20236_20601%22`). Useless tokens.
- **Rule:** Strip all `https?://\S+` from outgoing error messages; replace with `[REDACTED_URL]`. Truncate at 200 chars.
- **Mechanism (errors.py):** `sanitize_error_text()` is invoked automatically inside `structured_error()`.
- **Why this matters:** A Deep Research loop with 50 tool calls and 10% error rate burns 5 × 85 ≈ 425 tokens on raw backend URLs without sanitization. Multiply by a $0.05/1k token rate and the cost is non-trivial across sessions.

**Lesson 4: Transient failures (DNS/timeout/reset) must signal `retryable=True`.**
- **Anti-pattern observed:** Generic `CONN_ERROR` returned `retryable: false` even for transient DNS failures. Agents see this and **permanently abandon** the search task — they don't even try once more.
- **Rule:** Detect transient-error patterns (`dns`, `timeout`, `reset`, `refused`, `unreachable`) in the raw exception message and flip `retryable` to `True`. Non-transient backend errors (invalid query, malformed input) stay `retryable=False`.
- **Mechanism (errors.py):** `is_transient_conn_error(message)` keyword detector. Used by `search_web._map_ddgs_exception` and `read_article`'s FetchError handler.
- **Verification:** `tests/test_search.py::TestTransientErrorDetection` (5 tests).

**Secondary Lessons:**
- **H1 vs frontmatter title dedup (FRICTION-D1):** Trafilatura emits `# Title` as the first H1; we already serialize the same string into frontmatter `title:`. `_strip_redundant_h1()` removes the duplicate (~5-10% token savings per article). `eval_judge.py` was updated to count frontmatter `title:` as an implicit H1 for the heading-levels structure bonus — so dedup doesn't fight the quality scorer.
- **Temporal-freshness queries belong in the top-3 (FRICTION-C3):** Most research tasks are time-bounded ("2025 trends"). `_VIEWPOINT_TEMPLATES` was reordered: `"{topic} 2025 OR 2026"` is now position 0.
- **Docstring USE WHEN / DO NOT USE WHEN must be mutually exclusive AND actionable:** Each `DO NOT USE WHEN` should name the alternative tool ("→ call X directly"). Each `USE WHEN` should include a quantifiable trigger ("last 2+ search rounds returned same sources").

### [2026-05-28] [ACTIVE] Phase 4 — 非HTML検出の設計判断
- **URL 拡張子ガード（ネットワーク呼び出し前）:** `.pdf`, `.zip`, `.jpg` 等の拡張子を `PurePosixPath(urlparse(url).path).suffix` で検出し、`fetch()` 呼び出し前にショートサーキットする。エージェントが PDF URL を渡すケースは頻発するため、ネットワーク往復を完全に省略できる。
- **Content-Type ガード（ネットワーク呼び出し後）:** サーバーが `.html` を持つ URL から `application/pdf` を返すケースに対応。`response.headers.get("content-type", "")` をチェックし、`application/pdf`, `image/*`, `video/*`, `audio/*`, `application/vnd.*` を除外する。
- **エラーコード `UNSUPPORTED_FORMAT`:** `retryable: false` / hint: "Skip this URL and search for an HTML alternative." — エージェントに「別のURLを探せ」と明示的に指示する。
- **E2E シミュレーション設計:** ネットワーク制限がある環境（CI等）のため `--demo` モードを実装。現実的な事前設定データでフルフローを検証できる。Live モードはそのまま実ネットワーク呼び出しを行う。
- **MCP クライアント設定 (2026年確認):** `claude_desktop_config.json` は `{"mcpServers": {"name": {"command": "uv", "args": ["--directory", "/path", "run", "python", "-m", "module"]}}}` 形式。`type: "stdio"` は省略可能（デフォルト）。macOS パス: `~/Library/Application Support/Claude/claude_desktop_config.json`。

### [2026-05-28] [ACTIVE] Phase 3 — suggest_queries の設計判断
- **DDG Autocomplete エンドポイント:** `https://duckduckgo.com/ac/?q=<topic>` は `[{"phrase":"..."}]` を返す公開 API。DDGS v8 には built-in suggest メソッドはない。`curl_cffi` の `fetch()` で直接叩く（timeout=5s で素早くフォールバック）。
- **エコーチェンバー破壊のテンプレート戦略:** AC サジェストは「人気ある検索パターン」を返すが、エージェントがすでに見ているパターンと同じことが多い。`_VIEWPOINT_TEMPLATES`（criticism / alternatives / site:arxiv / 2025 OR 2026）を**常に**付加することで AC が使えない場合でも多様性を保証する。
- **AC の最初の結果はスキップ:** `phrases[0].lower() == topic.lower()` の場合（完全一致）はスキップ。DDG は常に入力語そのものを先頭に返す習性があり、これはノイズになる。
- **`Optional[str]` → `str | None`:** ruff UP045 で自動修正。Python 3.11+ プロジェクトでは `from __future__ import annotations` + `X | None` を使用すること。
- **Stuck Agent テストの設計:** `_fetch_autocomplete` を `AsyncMock` でパッチして AC 結果を制御し、テンプレートクエリの内容を検証する。実際のネットワークコールは不要。エコーチェンバー文脈は diet blog / tech blog の2種を用意してカバレッジを確保。

### [2026-05-28] [ACTIVE] aiosqlite — 正しい使用パターン
- **NG:** `db = await aiosqlite.connect(path)` の後で `async with db:` → スレッドが二重起動されて RuntimeError
- **OK:** `async with aiosqlite.connect(path) as db:` を使う、または `db = await aiosqlite.connect(path)` を取得後は `try/finally: await db.close()` で管理する
- **理由:** `aiosqlite.connect()` は接続を待機するコルーチンを返すが、返却されたオブジェクト自体も async context manager。`await` 済みオブジェクトに再度 `async with` すると内部スレッドが再起動しようとしてエラーになる。

### [2026-05-28] [ACTIVE] duckduckgo-search v8 — 追加の重要な制約（Phase 2 判明）
- **結果dictキーは `href`（`url` ではない）:** `DDGS.text()` の結果は `title`, `href`, `body` キーを持つ。SPEC.md の `SearchResult.url` にマッピングする際は `r.get("href", "")` を使うこと。
- **`published_date` は常に None:** html/lite/bing いずれのバックエンドも日付を返さない。`SearchResult.published_date` は `None` を期待することをエージェントのプロンプトで明示すること。
- **内部 HTTP クライアントは `primp` (Rust):** `curl_cffi` ではなく `primp` が使われており `impersonate="random"` がデフォルト。DDGS 自体がステルス対応済み。追加の curl_cffi ヘッダーは不要だが、`DDGS(headers={...})` で Accept-Language 等を上書きできる。
- **パッケージ名変更警告:** `duckduckgo_search` → `ddgs` に改名中。`RuntimeWarning` を `warnings.filterwarnings("ignore", category=RuntimeWarning)` で抑制すること。
- **Thread Safety:** `DDGS` インスタンスを共有してはならない。必ず呼び出しごとに新インスタンスを生成し、`asyncio.to_thread()` でスレッドに委譲すること。

### [2026-05-28] [ACTIVE] eval_judge — スコアリング改善（Phase 1 で適用）
- **コードブロック密度補正:** コードブロックは1行あたり文字数が短く density が不当に低くなる。`body_no_code`（コードブロック除去後）で prose 行長を計算し、コードブロックがある場合は density の下限を 2.0 に設定。
- **複数見出しレベル構造ボーナス:** heading_levels ≥ 2 なら +0.5 の structure ボーナスを付与。News/Wiki/TechDocs 等の多セクション文書を正しく評価できる。

### [2026-05-28] [HISTORICAL] curl_cffi v0.15 — 最新 impersonate ターゲット
- **Available:** `chrome146` が最新。`chrome131` も引き続き利用可能（CLAUDE.md 指定値）。
- **Rule:** `chrome131` はほぼ全サイトで動作実績があり安定している。新しいターゲットに変更する前に必ず動作確認すること。
- **Status note:** historical because code defaults are stable; revisit if Operations Rule 4 fires.

### [2026-05-28] [ACTIVE] trafilatura v2 — 3つの重要な制約
- **コード言語アノテーション消失:** `<code class="language-python">` の言語情報が常に削除される。**対処:** BeautifulSoup で抽出前に DOM 順で言語リストを収集し、抽出後の ` ``` ` フェンスに順番に注入する（`core/extractor.py` の `_extract_code_languages` / `_restore_code_languages`）。
- **コンテンツ重複（`<article>`/`<main>` タグバグ）:** `<article>` または `<main>` タグで包まれたコンテンツが2回出力される。**対処:** `utils/cleaner.py` の `deduplicate_blocks()` が段落ブロック単位で重複を除去する。
- **`with_metadata=True` が Markdown を破壊:** このフラグを使うとコードブロックがプレーンテキスト化される。**必須:** メタデータは `trafilatura.extract_metadata(html)` で別途取得し、フロントマターを手動組み立てすること。

### [2026-05-28] [ACTIVE] eval_judge.py — ノイズ検出はライン密度に依存する
- **Rule:** ノイズスコアはノイズ行数÷総行数の比率で計算する。短い記事（< 15行）でフッターが数行あるだけで比率が急上昇しスコアが過度に低くなる。
- **Solution:** eval_judge のテストフィクスチャは**最低30行以上**の現実的な長さを使うこと。短すぎるサンプルはスコアが不安定になる。

### [2026-05-28] [ACTIVE] duckduckgo-search v8 — DDGS is Synchronous
- **Rule:** `duckduckgo-search` v8.x の `DDGS.text()` は**同期メソッド**（asyncでない）。
- **Impact:** SPEC.md の「全I/OはAsync」要件と衝突する。
- **Solution:** `await asyncio.get_event_loop().run_in_executor(None, ddgs.text, ...)` でスレッドプールに委譲すること。`async def` 内で直接 `DDGS().text()` を呼ばないこと。
- **API Signature (v8.1.1):** `DDGS.text(keywords, region=None, safesearch='moderate', timelimit=None, backend='auto', max_results=None) -> list[dict[str, str]]`
- **Constructor:** `DDGS(headers=None, proxy=None, timeout=10, verify=True)` — カスタムヘッダーはここで渡す。

### [2026-05-28] [HISTORICAL] Project Initialization
- **Rule:** `duckduckgo-search` version 7.x changed `DDGS` import path. Always verify via `pip show`.
- **Pattern:** Tech blogs often have "Related Posts" sections that look like main content. `trafilatura` config `favor_precision=True` helps but requires manual DOM inspection for specific domains like Medium.
- **Status note:** v7 path lesson is superseded by v8 lessons above; kept for historical context only.
