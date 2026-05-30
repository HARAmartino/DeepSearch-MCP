"""Multi-stage content extraction pipeline.

Stage 1: trafilatura (primary) — best noise suppression, handles most sites.
Stage 2: readability-lxml + markdownify (fallback) — better for dense doc sites.
Stage 3: cleaner.py sanitization — remove residual boilerplate.

Key quirks handled here:
- trafilatura v2 does NOT preserve code fence language annotations.
  We pre-scan HTML with BeautifulSoup to collect them, then re-inject post-extraction.
- trafilatura v2 may duplicate content when HTML uses <article>/<main> landmarks.
  cleaner.deduplicate_blocks() removes the duplicate half.
- with_metadata=True in trafilatura breaks Markdown formatting.
  We call extract_metadata() separately and build frontmatter manually.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import trafilatura
from bs4 import BeautifulSoup

from ..utils.cleaner import clean
from ..utils.date_parser import to_iso8601

_MIN_CONTENT_LEN = 200
_MAX_CONTENT_CHARS = int(4000 * 4)  # ~4000 tokens × ~4 chars/token = 16 000 chars


# ---------------------------------------------------------------------------
# Domain adapters (Phase 6 / Day 2 Operations)
# ---------------------------------------------------------------------------
# Background: telemetry analysis (`evals/analyze_telemetry.py`) flags domains
# whose EMPTY_CONTENT / BLOCKED_403 rate exceeds 15%. The "Act" of the PDCA
# loop is to add a domain-specific HTML preprocessor here so trafilatura sees
# clean DOM. Each adapter:
#   - Receives the raw HTML string.
#   - Returns the modified HTML string (with noise removed).
#   - MUST be idempotent and safe for non-matching pages.
# Adapters are keyed by hostname suffix so `author.substack.com` matches.

def _substack_preprocess(html: str) -> str:
    """Strip Substack subscription widgets and CTAs before trafilatura.

    Substack articles wrap most of their visible page in a `<form>` subscription
    widget that, when included in extraction, either dominates the output
    (yielding the wrong "content") or causes trafilatura to bail out with
    EMPTY_CONTENT. Telemetry showed a 38% EMPTY_CONTENT rate on substack.com
    before this adapter.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return html

    # Selectors observed across Substack themes (Aug 2025 → present)
    selectors = [
        "div.subscription-widget-wrap",
        "div.subscription-widget",
        "div.subscribe-dialog",
        "div.subscribe-prompt",
        'div[data-component-name="SubscribePrompt"]',
        'div[data-component-name="SubscribeWidget"]',
        "form.subscribe-form",
        "div.post-footer",
        "div.paywall",
        ".comments-wrapper",
        "footer.post-footer",
    ]
    for sel in selectors:
        for el in soup.select(sel):
            el.decompose()
    return str(soup)


