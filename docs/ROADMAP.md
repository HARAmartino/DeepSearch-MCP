# 🗺️ Project Roadmap: DeepSearch-MCP
**Current Phase:** Day 2 Operations (post-v1.0.0) — self-improvement via PDCA + Dogfooding loops
**Last Updated:** 2026-05-29
**Maintainer:** AI Agent (Self-Updating)

---

## 🔄 The "Build-Eval-Learn" Protocol
全てのフェーズは、以下のサイクルを完了するまで「Done」とみなされません。

1.  **🔍 Fact-Check (Pre-Flight):** 使用するライブラリやAPIの最新仕様をWeb検索またはドキュメントで確認する（ハルシネーション防止）。
2.  **🔨 Build:** `CLAUDE.md` の規約に従い実装する。
3.  **🧪 Eval:** `evals/eval_judge.py` または実データを用いて品質をスコアリングする。
4.  **🧠 Learn:** 発見したパターンやバグ回避策を `CLAUDE.md` の `Lessons Learned` に追記する。
5.  **✅ Commit:** 変更をコミットし、このROADMAPのチェックボックスを更新する。

---

## 🟢 Phase 0: Foundation & The Judge
**Goal:** 開発環境の構築と、品質を自動判定する「審判（Judge）」の作成。

- [ ] **0.1 Environment Setup**
    - [ ] Initialize project with `uv` (Python 3.11+).
    - [ ] Install dependencies: `mcp`, `duckduckgo-search`, `trafilatura`, `curl_cffi`, `pydantic`, `pytest`.
    - [ ] Verify directory structure matches `CLAUDE.md`.
- [ ] **0.2 Create The Judge (`evals/eval_judge.py`)**
    - [ ] Implement logic to score Markdown output (0-10) based on:
        - **Noise Ratio:** Presence of nav/footer keywords.
        - **Structure:** Valid Markdown headers/lists.
        - **Density:** Text-to-HTML ratio estimation.
    - [ ] Create `tests/test_judge.py` with dummy HTML/Markdown pairs to verify scoring logic.
- [ ] **0.3 Baseline Measurement**
    - [ ] Run the original `duckduckgo-mcp-server` (if available) or a naive scraper against 3 test URLs.
    - [ ] Record the "Baseline Score" in `docs/BASELINE.md`.

> **🛑 Gate:** Phase 0 is complete only when `eval_judge.py` runs successfully and assigns low scores to noisy HTML and high scores to clean Markdown.

---

## 🔵 Phase 1: The "Clean Room" (Extraction Engine)
**Goal:** `read_article` ツールによるコンテキスト最適化。ノイズを極限まで除去する。

- [ ] **1.1 Fact-Check: Extraction Libraries**
    - [ ] Search web for "trafilatura vs readability-lxml 2025/2026 benchmark".
    - [ ] Confirm `trafilatura` arguments for Markdown output and metadata extraction.
- [ ] **1.2 Implement `read_article` Core**
    - [ ] Create `src/deepsearch_mcp/tools/extractor.py`.
    - [ ] Integrate `curl_cffi` for fetching (stealth mode).
    - [ ] Integrate `trafilatura` for parsing.
- [ ] **1.3 Adversarial Testing (The Gauntlet)**    - [ ] Test against 5 distinct site types:
        1.  **News:** (e.g., NHK, CNN) - Check for "Related News" noise.
        2.  **Blog:** (e.g., Medium, Hatena) - Check for author bio/sidebar noise.
        3.  **Tech Docs:** (e.g., ReadTheDocs, GitHub) - **Crucial:** Verify code block preservation.
        4.  **Wiki:** (e.g., Wikipedia) - Check for infobox handling.
        5.  **Recipe/SEO:** (e.g., AllRecipes) - Check for "life story" removal.
- [ ] **1.4 Refine & Fallback**
    - [ ] If `trafilatura` fails on Tech Docs, implement `readability-lxml` fallback logic.
    - [ ] Add regex cleaners for specific recurring artifacts (e.g., "Share on Twitter", "Cookie Settings").
