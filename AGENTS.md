# AGENTS.md — instructions for AI coding agents

**Single source of truth: [`CLAUDE.md`](CLAUDE.md). Read it in full and follow
it as if it were addressed to you.**

This repository is maintained by AI agents under one shared rulebook. To avoid
two files drifting out of sync, the real instructions live **only** in
`CLAUDE.md` and are *not* duplicated here. Whatever agent you are — OpenAI
Codex, GitHub Copilot, Cursor, Gemini, Claude Code, … — treat `CLAUDE.md` as
your primary instruction file. This file (and `.github/copilot-instructions.md`)
are thin pointers to it.

## Do this on every change (summarised from `CLAUDE.md`)

1. **Orient:** run `python scripts/status.py` (tests / lint / backlog / MTTI —
   computed, never guessed).
2. **Prime Directives:** never return a raw traceback — return a structured JSON
   `hint`; extract main content only (no nav / footer / cookie / ad text).
3. **Test first:** write the failing regression test before the fix.
4. **Definition of Done — all 5 boxes** (`docs/METHODOLOGY.md` §2): measurable
   before/after · regression-tested · gates green · **docs synced** · a
   `[ACTIVE]` lesson appended to `docs/LESSONS.md`.
5. **Documentation Sync (BLOCKING, `CLAUDE.md` §4):** in the *same commit*,
   update `CHANGELOG.md`, `docs/METHODOLOGY.md`, `docs/LESSONS.md`, and
   `README` / `docs/ARCHITECTURE.md` / `docs/MAINTENANCE.md` as the change
   requires.
6. **Gate:** run `python scripts/verify.py` and make it pass (pytest + ruff +
   dogfood_regression + docs links — **fully offline, no network required**).

## "Bxx" backlog items

`Bxx` (e.g. B13) is a row in `docs/METHODOLOGY.md` §5 (Open Improvement
Backlog). To "solve B13": read that row for the problem and expected impact,
implement it, mark the row `~~DONE~~ YYYY-MM-DD` (keep its `disc:` tag for the
MTTI metric), and satisfy the Definition of Done above.

## Environment note

Live-web dogfooding (real DuckDuckGo search / `read_article` fetches) is **not**
available in CI or agent sandboxes — and that's fine: it is **not** part of
`scripts/verify.py`. Do not add tests that require live network; mock the
network boundary instead (see `tests/` for the patterns).
