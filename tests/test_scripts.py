"""
Tests for the agent-facing DX scripts (scripts/status.py, scripts/verify.py).

These exist because the project is a tool *for* LLMs, maintained *by* LLMs:
the maintaining agent's biggest tax is re-orientation after context compaction
(status.py) and forgetting one of the three merge gates (verify.py). We test
the cheap, deterministic pieces — not the heavy subprocess wrappers
(`test_count`, `ruff_clean`, the real gates), which would spawn pytest-in-pytest.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load(modname: str):
    """Load scripts/<modname>.py as a module (scripts/ is not a package)."""
    path = ROOT / "scripts" / f"{modname}.py"
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


status = _load("status")
verify = _load("verify")
docs_map = _load("docs_map")
propose = _load("propose_noise_regex")
collect = _load("collect_telemetry")  # import only — collect() hits the network
research = _load("research")  # import only — run() hits the network
live_check = _load("live_check")      # import only — main() hits the network


# ---------------------------------------------------------------------------
# verify.py — gate runner logic (without running the real suite)
# ---------------------------------------------------------------------------

class TestVerifyRunGate:
    def test_passing_command_reports_ok(self):
        ok, secs, _summary = verify.run_gate("noop", [sys.executable, "-c", "pass"])
        assert ok is True
        assert secs >= 0

    def test_failing_command_reports_not_ok(self):
        ok, _secs, _summary = verify.run_gate(
            "fail", [sys.executable, "-c", "import sys; sys.exit(1)"]
        )
        assert ok is False

    def test_bad_command_does_not_raise(self):
        """A non-existent binary must be caught, not crash the runner."""
        ok, _secs, summary = verify.run_gate("missing", ["this-binary-does-not-exist-xyz"])
        assert ok is False
        assert "error" in summary.lower()

    def test_summary_is_last_output_line(self):
        ok, _secs, summary = verify.run_gate(
            "echo", [sys.executable, "-c", "print('first'); print('LAST LINE')"]
        )
        assert ok is True
        assert summary == "LAST LINE"

    def test_gates_list_is_complete(self):
        names = [g[0] for g in verify.GATES]
        assert names == ["pytest", "ruff", "dogfood_regression", "docs_links"]


# ---------------------------------------------------------------------------
# venv-bin resolution (shared shape in both scripts)
# ---------------------------------------------------------------------------

class TestVenvBin:
    def test_returns_venv_path_when_present(self):
        # The repo ships a .venv with python; the resolver should find it.
        resolved = verify._venv_bin("python")
        assert resolved.endswith("python")

    def test_falls_back_to_bare_name(self):
        resolved = verify._venv_bin("definitely-not-a-real-binary-zzz")
        assert resolved == "definitely-not-a-real-binary-zzz"


# ---------------------------------------------------------------------------
# status.py — cheap, deterministic readers
# ---------------------------------------------------------------------------

class TestStatusReaders:
    def test_dogfood_baselines_counts_goldens(self):
        out = status.dogfood_baselines()
        # We currently ship 4 (techcrunch, langchain_blog, devto, zdnet).
        assert "fixture" in out
        n = int(out.split()[0])
        assert n >= 4

    def test_last_audit_parses_a_date(self):
        out = status.last_audit()
        # Format YYYY-MM-DD, or graceful fallback.
        assert out == "not recorded" or out.count("-") == 2

    def test_lesson_tags_reports_counts(self):
        out = status.lesson_tags()
        assert "active" in out and "stale" in out

    def test_next_backlog_excludes_done_and_struck(self):
        items = status.next_backlog()
        assert isinstance(items, list)
        assert len(items) <= 3
        joined = " ".join(items)
        # B5 is marked DONE/struck in METHODOLOGY §5 — must never surface.
        assert "B5:" not in joined

    def test_next_backlog_surfaces_open_items(self):
        items = status.next_backlog()
        # At least one open backlog item should parse (B1/B2/B3…).
        assert items, "expected at least one open backlog row to parse"
        assert items[0].startswith("B")


# ---------------------------------------------------------------------------
# Smoke: both scripts are syntactically importable and expose main()
# ---------------------------------------------------------------------------

class TestScriptSmoke:
    def test_status_has_main(self):
        assert callable(status.main)

    def test_verify_has_main(self):
        assert callable(verify.main)

    def test_verify_includes_docs_links_gate(self):
        names = [g[0] for g in verify.GATES]
        assert "docs_links" in names


# ---------------------------------------------------------------------------
# docs_map.py — purpose extraction, link parsing, integrity
# ---------------------------------------------------------------------------

class TestDocsMapParsing:
    def test_purpose_takes_first_line_after_h1(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("# Title Here\n\n**The real purpose line.**\n\nbody\n")
        assert docs_map.purpose(f) == "The real purpose line."

    def test_purpose_strips_blockquote_and_links(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("# T\n\n> See [ARCH](ARCHITECTURE.md) for details.\n")
        assert docs_map.purpose(f) == "See ARCH for details."

    def test_purpose_no_description(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("# Only A Heading\n")
        assert docs_map.purpose(f) == "(no description)"

    def test_relative_links_finds_md_and_strips_anchor(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("[a](FOO.md) [b](bar/BAZ.md#sec) [c](https://x.com) [d](#local)\n")
        links = docs_map.relative_links(f)
        assert "FOO.md" in links
        assert "bar/BAZ.md" in links          # anchor stripped
        assert "https://x.com" not in links   # URL ignored
        assert all(not x.startswith("#") for x in links)  # pure anchor ignored


class TestDocsMapIntegrity:
    """Integration: the live repo must stay link-clean and orphan-free."""

    def test_no_dead_links_in_repo(self):
        dead = docs_map.dead_links()
        assert dead == [], f"dead links: {[(str(s), t) for s, t in dead]}"

    def test_no_unexpected_orphans(self):
        orph = [p.name for p in docs_map.orphans()]
        assert orph == [], f"unexpected orphan docs: {orph}"

    def test_baseline_is_allowlisted_not_orphan(self):
        # BASELINE.md is intentionally standalone; it must not be reported.
        assert "BASELINE.md" in docs_map._STANDALONE_OK
        assert "BASELINE.md" not in [p.name for p in docs_map.orphans()]

    def test_check_mode_returns_zero_when_clean(self):
        assert docs_map.main(["--check"]) == 0


# ---------------------------------------------------------------------------
# propose_noise_regex.py — candidate generation + blast-radius safety
# ---------------------------------------------------------------------------

class TestCandidateRegex:
    def test_generalizes_pure_digits(self):
        pat = propose.candidate_regex("View all 23")
        assert r"\d+" in pat
        assert "23" not in pat  # the specific count must NOT be hardcoded
        # and it should actually match other counts
        import re
        assert re.search(pat, "view all 47", re.IGNORECASE)

    def test_generalizes_numberish_with_suffix(self):
        pat = propose.candidate_regex("1.2K shares")
        import re
        assert re.search(pat, "3.4M shares", re.IGNORECASE)
        assert re.search(pat, "1.2K shares", re.IGNORECASE)

    def test_no_trailing_b_after_punctuation(self):
        # The 2026-05-29 trap: a trailing \b after ':' never matches.
        pat = propose.candidate_regex("Tags:")
        assert not pat.endswith(r"\b")

    def test_leading_and_trailing_b_on_word_phrase(self):
        pat = propose.candidate_regex("affiliate links")
        assert pat.startswith(r"\b")
        assert pat.endswith(r"\b")

    def test_whitespace_becomes_flexible(self):
        pat = propose.candidate_regex("affiliate links")
        assert r"\s+" in pat


class TestBlastRadius:
    def test_overbroad_pattern_flags_prose(self):
        """A pattern matching common words MUST report prose hits."""
        prose_hits, _noise_hits = propose.blast_radius(r"\bthe\b")
        assert len(prose_hits) > 0, "expected an over-broad pattern to hit prose"

    def test_specific_noise_pattern_is_clean(self):
        """A precise noise pattern must NOT hit any already-clean prose."""
        prose_hits, _noise = propose.blast_radius(r"\bView\s+all\s+\d+\b")
        assert prose_hits == []


class TestProposeForLine:
    def test_safe_noise_line_returns_zero(self):
        assert propose.propose_for_line("View all 23 comments") == 0

    def test_unflagged_line_returns_one(self):
        # Real prose the auditor does not flag → nothing to generalize.
        rc = propose.propose_for_line(
            "The event loop schedules coroutines and runs their callbacks."
        )
        assert rc == 1

    def test_main_with_arg(self):
        assert propose.main(["1.2K", "shares"]) == 0


# ---------------------------------------------------------------------------
# collect_telemetry.py — smoke only (collect() makes real network calls)
# ---------------------------------------------------------------------------

class TestCollectTelemetrySmoke:
    def test_battery_is_non_empty(self):
        assert collect.READ_URLS and collect.SEARCH_QUERIES

    def test_battery_spans_outcome_space(self):
        urls = " ".join(collect.READ_URLS)
        assert ".pdf" in urls            # → UNSUPPORTED_FORMAT
        assert "status/403" in urls      # → BLOCKED_403
        assert "invalid" in urls or "nonexistent" in urls  # → CONN_ERROR

    def test_outcome_classifier(self):
        import json as _json
        assert collect._outcome(_json.dumps([{"x": 1}])).startswith("OK:")
        err = _json.dumps({"status": "error", "code": "BLOCKED_403"})
        assert collect._outcome(err) == "ERROR:BLOCKED_403"
        assert collect._outcome("---\ntitle: x\n---\n\nbody").startswith("OK:body")


# ---------------------------------------------------------------------------
# research.py — the triage scaffold (pure; run() hits the network, not tested)
# ---------------------------------------------------------------------------

class TestResearchTriage:
    def _r(self, url, tier="unknown", dup=False):
        return {"url": url, "title": url, "source_tier": tier, "near_duplicate": dup}

    def test_authoritative_sorted_first(self):
        pool = [self._r("https://blog.example/a"),
                self._r("https://reuters.com/b", tier="authoritative")]
        picks = research.triage(pool, 5)
        assert picks[0]["url"] == "https://reuters.com/b"

    def test_near_duplicates_skipped(self):
        pool = [self._r("https://a.example/1"),
                self._r("https://b.example/2", dup=True)]
        picks = research.triage(pool, 5)
        assert [p["url"] for p in picks] == ["https://a.example/1"]

    def test_one_per_host(self):
        pool = [self._r("https://a.example/1"), self._r("https://a.example/2"),
                self._r("https://b.example/3")]
        picks = research.triage(pool, 5)
        hosts = {p["url"].split("/")[2] for p in picks}
        assert hosts == {"a.example", "b.example"}

    def test_capped_at_read_n(self):
        pool = [self._r(f"https://h{i}.example/x") for i in range(10)]
        assert len(research.triage(pool, 3)) == 3

    def test_has_main_and_run(self):
        assert callable(research.main) and callable(research.run)


class TestBacklogMTTI:
    """B2: MTTI is derived from the backlog's disc:/DONE dates. Deterministic
    tests inject the table text + `today` so they don't drift as §5 grows."""

    SAMPLE = (
        "| # | Improvement | Impact | Blocked on |\n"
        "|---|---|---|---|\n"
        # closed reactive: 3-day lead time
        "| ~~**B90**~~ | ~~bug~~ | — | **✅ DONE 2026-05-04** — fixed. disc:2026-05-01 |\n"
        # closed reactive: same-session (0d)
        "| ~~**B91**~~ | ~~bug~~ | — | **✅ DONE 2026-05-10** — fixed. disc:2026-05-10 |\n"
        # open reactive: still flagged
        "| **B92** | open bug | impact | — (run) disc:2026-05-02 |\n"
        # proactive: NO disc: → must be excluded entirely
        "| **B93** | planned enhancement | impact | Next migration |\n"
    )

    def test_parse_skips_proactive_rows(self):
        recs = status.parse_backlog_dates(self.SAMPLE)
        ids = {r["id"] for r in recs}
        assert ids == {"B90", "B91", "B92"}  # B93 (no disc:) excluded

    def test_parse_captures_disc_and_done(self):
        recs = {r["id"]: r for r in status.parse_backlog_dates(self.SAMPLE)}
        assert recs["B90"]["disc"] == "2026-05-01"
        assert recs["B90"]["done"] == "2026-05-04"
        assert recs["B92"]["done"] is None  # open → no DONE date

    def test_mtti_closed_lead_time(self):
        m = status.mtti(self.SAMPLE, today="2026-05-12")
        # closed lead times: B90=3d, B91=0d → mean 1.5, median 1.5
        assert m["closed_n"] == 2
        assert m["mtti_mean"] == 1.5
        assert m["mtti_median"] == 1.5

    def test_mtti_oldest_open_age(self):
        m = status.mtti(self.SAMPLE, today="2026-05-12")
        assert m["open_n"] == 1
        age, bid = m["oldest_open"]
        assert bid == "B92" and age == 10  # 2026-05-02 → 2026-05-12

    def test_mtti_no_open_rows(self):
        text = (
            "|---|---|---|---|\n"
            "| ~~**B90**~~ | x | — | **✅ DONE 2026-05-04** disc:2026-05-01 |\n"
        )
        m = status.mtti(text, today="2026-05-12")
        assert m["open_n"] == 0
        assert m["oldest_open"] is None

    def test_mtti_line_is_string_on_live_repo(self):
        # Smoke: the live board line must render without raising.
        line = status.mtti_line()
        assert isinstance(line, str) and "closed" in line or "open" in line


class TestLiveCheckSmoke:
    """live_check.main() hits the network — smoke the static parts only."""

    def test_url_list_is_diverse(self):
        assert len(live_check.LIVE_URLS) >= 3
        hosts = {u.split("/")[2] for u in live_check.LIVE_URLS}
        assert len(hosts) >= 3  # breadth: distinct domains

    def test_sample_truncates(self):
        body = "x" * 5000
        assert len(live_check._sample(body, n=600)) < len(body)
