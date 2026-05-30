# Project Concept: DeepSearch-MCP
**Version:** 1.0 (2026-05-28)
**Status:** Active Design
**Codename:** "The Prefrontal Cortex for Agents"

---

## 1. Executive Summary
**DeepSearch-MCP** is not just a search wrapper; it is an **intelligent context layer** designed to solve the "Information Overload" and "Fragility" problems that plague autonomous LLM agents.

While standard MCP servers simply pipe raw data from the web to the LLM, DeepSearch-MCP acts as a **cognitive filter**. It digest raw HTML, strips noise, handles adversarial bot-protection, and suggests lateral thinking paths, allowing the agent to focus on **reasoning** rather than **parsing**.

---

## 2. The Problem: Why Existing Tools Fail Agents
Current web-search MCP implementations (including the base `duckduckgo-mcp-server`) face three critical failures when deployed in autonomous "Deep Research" loops:

### 📉 A. Context Pollution (The "Noise" Problem)
*   **Issue:** Standard scrapers return navigation bars, cookie banners, sidebars, and ad scripts.
*   **Impact:** This wastes 40-70% of the context window with irrelevant tokens. It increases latency, cost, and triggers the "Lost in the Middle" phenomenon, where LLMs miss critical facts buried in noise.
*   **Requirement:** We need **Surgical Extraction**—delivering only the "meat" of the content in clean Markdown.

### 🛑 B. The "Glass Jaw" (Fragility)
*   **Issue:** The web is hostile. Cloudflare Turnstile, Akamai, and simple rate-limiting (429) block standard Python `requests` or `httpx` instantly.
*   **Impact:** Agents hit a wall and hallucinate or terminate the task prematurely.
*   **Requirement:** **Adversarial Networking**. The server must mimic a real browser (TLS fingerprinting) and handle retries intelligently without waking the human operator.

### 🔄 C. Passive Retrieval vs. Active Research
*   **Issue:** Standard tools answer *exactly* what is asked but fail to guide the agent when the query is flawed or the topic is complex.
*   **Impact:** Agents get stuck in "local minima," reading the same 3 SEO-optimized articles repeatedly.
*   **Requirement:** **Cognitive Support**. The tool should suggest related entities, counter-arguments, and deeper search vectors.

---

## 3. Core Philosophy: "Context Engineering"
We adopt the philosophy of **Context Engineering** (2025+ trend): *The quality of an agent's output is bounded by the signal-to-noise ratio of its input.*

| Feature | Standard MCP Server | **DeepSearch-MCP** |
| :--- | :--- | :--- |
| **Input** | URL / Query | URL / Query + **Intent Context** |
| **Processing** | HTML -> Text | HTML -> **DOM Analysis** -> **Semantic Cleaning** -> Markdown |
| **Networking** | `requests` / `httpx` | `curl_cffi` (Impersonation) + **Auto-Rotation** |
| **Output** | Raw String | **Structured Object** (Content + Metadata + Confidence Score) |
| **Error** | Exception Traceback | **Actionable Hint** (e.g., "Try a broader query") |

---

## 4. Architectural Pillars

### 🏛️ Pillar 1: The "Clean Room" Extraction Engine
We do not trust the raw HTML. We use a multi-stage pipeline to ensure purity.
1.  **Fetch:** Stealth fetch via `curl_cffi`.
2.  **Parse:** `trafilatura` for main content extraction (proven F1-score superiority).
3.  **Sanitize:** Regex-based removal of "Read More", "Subscribe", and "Related Posts" artifacts that confuse LLMs.
4.  **Format:** Strict Markdown with YAML frontmatter (Title, Date, Author) for grounding.

### 🏛️ Pillar 2: Agentic Resilience
The server assumes failure is the default state.
*   **Smart Retries:** Exponential backoff with jitter on 429/503 errors.
*   **Fallback Chains:** If DuckDuckGo HTML fails -> Try DuckDuckGo Lite -> Try Bing Cache (if available).
*   **Honest Reporting:** If a page is paywalled or blocked, return a structured `{"status": "blocked", "reason": "paywall"}` so the agent can move on, rather than guessing.

### 🏛️ Pillar 3: Lateral Thinking Support
To support **Deep Research** workflows (iterative investigation):
*   **`suggest_queries`**: Analyzes the *current* search results to find gaps. (e.g., "You found 5 articles on *benefits*, but 0 on *risks*. Suggest searching for 'side effects' or 'criticism'.")
*   **Entity Extraction**: Highlights key people/orgs mentioned in snippets for easy drill-down.

---

## 5. Target Use Cases
1.  **Autonomous Deep Research Agents:** Agents that write 10-page reports by iterating through 50+ sources.
2.  **Fact-Checking Bots:** Systems that need to verify a claim against primary sources quickly.
3.  **RAG Pipelines:** Pre-processing web data before embedding into a vector database (cleaner data = better retrieval).

---

## 6. Differentiation from Base Repo
*   **Base (`nickclyde/duckduckgo-mcp-server`):** A functional "remote control" for DuckDuckGo. Good for simple queries.
*   **DeepSearch-MCP:** A "research assistant". It optimizes for **token efficiency**, **stealth**, and **agent autonomy**.

---

## 7. Success Metrics (KPIs)
*   **Token Reduction:** >60% reduction in tokens per page compared to raw HTML scraping.
*   **Success Rate:** >90% successful content retrieval on top 100 tech/news domains (bypassing basic bot protection).
*   **Agent Autonomy:** Reduction in "human intervention" requests due to scraping errors.