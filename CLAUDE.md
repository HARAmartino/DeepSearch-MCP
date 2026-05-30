# Project: DeepSearch-MCP
**Mission:** Build the ultimate web-search MCP server optimized for LLM Agents (Deep Research).
**Status:** Release-ready (v1.0.0) — Self-Evolving via PDCA + Dogfooding loops.

> This file is loaded into every agent session. **Keep it short.**
> Historical knowledge, audit logs, and Operations playbooks live in dedicated
> `docs/*.md` files referenced from §6 below. If you find yourself adding more
> than a paragraph to a non-pointer section, ask whether it belongs in a
> dedicated doc instead. Prime Directive 1 applies to this file too.

---

## 🧭 Orientation (run first)
Your memory of this repo may be stale after a context compaction. Don't guess —
get live ground truth in one call:

- `python scripts/status.py` — tests / lint / golden count / last audit / next backlog (computed, never stored).
- `python scripts/verify.py` — the single merge gate (pytest + ruff + dogfood_regression + docs links, one exit code).
- `python scripts/docs_map.py` — map of all docs (role + purpose) + dead-link / orphan check.

(`uv` may not be on the tool-shell PATH; `.venv/bin/python scripts/…` always works.)

---

## 💎 Prime Directives (Absolute Rules)
あなたは以下の3原則に違反するコードを書いてはなりません。

1. **Context is Gold (コンテキスト絶対主義)**
   - **禁止:** ナビゲーション、フッター、Cookieバナー、広告、"Skip to content"リンク、SNSシェアボタンのテキストを出力に含めること。
   - **必須:** `trafilatura` 等を用いて本文のみを抽出し、Markdown化すること。
2. **Robustness by Default (堅牢性の標準化)**
   - Web は敵対的環境。403/429/Timeout は「例外」ではなく「日常」。
   - **必須:** Python の Traceback をそのまま返さず、LLM が次のアクション（リトライ、クエリ変更）を判断できる**構造化されたヒント (JSON)** を返す。
3. **Fact-Check First (ハルシネーション対策)**
   - `duckduckgo-search` 等のライブラリは API 仕様が頻繁に変わる。
   - **必須:** 実装前に `pip show <pkg>` または Web 検索で**最新の API リファレンスを確認**してからコードを書く。記憶にある古い API を使わない。

---

## 🛠 Tech Stack
- **Language:** Python 3.11+ (`X | None` syntax + `asyncio.to_thread` required)
- **Framework:** `mcp` (FastMCP) — Pydantic models for all I/O
- **Search:** `duckduckgo-search` v8+ (sync API → wrap in `asyncio.to_thread`)
- **Extraction:** `trafilatura` (primary) + `readability-lxml` (fallback)
- **Networking:** `curl_cffi` with `impersonate="chrome131"`
- **Validation:** `pydantic` v2 (strict)
- **Testing:** `pytest`, `pytest-asyncio`, `respx`

---

## 📂 Directory Structure
```text
DeepSearch-MCP/
├── CLAUDE.md                 # 🧠 This file — always loaded
├── README.md / CHANGELOG.md  # User-facing
├── docs/
│   ├── CONCEPT.md            # Why this project exists
│   ├── SPEC.md               # Technical spec
│   ├── ARCHITECTURE.md       # Mermaid system map
│   ├── MAINTENANCE.md        # SRE runbook + SQL recipes
│   ├── METHODOLOGY.md        # 🆕 Self-Improvement process (read when improving)
│   ├── LESSONS.md            # 🆕 Lessons Learned archive (read when debugging)
│   └── ROADMAP.md / BASELINE.md
├── src/deepsearch_mcp/
│   ├── server.py             # FastMCP entrypoint
│   ├── tools/                # search.py · extractor.py · suggest.py
│   ├── core/                 # http · models · errors · cache · extractor · telemetry
│   └── utils/                # cleaner · date_parser
├── tests/                    # 217 tests, all phases
└── evals/                    # eval_judge · simulate_research · analyze_telemetry
                              # · generate_dummy_telemetry · dogfood_research
                              # · dogfood_regression + dogfood_baseline/
```

---

## 💻 Implementation Standards

### 1. MCP Tool Definition (The "Prompt" Pattern)
Tool の docstring は LLM への**プロンプト**。以下を必ず含める:
- `## USE WHEN` — **量的なトリガー** (e.g. "last 2+ rounds returned same sources")
- `## DO NOT USE WHEN` — **代替ツール名を明記** ("→ call X directly")
- `## PARAMETERS` — 各引数の意味
- `## RETURNS` — スキーマと典型値
- `## EXAMPLES (Few-Shot)` — Good / Bad の対比

参考: `src/deepsearch_mcp/tools/extractor.py::read_article` の docstring。

### 2. Structured Error Handling
LLM がリカバリーできるよう `hint` を含める。生 Traceback を返してはならない。
```python
# GOOD
return err.structured_error(
    err.BLOCKED_403,
    "HTTP 403 for {url}",
    hint_override="…",          # call-site specific
    retryable_override=False,
)
```
詳細仕様: `src/deepsearch_mcp/core/errors.py` の `structured_error()`。

