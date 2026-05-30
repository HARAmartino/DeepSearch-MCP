# Technical Specification: DeepSearch-MCP
**Version:** 1.0.0-draft
**Target Audience:** AI Agent (Claude Code) & Maintainers
**Status:** Approved for Implementation

---

## 1. System Architecture

### 1.1 Data Flow
```mermaid
graph TD
    User[LLM Agent] -->|MCP Call| Server[FastMCP Server]
    Server -->|Check| Cache[(SQLite Cache)]
    Cache -->|Hit| Server
    Cache -->|Miss| Fetcher[Stealth Fetcher (curl_cffi)]
    Fetcher -->|HTML| Extractor[Extraction Engine]
    Extractor -->|Markdown + Meta| Server
    Server -->|Response| User
    
    subgraph Extraction Engine
        Trafilatura[Trafilatura (Primary)]
        Readability[Readability-LXML (Fallback)]
        Cleaner[Regex Noise Cleaner]
    end
```

### 1.2 Core Components
1.  **`server.py`**: FastMCP entry point. Registers tools and handles lifecycle.
2.  **`core/http.py`**: Wrapper around `curl_cffi`. Handles TLS impersonation, retries, and proxy rotation (future).
3.  **`core/extractor.py`**: Orchestrates the "Clean Room" pipeline (Fetch -> Parse -> Sanitize).
4.  **`core/cache.py`**: SQLite-based response caching to respect rate limits and speed up ReAct loops.

---

## 2. MCP Tools API Definition

### 2.1 `search_web`
Performs a web search using DuckDuckGo. Returns structured results with metadata.

*   **Input Schema:**
```python
    class SearchInput(BaseModel):
        query: str = Field(description="The search query. Use keywords, not full sentences.")
        region: str = Field(default="wt-wt", description="Region code (e.g., 'jp-jp', 'us-en', 'wt-wt' for global).")
        safesearch: Literal["on", "moderate", "off"] = Field(default="moderate")
        timelimit: Optional[Literal["d", "w", "m", "y"]] = Field(default=None, description="d=day, w=week, m=month, y=year")
        max_results: int = Field(default=10, ge=1, le=50)
```
*   **Output Schema:** `List[SearchResult]` (See Data Models)*   **Behavior:**
    1.  Check Cache.
    2.  If miss, call `duckduckgo_search.DDGS.text()`.
    3.  Normalize dates to ISO 8601.
    4.  Store in Cache (TTL: 24h).
*   **Constraints:**
    *   Must handle `RatelimitException` by returning a structured error (See Sec 5).
    *   Must insert random jitter (0.5s - 2.0s) before request.

### 2.2 `read_article`
Fetches a URL and extracts the main content as clean Markdown.

*   **Input Schema:**
```python
    class ReadInput(BaseModel):
        url: str = Field(description="The full URL to fetch.")
        include_links: bool = Field(default=False, description="Keep hyperlinks in markdown? (False saves tokens)")
        include_images: bool = Field(default=False, description="Keep image markdown? (False saves tokens)")
```
*   **Output Schema:** `str` (Markdown with YAML Frontmatter)
*   **Behavior:**
    1.  **Fetch:** Use `curl_cffi` (impersonate="chrome131").
    2.  **Parse:** Try `trafilatura.extract(output_format="markdown")`.
    3.  **Fallback:** If trafilatura returns None/Empty, try `readability-lxml` + `markdownify`.
    4.  **Sanitize:** Remove "Subscribe", "Share", "Cookie" artifacts via Regex.
    5.  **Format:** Prepend YAML Frontmatter (Title, Author, Date, URL).
*   **Constraints:**
    *   Timeout: 10 seconds.
    *   Max Content Length: 100KB (truncate if larger to protect context).

### 2.3 `suggest_queries`
Suggests related search queries to help the agent broaden or deepen research.

*   **Input Schema:**
```python
    class SuggestInput(BaseModel):
        topic: str = Field(description="The main topic or current search query.")
        context: Optional[str] = Field(default=None, description="Optional context from previous results.")
```
*   **Output Schema:** `List[str]` (List of 3-5 suggested queries)
*   **Behavior:**
    *   Primary: Scrape "Related Topics" from DuckDuckGo HTML (if stable).
    *   Fallback: Use simple keyword permutation logic (e.g., add "vs", "alternatives", "risks").
    *   *Note: Do not use external LLM API for this to keep the server standalone.*

---

## 3. Data Models (Pydantic V2)