def _medium_preprocess(html: str) -> str:
    """Strip Medium member-only gates and upsell prompts.

    Telemetry showed a 27% BLOCKED_403 rate on medium.com — most of these are
    actually member-only paywalls served as 403. The adapter removes the gate
    overlay so trafilatura can still extract the preview prose underneath.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return html
    selectors = [
        '[data-test-id*="MemberOnly"]',
        '[aria-label*="Sign in"]',
        '[aria-label*="member-only"]',
        "div.meteredContent",
        "div.subscription-prompt",
        "div.js-postShareWidget",
    ]
    for sel in selectors:
        for el in soup.select(sel):
            el.decompose()
    return str(soup)


# Keyed by hostname suffix. Subdomain matches (foo.substack.com) handled in apply.
_DOMAIN_PREPROCESSORS: dict[str, callable] = {
    "substack.com": _substack_preprocess,
    "medium.com": _medium_preprocess,
}


def _apply_domain_adapter(html: str, url: str) -> str:
    """Route to a domain-specific preprocessor when one exists for the URL host."""
    if not url:
        return html
    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()
    preprocessor = _DOMAIN_PREPROCESSORS.get(hostname)
    if not preprocessor:
        # Match subdomains: author.substack.com → substack.com
        for suffix, fn in _DOMAIN_PREPROCESSORS.items():
            if hostname.endswith("." + suffix):
                preprocessor = fn
                break
    if preprocessor:
        return preprocessor(html)
    return html


def extract(html: str, url: str = "", include_links: bool = False) -> tuple[str, dict]:
    """Extract clean Markdown and metadata from raw HTML.

    Returns:
        (markdown_body, metadata_dict) where metadata_dict contains
        title, author, published_date, url, hostname.
    """
    # Phase 6: domain-specific noise removal (substack/medium gates, etc.)
    html = _apply_domain_adapter(html, url)

    # Collect code block language annotations before trafilatura strips them
    code_langs = _extract_code_languages(html)

    # Extract metadata separately (with_metadata=True corrupts Markdown output)
    meta = _extract_metadata(html, url)

    # Stage 1: trafilatura
    markdown = _run_trafilatura(html, include_links=include_links)

    # Stage 2: readability fallback
    if not markdown or len(markdown) < _MIN_CONTENT_LEN:
        markdown = _run_readability(html, include_links=include_links)

    if not markdown:
        return "", meta

    # Restore code block language annotations trafilatura stripped
    if code_langs:
        markdown = _restore_code_languages(markdown, code_langs)

    # Stage 3: clean residual noise and duplicates
    markdown = clean(markdown)

    # Stage 4 (Persona A FRICTION-D1): strip leading H1 if it duplicates frontmatter title
    if meta.get("title"):
        markdown = _strip_redundant_h1(markdown, meta["title"])

    # Truncate to protect context window
    if len(markdown) > _MAX_CONTENT_CHARS:
        tail = "\n\n*[Content truncated to protect context window]*"
        markdown = markdown[:_MAX_CONTENT_CHARS] + tail

    return markdown, meta


def _run_trafilatura(html: str, include_links: bool = False) -> str | None:
    try:
        result = trafilatura.extract(
            html,
            output_format="markdown",
            include_formatting=True,
            favor_precision=True,
            include_links=include_links,
            include_images=False,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        return result or ""
    except Exception:
        return ""


def _run_readability(html: str, include_links: bool = False) -> str | None:
    """Fallback: readability-lxml extracts main content node, markdownify converts."""
    try:
        from markdownify import markdownify as md
        from readability import Document

        doc = Document(html)
        content_html = doc.summary(html_partial=True)

        convert_links = "all" if include_links else "none"
        markdown = md(
            content_html,
            heading_style="ATX",
            bullets="-",
            convert_links=convert_links,
            strip=["script", "style", "nav", "footer", "aside"],
        )
        return markdown.strip() or ""
    except Exception:
        return ""


def _extract_metadata(html: str, url: str = "") -> dict:
    """Extract title, author, date, hostname via trafilatura.extract_metadata."""
    hostname = urlparse(url).hostname or ""
    defaults = {
        "title": "", "author": None, "published_date": None,
        "url": url, "hostname": hostname,
    }
    try:
        meta = trafilatura.extract_metadata(html, default_url=url or None)
        if not meta:
            return defaults
        return {
            "title": meta.title or "",
            "author": meta.author or None,
            "published_date": to_iso8601(meta.date),
            "url": url or meta.url or "",
            "hostname": hostname or (
                urlparse(meta.url or "").hostname or "" if meta.url else ""
            ),
        }
    except Exception:
        return defaults


def _extract_code_languages(html: str) -> list[str]:
    """Scan HTML for <pre><code class="language-X"> blocks and return languages in DOM order."""
    try:
        soup = BeautifulSoup(html, "lxml")
        langs: list[str] = []
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            lang = ""
            if code:
                for cls in code.get("class") or []:
                    if cls.startswith("language-"):
                        lang = cls[9:]
                        break
                    if cls.startswith("lang-"):
                        lang = cls[5:]
                        break
            langs.append(lang)
        return langs
    except Exception:
        return []


def _restore_code_languages(markdown: str, languages: list[str]) -> str:
    """Replace bare opening ``` fences with language-annotated versions, in order."""
    if not any(languages):
        return markdown

    idx = 0
    lines = markdown.split("\n")
    result: list[str] = []
    for line in lines:
        if re.match(r"^```\s*$", line) and idx < len(languages):
            line = f"```{languages[idx]}" if languages[idx] else "```"
            idx += 1
        result.append(line)
    return "\n".join(result)


_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


def _normalize_title(s: str) -> str:
    """Lowercase, strip punctuation/whitespace for fuzzy title comparison."""
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(s.split())


def _strip_redundant_h1(markdown: str, title: str) -> str:
    """Remove the first H1 line if it matches (or is a prefix of) the frontmatter title.

    Trafilatura often emits the article H1 verbatim while we already serialize
    the same string into frontmatter `title:`. Stripping the duplicate saves
    ~5-10% tokens on short articles (Persona A FRICTION-D1).
    """
    if not markdown or not title:
        return markdown

    norm_title = _normalize_title(title)
    if not norm_title:
        return markdown

    # Find the first H1 in roughly the leading region of the document
    head = markdown[:500]
    match = _H1_RE.search(head)
    if not match:
        return markdown

    norm_h1 = _normalize_title(match.group(1))
    if not norm_h1:
        return markdown

    # Match if H1 equals, contains, or is contained by the frontmatter title
    if norm_h1 == norm_title or norm_h1 in norm_title or norm_title in norm_h1:
        # Strip the matched H1 line plus any trailing blank line
        before = markdown[: match.start()]
        after = markdown[match.end():].lstrip("\n")
        return (before + after).lstrip("\n")

    return markdown


def build_frontmatter(meta: dict) -> str:
    """Format metadata as YAML frontmatter block."""
    lines = ["---"]
    if meta.get("title"):
        safe_title = meta["title"].replace('"', '\\"')
        lines.append(f'title: "{safe_title}"')
    if meta.get("author"):
        safe_author = str(meta["author"]).replace('"', '\\"')
        lines.append(f'author: "{safe_author}"')
    if meta.get("published_date"):
        lines.append(f'published_date: "{meta["published_date"]}"')
    if meta.get("url"):
        lines.append(f'url: {meta["url"]}')
    if meta.get("hostname"):
        lines.append(f'hostname: {meta["hostname"]}')
    lines.append("---")
    return "\n".join(lines)