### 3. Stealth & Networking
- **Always:** fetch via `core/http.py` `fetch()` — it impersonates `chrome131`
  and **rotates to `safari17_0` on a 401/403 block** (some anti-bot setups block
  Chrome's TLS fingerprint; see B17). Don't hand-roll `AsyncSession`.
- **Always:** realistic `User-Agent`, `Accept-Language` headers.
- **Random delay:** `await asyncio.sleep(random.uniform(0.5, 1.5))` between live requests.

### 4. Documentation Sync (BLOCKING RULE)
コードのアーキテクチャ / 運用特性に影響する変更を行ったら、以下のドキュメントを**同じコミット内で**同期させる。コードと記述が乖離した瞬間、人間とエージェントの双方が誤った前提で作業し始める。

| トリガーとなる変更 | 同期必須ファイル |
|---|---|
| 新ツール / コア層モジュール追加 | `docs/ARCHITECTURE.md` の Mermaid 図 + `README.md` の Project Structure |
| 新しい Operations Rule | `docs/METHODOLOGY.md` §4 + `docs/MAINTENANCE.md` "Responding to alerts" |
| ユーザー可視の I/O / エラーコード / 環境変数 | `CHANGELOG.md` の `## [Unreleased]` |
| 新しい依存 / Python バージョン要件 | `pyproject.toml` + `docs/MAINTENANCE.md` "Updating dependencies" |
| 新しい教訓 / Operations Rule | `docs/LESSONS.md` または `docs/METHODOLOGY.md` |

**マージ前チェックリスト:** 該当する全ファイルに反映済みか? 1件でも未反映ならマージ禁止。

---

## 🔄 The "Build-Eval-Learn" Workflow

タスク完了時のループ:

1. **Plan:** `docs/ROADMAP.md` または `docs/METHODOLOGY.md` §1 (Trigger Hierarchy) で次の対象を選ぶ。
2. **Build:** コードを実装。**先にテスト**を書く。
3. **Eval:**
   - `pytest tests/ -q` + `ruff check src/ tests/ evals/` を green に。
   - 抽出を変えた場合: `python evals/dogfood_regression.py` で golden 検証。
   - 品質スコアを動かした場合: `evals/eval_judge.py` の Gauntlet 平均 ≥ 8.5 を維持。
4. **Learn:**
   - 一般化できる教訓を `docs/LESSONS.md` に追記 (`[ACTIVE]` タグ + 日付)。
   - 改善作業なら `docs/METHODOLOGY.md` §2 の Definition of Done 5 項目を満たす。

---

## 🚦 Quick-Reference: What to read when

| 状況 | 参照すべきファイル |
|------|------------------|
| MCP ツール仕様・スキーマを変える | [docs/SPEC.md](docs/SPEC.md) |
| データフローや依存関係を把握したい | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 本番アラートに対応する / 依存を更新する | [docs/MAINTENANCE.md](docs/MAINTENANCE.md) |
| 「次に何を改善するか」を自律的に決めたい | [docs/METHODOLOGY.md](docs/METHODOLOGY.md) §1 |
| 既知のライブラリ罠 / 過去のバグ原因を調べたい | [docs/LESSONS.md](docs/LESSONS.md) |
| フェーズ計画・進捗を見たい | [docs/ROADMAP.md](docs/ROADMAP.md) |
| ユーザー向けセットアップ手順 | [README.md](README.md) |
| バージョン間の差分 | [CHANGELOG.md](CHANGELOG.md) |
| ドキュメント全体の地図・整合性を見たい | `python scripts/docs_map.py` |

---

## 🧠 Anti-Patterns (must avoid)

過去6セッションで踏んだ罠。改善サイクル開始前に再読すること。詳細は `docs/METHODOLOGY.md` §3。

1. ❌ **複数改善の同時着手** — どのパッチが効いたか不明になる。1サイクル1テーマ。
2. ❌ **テスト無しの "明らかに正しい" 修正** — 6か月後の自分はその "明らか" を覚えていない。
3. ❌ **回帰テストより先にコードを書く** — Dogfooding cycle で確認済み: 先にテストを書く方が確実。
4. ❌ **集計指標だけで品質を測る** — `eval_judge` / telemetry は frequency。semantic noise は dogfooding でしか見えない。
5. ❌ **Lessons Learned の append-only** — stale 知識は新人エージェントを誤誘導する。四半期監査必須。

---

## 🗂 Lessons Learned

全エントリは [docs/LESSONS.md](docs/LESSONS.md) を参照。タグ規約:
- `[ACTIVE]` — コードがこの知識に依存している (削除すると bug が再発する可能性)。
- `[HISTORICAL]` — 当時は真だったが現在は load-bearing でない (参考情報)。
- `[STALE]` — もはや事実でない (次回監査で削除)。

新しい教訓は `docs/LESSONS.md` の末尾に**新しい日付エントリ**として追記し、必ずタグを付ける。
過去エントリの編集は四半期監査時のみ。