- [ ] **1.5 Update Knowledge Base**
    - [ ] **Action:** Update `CLAUDE.md` -> `Lessons Learned` with domain-specific extraction patterns found.

> **🛑 Gate:** `eval_judge.py` average score > 8.5/10 on the test set.

---

## 🟠 Phase 2: The "Shield" (Search & Resilience)
**Goal:** `search_web` の堅牢化。ボット検出回避と構造化エラーハンドリング。

- [ ] **2.1 Fact-Check: DuckDuckGo API**
    - [ ] **CRITICAL:** Search web for "duckduckgo-search python library latest version changelog".
    - [ ] Verify `DDGS` import path and `text()` method signature.
- [ ] **2.2 Implement `search_web` with Cache**
    - [ ] Create `src/deepsearch_mcp/tools/search.py`.
    - [ ] Implement SQLite-based caching (TTL: 24h) to prevent rate limits.
    - [ ] Add random delays (jitter) between requests.
- [ ] **2.3 Chaos Engineering (Error Handling)**
    - [ ] Simulate `RatelimitException` and `403 Forbidden`.
    - [ ] Verify output is a **Structured JSON Hint** (not a traceback).
    - [ ] Example: `{"status": "error", "code": "RATE_LIMITED", "message": "DuckDuckGo rate limit reached.", "hint": "Wait 60s before retrying, or refine query to be more specific.", "retryable": true}`
- [ ] **2.4 Stealth Integration**
    - [ ] Ensure `curl_cffi` impersonation is active for search requests if HTML endpoint is used.
- [ ] **2.5 Update Knowledge Base**
    - [ ] **Action:** Update `CLAUDE.md` with effective `User-Agent` strings or proxy strategies if discovered.

> **🛑 Gate:** Server returns valid JSON hints on simulated 429/403 errors. Cache hit rate > 90% on repeated queries.

---

## 🟣 Phase 3: The "Navigator" (Agentic Autonomy)
**Goal:** LLMの調査能力を拡張する `suggest_queries` とメタデータ活用。

- [x] **3.1 Implement `suggest_queries`**
    - [x] DDG `/ac/` autocomplete API for real user patterns (curl_cffi, timeout=5s).
    - [x] `_VIEWPOINT_TEMPLATES` for criticism/alternatives/primary-source/temporal angles.
    - [x] Entity extraction from context snippets (proper noun regex + stop-word filter).
    - [x] Registered in `server.py`.
- [x] **3.2 Metadata Enrichment**
    - [x] `date_parser.py` rewritten with `extract_date_from_url` (4 regex patterns) and `extract_date_from_text` (3 patterns).
    - [x] `best_effort_date(raw, url, body)` chains all sources in priority order.
- [x] **3.3 Tool Description Optimization**
    - [x] All 3 tools (`read_article`, `search_web`, `suggest_queries`) updated with `## EXAMPLES (Few-Shot)` sections.
    - [x] Negative constraints added to all tools.
- [x] **3.4 Simulation: The "Stuck" Agent**
    - [x] `tests/test_suggest.py` — `TestStuckAgentSimulation` class with diet blog and tech blog echo-chamber scenarios.
    - [x] Verified: criticism/alternatives/primary-source/temporal angles all present in output.
    - [x] 109/109 tests pass across all phases.

> **🛑 Gate: ✅ PASSED** — `suggest_queries` returns 3–8 unique queries; Stuck Agent tests verify echo-chamber breaking.

---

## 🔴 Phase 4: Field Operations (Integration)
**Goal:** 実環境でのエンドツーエンドテストとドキュメント統合。

- [x] **4.1 E2E Research Simulation**
    - [x] `evals/simulate_research.py` — 4-step ReAct loop: search → extract → suggest → follow-up.
    - [x] `--demo` mode with realistic MCP-trends pre-set data (no network required).
    - [x] Live mode for real DuckDuckGo calls; error recovery demonstrated.
    - [x] Reports: token budget, source diversity (5 unique hosts), step timings, error recovery.
