"""MCP Tool: read_article — fetch and extract clean Markdown from a URL."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from ..core import errors as err
from ..core.extractor import build_frontmatter, extract
from ..core.http import FetchError, decode_html, fetch
from ..core.telemetry import track

mcp = FastMCP("deepsearch-read-article")

# Extensions that are never parseable as HTML article content
_NON_HTML_EXTENSIONS = frozenset(
    ".pdf .zip .gz .tar .rar .7z .docx .xlsx .pptx .odt .ods "
    ".jpg .jpeg .png .gif .webp .svg .ico .mp4 .mp3 .avi .mov "
    ".woff .woff2 .ttf .eot .exe .dmg .pkg .deb .rpm".split()
)

# Content-Type prefixes that are non-HTML
_NON_HTML_CONTENT_TYPES = (
    "application/pdf",
    "application/zip",
    "application/octet-stream",
    "application/msword",
    "application/vnd.",
    "image/",
    "audio/",
    "video/",
    "font/",
)


def _is_non_html_url(url: str) -> bool:
    """Return True if the URL extension signals a non-HTML resource."""
    try:
        path = PurePosixPath(urlparse(url).path)
        return path.suffix.lower() in _NON_HTML_EXTENSIONS
    except Exception:
        return False


def _is_non_html_content_type(content_type: str) -> bool:
    """Return True if the Content-Type header indicates a non-HTML response."""
    ct = content_type.lower().split(";")[0].strip()
    return any(ct.startswith(prefix) for prefix in _NON_HTML_CONTENT_TYPES)


@mcp.tool()
@track(tool_name="read_article", primary_input="url")
async def read_article(
    url: str,
    include_links: bool = False,
    include_images: bool = False,
) -> str:
    """
    Fetches and extracts the main content of a webpage as clean Markdown.

    ## USE WHEN
    - You have a **specific article URL** (from `search_web` results).
    - Reading news articles, blog posts, or documentation pages.
    - You need full text — snippets from `search_web` weren't enough.

    ## DO NOT USE WHEN
    - URL is a homepage, category page, or search result listing.
    - URL ends in `.pdf`, `.zip`, `.jpg`, `.docx`, etc. → returns UNSUPPORTED_FORMAT.
    - URL requires authentication / login.
    - You only need a snippet — `search_web` snippets are ~10× cheaper.

    ## PARAMETERS
    - `url`: Full article URL including scheme (https://...).
    - `include_links`: Default False. Keep markdown hyperlinks in the body?
      False saves ~10-30% tokens; only set True if link URLs are part of the answer.
    - `include_images`: Default False. Keep `![alt](src)` image markdown?
      False is almost always correct — images don't help LLM reasoning and
      bloat the context. Only set True if the page is fundamentally visual
      (charts, diagrams, infographics where alt-text carries the meaning).

    ## RETURNS
    - YAML frontmatter (title, author, published_date, url, hostname).
    - Clean Markdown body (headers, lists, code blocks with language).
    - Truncated at ~16,000 chars to protect context window.
    - Redundant H1 matching frontmatter title is stripped automatically.

    ## CONSTRAINTS
    - Removes ads, navbars, footers, and social share buttons automatically.
    - Timeout: 10s per attempt, 3 retries with exponential backoff.
    - Returns a structured JSON error if the site blocks access.

    ## EXAMPLES (Few-Shot)

    Good:
      url="https://realpython.com/python-async-io/"
      → "---\ntitle: Async IO in Python...\n---\n\n# Async IO\n\n..."
        (clean article with frontmatter, code blocks annotated with language)

    Good (error handled):
      url="https://example.com/paywalled-article"
      → {"status":"error","code":"BLOCKED_403","hint":"Try a cached version..."}

    Bad (wrong tool — use search_web first to discover URLs):
      url="https://google.com/search?q=python+asyncio"

    Bad (non-HTML resource — will return UNSUPPORTED_FORMAT error):
      url="https://example.com/report.pdf"
    """
    # Fast-path: reject obviously non-HTML URLs before any network call
    if _is_non_html_url(url):
        return err.structured_error(
            err.UNSUPPORTED_FORMAT,
            f"URL appears to be a non-HTML resource: {url}",
        )

    try:
        response = await fetch(url)
        html = decode_html(response)  # charset-aware (Shift_JIS/EUC-JP) — B20
    except FetchError as exc:
        # For CONN_ERROR / TIMEOUT, transient DNS/reset → retryable; hint targets fetch context
        exc_str = str(exc)
        transient = err.is_transient_conn_error(exc_str)
        if exc.code == err.CONN_ERROR:
            return err.structured_error(
                err.CONN_ERROR,
                exc_str,
                hint_override=(
                    "Network unreachable while fetching the URL (likely transient). "
                    "Retry once; if it persists, pick a different result from search_web."
                ),
                retryable_override=transient or exc.retryable,
            )
        if exc.code == err.TIMEOUT:
            return err.structured_error(
                err.TIMEOUT,
                exc_str,
                hint_override=(
                    "Target site is slow or unresponsive. "
                    "Skip this URL and try the next result from search_web."
                ),
            )
        # 403 / 429 / other codes use their default hints
        return err.structured_error(exc.code, exc_str, retryable_override=exc.retryable)
    except Exception as exc:
        return err.structured_error(
            err.CONN_ERROR,
            f"Unexpected error fetching {url}: {exc}",
            hint_override=(
                "Unexpected fetch failure. Skip this URL and try another "
                "result from search_web."
            ),
        )

    # Check for bad HTTP status that curl_cffi may have returned content for
    if response.status_code != 200:
        return err.from_http_status(response.status_code, url)

    # Content-Type guard: reject non-HTML responses even when status is 200
    content_type = response.headers.get("content-type", "")
    if content_type and _is_non_html_content_type(content_type):
        return err.structured_error(
            err.UNSUPPORTED_FORMAT,
            f"Non-HTML Content-Type '{content_type.split(';')[0].strip()}' for {url}",
        )

    markdown_body, meta = extract(html, url=url, include_links=include_links)

    if not markdown_body or len(markdown_body.strip()) < 50:
        return err.structured_error(
            err.EMPTY_CONTENT,
            f"Could not extract meaningful content from {url}",
        )

    frontmatter = build_frontmatter(meta)
    return f"{frontmatter}\n\n{markdown_body}"
