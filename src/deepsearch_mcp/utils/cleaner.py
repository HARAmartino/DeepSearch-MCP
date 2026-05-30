"""Regex-based Markdown noise reduction.

Removes boilerplate artifacts that survive content extraction:
subscribe prompts, social share buttons, cookie notices, etc.
Also handles trafilatura-specific quirks (content duplication).
"""

from __future__ import annotations

import re

# Lines that are pure boilerplate noise.
#
# History
#   v1 (Phase 1):    initial set — cookies, subscribe, share, footer.
#   v2 (Phase 6+1):  Dogfooding session 2026-05-29 found four uncaught
#                    patterns in TechCrunch + LangChain blog fixtures
#                    (estimated reading time, audio CTAs, "Continue
#                    reading" gates, "Written by …" bylines duplicating
#                    frontmatter author). Added below.
_NOISE_LINE_RE = re.compile(
    r"(?:"
    # Phase 1 patterns
    r"skip\s+to\s+(main\s+)?content"
    r"|cookie\s+(settings|policy|consent|banner|notice)"
    r"|accept\s+(all\s+)?cookies?"
    r"|subscribe\s+to\s+(our\s+)?(newsletter|updates?|mailing list)"
    r"|sign\s+up\s+for\s+(our\s+)?newsletter"
    r"|share\s+on\s+(twitter|x\.com|facebook|linkedin|instagram|reddit|pinterest)"
    r"|follow\s+us\s+on\s+"
    r"|all\s+rights\s+reserved"
    r"|privacy\s+policy(\s*\||\s*[-–]\s*)?"
    r"|terms\s+(of\s+)?(use|service)"
    r"|©\s*\d{4}"
    r"|sign\s+(up|in)\s+to\s+(read|continue|access|unlock)"
    r"|already\s+a\s+(subscriber|member)"
    r"|related\s+(posts?|articles?|stories|reads?)"
    r"|you\s+might\s+(also\s+)?like"
    r"|read\s+more\s+(from|about|on)"
    r"|advertisement\s*$"
    r"|sponsored\s+(content|post|by)"
    r"|click\s+here\s+to\s+(read|learn|download|subscribe)"
    r"|back\s+to\s+top\s*$"
    # Phase 6+1 (Dogfooding) — uncaught 2026-style patterns
    # "Reading time: 8 min" / "Estimated reading time: 8 minutes"
    r"|(?:estimated\s+)?reading\s+time\s*[:\-–]\s*\d+"
    # "8 min read" on its own line
    r"|\d+\s*(?:min|minute|hour)s?\s+read\s*$"
    # "Continue reading to see..." / "Continue reading below"
    r"|continue\s+reading\s+(?:to\s+\S+|the\s+\S+|for\s+\S+|below)"
    # "Listen to this article on the X Podcast"
    r"|listen\s+to\s+this\s+(?:article|post|story)"
    # "Written by Maria Santos — Senior Correspondent"
    r"|written\s+by\s+[A-Z][\w\s]{1,50}\s+[—\-–]"
    # Newsletter consent gate: "By signing up, you agree to ..."
    r"|by\s+signing\s+up,?\s+you\s+agree"
    # "Get the latest … inbox" (any phrasing)
    r"|get\s+the\s+latest\b[^.]{0,80}\binbox\b"
    # "Tags: X, Y, Z"
    r"|tags?\s*[:\-]\s*[\w,\s]+$"
    # "Posted in: Engineering Blog"
    r"|posted\s+in\s*[:\-]?\s*[\w\s]+$"
    # "Originally published in TechCrunch"
    r"|originally\s+published\s+(?:on|in|at)\s+"
    # Bare "Estimated reading time" header
    r"|estimated\s+reading\s+time"
    # Phase 6+2 (Dogfooding 2026-05-29, surfaced by dogfood_audit.py) —
    # affiliate / sponsorship disclosures. These are full sentences, so the
    # noise-leak auditor's STRONG tier (length-independent) flagged them where
    # the human eyeball + length-gated heuristic had missed them.
    # "This article may contain affiliate links. If you buy … commission."
    r"|\baffiliate\s+links?\b"
    r"|\bmay\s+earn\s+an?\s+commission\b"
    r"|\bthis\s+(?:article|post|page)\s+(?:may\s+)?contains?\s+affiliate"
    r"|\bpaid\s+(?:partnership|promotion)\b"
    r")",
    re.IGNORECASE,
)

# Excessive blank lines (3+ → 2)
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")

# Trailing whitespace on each line
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)


def remove_noise_lines(text: str) -> str:
    """Remove lines that match known boilerplate patterns."""
    lines = text.splitlines()
    cleaned = [ln for ln in lines if not _NOISE_LINE_RE.search(ln)]
    return "\n".join(cleaned)


def normalize_whitespace(text: str) -> str:
    """Collapse 3+ blank lines to 2, strip trailing whitespace per line."""
    text = _TRAILING_WS_RE.sub("", text)
    text = _EXCESS_NEWLINES_RE.sub("\n\n", text)
    return text.strip()


# Wikipedia-style inline citation markers: "...chatbots.[1] Biased...[12]".
# Discovered 2026-05-30 reading a REAL Wikipedia extraction (my hand-written
# fixtures never contained citations). Real context pollution per Directive 1.
# TRAP: "[0]" / "[1]" are also array indices in code, so this MUST run only
# outside code — `arr[1]` and a fenced ```list[0]``` must survive untouched.
_CITATION_RE = re.compile(r"\[\d{1,3}\]")