All internal data transfer objects must inherit from `BaseModel`.
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class SearchResult(BaseModel):
    title: str
    url: str
    body: str = Field(description="Snippet/Summary")
    published_date: Optional[str] = Field(default=None, description="ISO 8601 format (YYYY-MM-DD)")
    score: Optional[float] = Field(default=None, description="Relevance score if available")

class ArticleMetadata(BaseModel):
    title: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    url: str
    hostname: str

class StructuredError(BaseModel):
    status: Literal["error"] = "error"
    code: str = Field(description="Machine-readable error code (e.g., BLOCKED_403)")
    message: str
    hint: str = Field(description="Actionable advice for the LLM agent")
    retryable: bool = False
```

---

## 4. Core Logic Specifications

### 4.1 Stealth Networking (`core/http.py`)
*   **Library:** `curl_cffi.requests.AsyncSession`
*   **Impersonation:** `chrome131` (or latest stable available in lib).
*   **Headers:**
    *   `Accept-Language`: `en-US,en;q=0.9,ja;q=0.8` (Rotate based on region)
    *   `Sec-Fetch-Dest`: `document`
*   **Retry Policy:**
    *   Max Retries: 3
    *   Backoff: Exponential (1s, 2s, 4s) with Jitter.
    *   Trigger on: 429, 500, 502, 503, 504.

### 4.2 Extraction Pipeline (`core/extractor.py`)
1.  **Input:** Raw HTML bytes.
2.  **Stage 1 (Trafilatura):**
    *   Config: `favor_precision=True`, `include_links=False`, `include_images=False`.
    *   *Check:* If result length < 200 chars, assume failure.
3.  **Stage 2 (Fallback - Readability):**
    *   Use `readability-lxml` to find main content node.    *   Convert to Markdown using `markdownify`.
4.  **Stage 3 (Sanitization):**
    *   Regex remove: `(?i)(subscribe to our newsletter|share on twitter|cookie settings|all rights reserved)`.
    *   Remove excessive newlines (`\n{3,}` -> `\n\n`).

---

## 5. Error Handling Protocol

The server must **never** raise a raw Python exception to the MCP client. It must return a JSON string representing a `StructuredError`.

| HTTP Status / Condition | Error Code | Hint for Agent | Retryable |
| :--- | :--- | :--- | :--- |
| 403 Forbidden | `BLOCKED_403` | "Access denied. The site likely has anti-bot protection. Try a different source." | False |
| 429 Too Many Requests | `RATE_LIMITED` | "Search rate limit reached. Wait 60s or refine query to be more specific." | True (after delay) |
| Timeout | `TIMEOUT` | "Site is unresponsive. Skip this URL and try another." | False |
| Extraction Failed | `EMPTY_CONTENT` | "Could not extract main content (maybe PDF or dynamic SPA). Skip." | False |
| Network Error | `CONN_ERROR` | "DNS or connection failed. Check URL validity." | False |

**Example Response:**
```json
{
  "status": "error",
  "code": "BLOCKED_403",
  "message": "403 Forbidden for url: https://example.com",
  "hint": "Access denied. The site likely has anti-bot protection. Try a different source.",
  "retryable": false
}
```

---

## 6. Caching Strategy

*   **Backend:** SQLite (`cache.db` in local data dir).
*   **Key Generation:**
    *   Search: `sha256(query + region + timelimit)`
    *   Article: `sha256(url)`
*   **TTL (Time To Live):**
    *   Search Results: 24 Hours.
    *   Article Content: 7 Days.
*   **Schema:**
```sql
    CREATE TABLE cache (
        key TEXT PRIMARY KEY,
        value TEXT, -- JSON serialized
        timestamp INTEGER,
        ttl INTEGER
    );
```
---

## 7. Configuration (Environment Variables)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DEEPSEARCH_CACHE_DIR` | `./.cache` | Directory for SQLite DB. |
| `DEEPSEARCH_TIMEOUT` | `10` | HTTP Timeout in seconds. |
| `DEEPSEARCH_MAX_TOKENS` | `4000` | Soft limit for article truncation. |
| `DEEPSEARCH_LOG_LEVEL` | `INFO` | Logging level. |

---

## ⚠️ Implementation Notes for AI Agent
1.  **Fact-Check:** Before implementing `search_web`, run `pip show duckduckgo-search` and verify the `DDGS` class methods. The API changed significantly between v6 and v7.
2.  **Async:** All I/O operations must be `async`. Use `curl_cffi.requests.AsyncSession`.
3.  **Date Parsing:** Use `dateparser` library to handle fuzzy dates like "2 hours ago" or "yesterday" and normalize to ISO 8601.