"""Normalize arbitrary date strings to ISO 8601 (YYYY-MM-DD).

Since DDGS v8 never returns published_date for text results, two fallback
strategies fill the gap:
  1. URL path date extraction  — e.g. /2026/05/28/, /2026-05-28
  2. Text pattern extraction   — ISO 8601, "May 28, 2026", etc. in article body
"""

from __future__ import annotations

import re

import dateparser

_SETTINGS = {
    "PREFER_DAY_OF_MONTH": "first",
    "RETURN_AS_TIMEZONE_AWARE": False,
    "PREFER_LOCALE_DATE_ORDER": True,
}

# URL date patterns (tried in order, most specific first)
_URL_PATTERNS: list[re.Pattern] = [
    # /2026/05/28/  or  /2026/05/28
    re.compile(r"/(\d{4})/(\d{1,2})/(\d{1,2})(?:[/\-_?#]|$)"),
    # /2026-05-28  or  _2026-05-28
    re.compile(r"[/_-](\d{4})-(\d{2})-(\d{2})(?:[/\-_?#]|$)"),
    # ?date=20260528  or &date=2026-05-28
    re.compile(r"[?&]date=(\d{4})[-/]?(\d{2})[-/]?(\d{2})(?:&|$)"),
    # /20260528/  (compact)
    re.compile(r"/(\d{4})(\d{2})(\d{2})/"),
]

# Text date patterns for body extraction (most common in articles)
_TEXT_PATTERNS: list[re.Pattern] = [
    # YYYY-MM-DD
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    # Month DD, YYYY  or  Month D, YYYY
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September"
        r"|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{1,2}),\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    # DD Month YYYY
    re.compile(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August"
        r"|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug"
        r"|Sep|Oct|Nov|Dec)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]

_MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def to_iso8601(raw: str | None) -> str | None:
    """Parse a fuzzy date string and return YYYY-MM-DD, or None if unparseable."""
    if not raw or not raw.strip():
        return None
    try:
        dt = dateparser.parse(raw.strip(), settings=_SETTINGS)
        if dt:
            return dt.date().isoformat()
    except Exception:
        pass
    return None


def extract_date_from_url(url: str) -> str | None:
    """Extract a publication date from a URL path using regex patterns.

    Examples:
      https://example.com/2026/05/28/article → "2026-05-28"
      https://blog.com/posts/2026-05-28-title → "2026-05-28"
    """
    if not url:
        return None
    for pattern in _URL_PATTERNS:
        m = pattern.search(url)
        if m:
            groups = m.groups()
            try:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                if 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                continue
    return None


def extract_date_from_text(text: str) -> str | None:
    """Extract the first recognizable date from article body text.

    Tries regex patterns before falling back to dateparser for reliability.
    Returns None if no date is found or parsing fails.
    """
    if not text or len(text) < 8:
        return None

    # Pattern 1: YYYY-MM-DD
    m = _TEXT_PATTERNS[0].search(text[:2000])
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # Pattern 2: "Month DD, YYYY"
    m = _TEXT_PATTERNS[1].search(text[:2000])
    if m:
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month_num = _MONTH_MAP.get(month_name)
        if month_num and 2000 <= year <= 2099 and 1 <= day <= 31:
            return f"{year:04d}-{month_num:02d}-{day:02d}"

    # Pattern 3: "DD Month YYYY"
    m = _TEXT_PATTERNS[2].search(text[:2000])
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month_num = _MONTH_MAP.get(month_name)
        if month_num and 2000 <= year <= 2099 and 1 <= day <= 31:
            return f"{year:04d}-{month_num:02d}-{day:02d}"

    return None


def best_effort_date(
    raw: str | None = None,
    url: str | None = None,
    body: str | None = None,
) -> str | None:
    """Return the best available date from multiple sources, in priority order:
    1. raw string (e.g. from article metadata)
    2. URL path extraction
    3. Article body text extraction
    Returns None if all sources fail.
    """
    return (
        to_iso8601(raw)
        or (extract_date_from_url(url) if url else None)
        or (extract_date_from_text(body) if body else None)
    )