- [x] **4.2 Edge Case Finalization — Non-HTML Detection**
    - [x] `UNSUPPORTED_FORMAT` error code added to `errors.py`.
    - [x] URL extension guard: 30+ extensions (PDF, ZIP, JPG, MP4, DOCX, etc.) rejected pre-fetch.
    - [x] `Content-Type` guard: application/pdf, image/*, video/*, audio/*, application/vnd.* rejected post-fetch.
    - [x] 30 new tests in `test_extractor.py`: `TestIsNonHtmlUrl`, `TestIsNonHtmlContentType`, `TestReadArticleUnsupportedFormat`.
- [x] **4.3 Final Documentation**
    - [x] `README.md` — Complete with: Concept, Quick Start, MCP Client Config (Claude Desktop/Code/Cursor), Tools Overview, Agent Best Practices, Troubleshooting, Dev guide.
    - [x] MCP config format verified against 2026 official documentation.

> **🛑 Gate: ✅ PASSED** — 139/139 tests pass; simulation runs end-to-end with error recovery; README covers all client types.

---

## 🟢 Phase 5: Adversarial Dogfooding (Reflection Loop)
**Goal:** エージェント視点で実際に使い、Friction を撲滅する。Self-critique → patch → verify サイクル。

- [x] **5.1 Persona A — Critic Pass**
    - [x] Deep Research タスク (AI agent memory, RAG vs long-term memory) を実ツール呼び出しで実行。
    - [x] 10件の Friction を `[FRICTION-X#]` タグ付きで識別。
    - [x] 重大度分類: 4 Critical, 2 High, 4 Medium/Low。
- [x] **5.2 Persona B — Architect Patch**
    - [x] **C1: Smart Quoting** — `_render_topic()` で ≤2語のみ quote-wrap、長トピックは bare。
    - [x] **B1: Error Sanitization** — `sanitize_error_text()` で URL/制御文字を除去、200文字に切詰め。
    - [x] **B2: Context-Aware Hints** — `structured_error()` に `hint_override` / `retryable_override`、`search_web` 専用の query-context hints。
    - [x] **B3: Transient Detection** — `is_transient_conn_error()` で DNS/timeout/reset を検出、`retryable=True` に flip。
    - [x] **D1: H1 Dedup** — `_strip_redundant_h1()` で frontmatter title と一致する H1 を本文から削除。eval_judge を frontmatter title 認識に対応。
    - [x] **C3: Temporal Top-3** — `_VIEWPOINT_TEMPLATES` reorder、`{topic} 2025 OR 2026` を position 0 に。
    - [x] **A1/E1: Docstring 刷新** — USE WHEN に定量的トリガー (e.g. "last 2+ rounds"), `include_images` 説明追加。
- [x] **5.3 Regression Tests (+27 新規)**
    - [x] `TestSmartQuoting` (7): long topic non-quoted, short topic quoted, temporal in top-3。
    - [x] `TestErrorSanitization` (5): URL strip, length cap, whitespace collapse。
    - [x] `TestTransientErrorDetection` (5): DNS / timeout / reset / non-transient distinction。
    - [x] `TestSearchWebContextAwareHints` (5): query-context hints, REDACTED_URL, retryable=True。
    - [x] `TestH1Deduplication` (5): exact strip, leading-only strip, case-insensitive, helper unit。
- [x] **5.4 Verification (Persona A Re-Run)**
    - [x] C1: 7語トピックで quote-wrapped=0 件、全クエリに topic キーワード保持。
    - [x] B1: エラーメッセージ 177 chars (≤200), `[REDACTED_URL]` 置換、生 URL 漏洩なし。
    - [x] B2: hint が "Check query spelling or try broader terms" (query-context)。
    - [x] B3: DNS-origin CONN_ERROR が `retryable: true`。
    - [x] D1: 出力サイズ 1084 → 545 chars (50%減)、H1 重複なし。
- [x] **5.5 CLAUDE.md Lessons Learned**
    - [x] Lesson 1: Tools must compose.
    - [x] Lesson 2: Error hints must match input type.
    - [x] Lesson 3: Sanitize before reaching LLM.
    - [x] Lesson 4: Transient failures → retryable=true.

> **🛑 Gate: ✅ PASSED** — 166/166 tests pass; 0 ruff errors; Persona A re-run shows all 5 Critical/High frictions resolved; CLAUDE.md updated with 4 permanent rules.

---

## 🟦 Phase 6: Day 2 Operations (Self-Healing PDCA)
**Goal:** リリース後の運用フェーズにおける自己改善ループ。観測 → 分析 → 自動パッチ。

- [x] **6.1 Plan & Do — Telemetry 基盤**
    - [x] `core/telemetry.py` — async SQLite recording、`@track(tool_name, primary_input)` デコレータ。
    - [x] スキーマ: `timestamp, tool_name, input_summary, status, tokens_approx, latency_ms, domain` + 3 インデックス。
    - [x] 制約クリア: 書き込みは `asyncio.create_task` でバックグラウンド実行、`_pending_tasks` セットでGC防止。
    - [x] PII対策: 80字超の入力は `sha1[:8]` ダイジェスト付きで切詰め。
    - [x] 環境変数: `DEEPSEARCH_TELEMETRY=0` で完全無効化 (tests/conftest.py 既定)。
    - [x] 3 ツール全てに統合 (`search_web`, `read_article`, `suggest_queries`)。
- [x] **6.2 Check — 自動分析スクリプト**
    - [x] `evals/analyze_telemetry.py` — 3レポート (Failure Hotspots / Token Inefficiency / Error Patterns) + 自動 SUGGESTED ACTIONS。
    - [x] CLI: `--json` 機械可読モード、`--db PATH` 任意DB指定。
    - [x] 閾値: 失敗率 ≥15%、平均 ≥3000 tokens、エラー比率 ≥30/50% で `⚠️` 自動フラグ。
    - [x] `evals/generate_dummy_telemetry.py` — シード可能な合成データ生成器 (560行: 意図的に substack 38% / medium 27% / bigcorp 3956avg を仕込む)。
- [x] **6.3 Act — 自己修復プロトコル**
    - [x] アナライザ実行 → `substack.com (38%)`, `medium.com (27%)` が ⚠️ 検出。
    - [x] `core/extractor.py` に `_DOMAIN_PREPROCESSORS` インフラ追加。
    - [x] `_substack_preprocess()` 実装 — subscription widget / dialog / footer を decompose。
    - [x] `_medium_preprocess()` 実装 — member-only wall / metered content を decompose。
    - [x] サブドメインマッチング (`author.substack.com` も routes)。
    - [x] A/B 検証: substack adapter で eval_judge スコア 8.0 → 8.5 (+0.5)、tokens -8。
- [x] **6.4 Tests & Lint**
    - [x] `test_telemetry.py` — 28 tests (decorator records, disabled passthrough, failure safety, schema sanity)。
    - [x] `TestSubstackAdapter` + `TestMediumAdapter` — 10 tests (widget stripped, subdomain routes, passthrough)。
    - [x] 204/204 passing; 0 ruff errors。
- [x] **6.5 CLAUDE.md Operations Rules**
    - [x] Rule 1: ドメイン失敗率 ≥15% → adapter 追加。
    - [x] Rule 2: トークン平均 ≥3000 → ノイズパターン調査。
    - [x] Rule 3: RATE_LIMITED ≥30% → cache TTL/jitter 調整。
    - [x] Rule 4: BLOCKED_403 ≥50% → impersonate 更新。
    - [x] Rule 5: 同一 input_summary 多数 → ループ検出 (エージェント側問題)。

> **🛑 Gate: ✅ PASSED** — Telemetry recording works (28 tests); analyzer surfaces actionable hotspots; Act-phase adapter delivers measurable quality improvement (+0.5 score); 5 Operations Rules permanent in CLAUDE.md.

---

## 📝 Change Log (Auto-Updated)
| Date | Phase | Change Description | Agent |
| :--- | :--- | :--- | :--- |
| 2026-05-28 | - | Initial Roadmap Creation | Human |
| | | | |