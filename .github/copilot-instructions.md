# GitHub Copilot instructions

**This repository's full instructions live in [`CLAUDE.md`](../CLAUDE.md) — the
single source of truth. Read it in full and follow it.** Rules are intentionally
*not* duplicated here (they would drift). [`AGENTS.md`](../AGENTS.md) mirrors
this pointer for other agents (Codex, Cursor, Gemini, …).

When you open a PR, you MUST satisfy these (full detail in `CLAUDE.md` and
`docs/METHODOLOGY.md` §2):

- **Prime Directives:** structured JSON error `hint`s, never raw tracebacks;
  extract main content only (strip nav / footer / cookie / ad text).
- **Test first:** add the failing regression test before the fix.
- **Definition of Done — all 5 boxes:** measurable before/after · regression
  test · gates green · **all docs synced in the same commit** · a `[ACTIVE]`
  lesson in `docs/LESSONS.md`.
- **Documentation Sync (BLOCKING):** `CHANGELOG.md` + `docs/METHODOLOGY.md` +
  `docs/LESSONS.md` + `README` / `docs/ARCHITECTURE.md` as needed.
- **Run `python scripts/verify.py` and make it pass** (pytest + ruff +
  dogfood_regression + docs links — offline). Orient first with
  `python scripts/status.py`.

`Bxx` (e.g. B13) = a row in `docs/METHODOLOGY.md` §5; read that row for the spec,
then mark it `~~DONE~~ YYYY-MM-DD` (keep its `disc:` tag). Live-web tests are not
runnable in CI and are not required by `verify.py` — don't add network-dependent
tests; mock the boundary.