# Wikipedia editorial / dispute annotations that survive extraction as bracketed
# text: "[citation needed]", "[update]", "[note 1]", "[dubious – discuss]"...
# Found 2026-05-30 inspecting REAL wiki pages (LLM, Transformer articles).
# CRITICAL: this is an ALLOW-LIST of known editorial phrases, NOT a blanket
# "[word]" strip — because the same pages contain "[MASK]", "[UNK]", "[CLS]"
# which are real NLP tokens (content!). An allow-list preserves them by default.
_EDITORIAL_RE = re.compile(
    r"\[\s*(?:"
    r"citation needed|page needed|better source needed|"
    r"additional citations?\s+needed|unreliable source\??|original research\??|"
    r"clarification needed|failed verification|verification needed|"
    r"dubious[^\]]*|disputed[^\]]*|update|needs update|when\?|who\?|why\?|"
    r"where\?|whom\?|according to whom\??|by whom\??|vague|"
    r"note\s+\d+|note\s+[a-z]"
    r")\s*\]",
    re.IGNORECASE,
)
# Split keeping delimiters: fenced ```blocks``` and inline `code` are protected.
_CODE_SPAN_RE = re.compile(r"(```.*?```|`[^`\n]+`)", re.DOTALL)


def strip_reference_markers(text: str) -> str:
    """Remove `[N]` citations + known Wikipedia editorial tags from prose.

    Never touches code spans (so `arr[1]` survives) and never strips bracketed
    tokens outside the editorial allow-list (so NLP tokens like `[MASK]`,
    `[UNK]` survive — they are content, not noise).
    """
    parts = _CODE_SPAN_RE.split(text)
    out: list[str] = []
    for part in parts:
        if part.startswith("```") or (part.startswith("`") and part.endswith("`")):
            out.append(part)  # code span — leave indices like arr[1] intact
        else:
            cleaned = _CITATION_RE.sub("", part)
            cleaned = _EDITORIAL_RE.sub("", cleaned)
            cleaned = re.sub(r" {2,}", " ", cleaned)  # tidy gaps left behind
            out.append(cleaned)
    return "".join(out)


def deduplicate_blocks(text: str) -> str:
    """Remove duplicate paragraph/block segments (trafilatura <article>/<main> quirk).

    Trafilatura v2 sometimes outputs content twice when the HTML uses semantic
    landmark elements (<article>, <main>). This removes the duplicate half.
    """
    # Split on double-newlines to get logical blocks
    blocks = re.split(r"\n{2,}", text)
    if len(blocks) <= 2:
        return text

    seen: list[str] = []
    unique: list[str] = []
    for block in blocks:
        normalized = re.sub(r"\s+", " ", block.strip()).lower()
        if normalized and normalized not in seen:
            seen.append(normalized)
            unique.append(block)

    return "\n\n".join(unique)


# Wikipedia "chrome" that trafilatura dumps as a LEADING markdown table before
# the article prose: the "Part of a series on" nav template and infoboxes
# (person / footballer / company). Found 2026-05-30 on real Sam Altman, Mitoma,
# and LLM articles (B9). High-precision marker phrases — each rarely leads a
# legitimate non-infobox article. We only strip a *leading* table (before the
# first prose sentence), so mid-article data tables are never touched.
_WIKI_CHROME_MARKERS = (
    # navigation template
    "part of a series on",
    # person / sports infoboxes
    "personal information",
    "team information",
    "date of birth",
    "place of birth",
    "alma mater",
    "net worth",
    "notable work",
    "youth career",
    "senior career",
    "college career",
    "international career",
    # company / website / organization infoboxes (B18 — added 2026-05-30 after
    # the DuckDuckGo Wikipedia infobox leaked). Each is an infobox *key* that is
    # not a normal data-table column header, so the position+marker gate stays
    # high-precision. (Deliberately NOT "headquarters"/"founder"/"launched":
    # those can be columns in a legit company comparison table.)
    "type of site",
    "area served",
    "key people",
    "current status",
    "number of employees",
    "traded as",
)
_MAX_LEADING_SCAN = 60  # don't scan an unbounded "leading region"


def _is_prose_sentence(line: str) -> bool:
    """A line that looks like real article prose (not a table/heading/list)."""
    s = line.strip()
    if not s or "|" in s or s.startswith(("#", "-", "*", ">", "!", "=")):
        return False
    return len(s.split()) >= 8


def strip_leading_wiki_chrome(text: str) -> str:
    """Drop a leading Wikipedia infobox / "series" nav table before the prose.

    Conservative: strips only the leading region (up to the first prose
    sentence or second-level heading) and only if that region is a table
    carrying a known infobox/nav marker. Mid-article tables are untouched.
    """
    lines = text.split("\n")
    i = 0
    n = len(lines)

    # Skip leading blanks and a single leading H1 (the title).
    while i < n and not lines[i].strip():
        i += 1
    if i < n and re.match(r"^\s*#\s+\S", lines[i]):
        i += 1
        while i < n and not lines[i].strip():
            i += 1

    start = i
    end = i
    while end < n and (end - start) < _MAX_LEADING_SCAN:
        s = lines[end].strip()
        if _is_prose_sentence(s):
            break
        if re.match(r"^\s*#{2,}\s+\S", lines[end]):  # next section heading
            break
        end += 1

    region = "\n".join(lines[start:end]).lower()
    if "|" in region and any(m in region for m in _WIKI_CHROME_MARKERS):
        # Drop the leading chrome region (keep everything before `start` —
        # i.e. a leading H1 — and everything from `end` onward).
        kept = lines[:start] + lines[end:]
        return "\n".join(kept)
    return text


def clean(text: str) -> str:
    """Full pipeline: wiki chrome → dedup → noise → citations → normalize."""
    text = strip_leading_wiki_chrome(text)
    text = deduplicate_blocks(text)
    text = remove_noise_lines(text)
    text = strip_reference_markers(text)
    text = normalize_whitespace(text)
    return text
