#!/usr/bin/env python3
"""
docs_map.py — a *generated* documentation map + integrity checker.

**Why this exists.** The project has 11 markdown docs; one change cycle can
touch 5 of them. Two agent frictions follow: (a) *routing* — "which doc do I
read for X?"; (b) *sync-risk* — touch one doc, leave a dangling cross-reference
or an orphaned file.

Consolidating the docs was the obvious fix and was rejected: it is high-risk
(rewrites lose nuance) and a single committed map file would itself drift.
Instead this **computes** the map on demand (same principle as `status.py`:
compute ground truth, never store it) and **mechanically checks** the two
things that actually break:

  - **Dead links** — every relative markdown link must resolve. This is a
    real bug and fails `--check` (so `verify.py` gates on it).
  - **Orphans** — docs no other doc links to. An agent may never discover
    them. Reported as a warning, not a failure (some docs are legitimately
    standalone entry points).

It does NOT try to detect *content* staleness (e.g. ROADMAP saying "Phase 0").
But printing each doc's first descriptor line next to its role makes obvious
drift visible to the reader.

Run:
    python scripts/docs_map.py            # print the map + integrity summary
    python scripts/docs_map.py --check    # exit non-zero if any dead links
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Root-level docs worth mapping (skip incidental .md like this script's dir).
_ROOT_DOCS = ["CLAUDE.md", "README.md", "CHANGELOG.md"]

# Docs that are *intentionally* standalone (one-time snapshots / archives).
# Listing them here keeps the orphan check meaningful — an orphan warning
# should mean "accidentally undiscoverable", not "known archive". Suppressing
# known-OK noise is signal hygiene, not gaming the metric.
_STANDALONE_OK = {"BASELINE.md"}

# Filename → one-word role, so the map doubles as a routing table.
_ROLE = {
    "CLAUDE.md": "rules (always-loaded)",
    "README.md": "users / setup",
    "CHANGELOG.md": "history",
    "CONCEPT.md": "why it exists",
    "SPEC.md": "what (tool contracts)",
    "ARCHITECTURE.md": "how (data flow)",
    "METHODOLOGY.md": "process (improve)",
    "MAINTENANCE.md": "ops (runbook)",
    "LESSONS.md": "memory (bugs/quirks)",
    "ROADMAP.md": "plan (phases)",
    "BASELINE.md": "baseline metrics",
}

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_H1_RE = re.compile(r"^#\s+(.*)")


def discover_docs() -> list[Path]:
    docs = sorted((ROOT / "docs").glob("*.md"))
    roots = [ROOT / name for name in _ROOT_DOCS if (ROOT / name).exists()]
    return roots + docs


def purpose(path: Path) -> str:
    """First descriptive line after the H1 (bold tagline, blockquote, or prose)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "(unreadable)"
    seen_h1 = False
    for line in lines:
        s = line.strip()
        if not seen_h1:
            if _H1_RE.match(s):
                seen_h1 = True
            continue
        if not s or s == "---":
            continue
        # First meaningful line after the H1.
        s = re.sub(r"^>\s*", "", s)            # blockquote marker
        s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)  # bold
        s = re.sub(r"[*_`]", "", s)            # stray emphasis
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # link → text
        return (s[:88] + "…") if len(s) > 88 else s
    return "(no description)"


def relative_links(path: Path) -> list[str]:
    """Relative (non-URL) link targets found in a doc, anchors stripped."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[str] = []
    for target in _LINK_RE.findall(text):
        t = target.strip()
        if t.startswith(("http://", "https://", "mailto:", "#")):
            continue
        t = t.split("#", 1)[0].strip()  # drop anchor
        if t:
            out.append(t)
    return out


def dead_links() -> list[tuple[Path, str]]:
    """(source_doc, target) for every relative link that does not resolve."""
    dead: list[tuple[Path, str]] = []
    for doc in discover_docs():
        for target in relative_links(doc):
            resolved = (doc.parent / target).resolve()
            if not resolved.exists():
                dead.append((doc, target))
    return dead


def orphans() -> list[Path]:
    """docs/*.md never linked from any scanned doc (discovery risk)."""
    linked: set[Path] = set()
    for doc in discover_docs():
        for target in relative_links(doc):
            linked.add((doc.parent / target).resolve())
    out: list[Path] = []
    for doc in sorted((ROOT / "docs").glob("*.md")):
        if doc.name in _STANDALONE_OK:
            continue
        if doc.resolve() not in linked:
            out.append(doc)
    return out


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def print_map() -> None:
    print("=" * 74)
    print("  DeepSearch-MCP — DOCS MAP (generated; read, don't cache)")
    print("=" * 74)
    for doc in discover_docs():
        role = _ROLE.get(doc.name, "—")
        print(f"  {_rel(doc):<24} [{role}]")
        print(f"      {purpose(doc)}")
    print("-" * 74)


def print_integrity() -> int:
    dead = dead_links()
    orph = orphans()

    if dead:
        print(f"  ❌ DEAD LINKS ({len(dead)}):")
        for src, target in dead:
            print(f"     {_rel(src)} → {target}")
    else:
        print("  ✅ Links: all relative markdown links resolve.")

    if orph:
        print(f"  ⚠️  ORPHANS ({len(orph)}) — not linked from any doc "
              f"(an agent may never find them):")
        for o in orph:
            print(f"     {_rel(o)}")
    else:
        print("  ✅ Orphans: every doc is referenced somewhere.")

    # Final line is a concise one-liner so callers that capture the last line
    # of output (e.g. scripts/verify.py) show something meaningful.
    print(
        f"  docs integrity: {len(dead)} dead link(s), {len(orph)} orphan(s)"
    )
    return 1 if dead else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    check_only = "--check" in argv

    if not check_only:
        print_map()
    return print_integrity()


if __name__ == "__main__":
    sys.exit(main())
