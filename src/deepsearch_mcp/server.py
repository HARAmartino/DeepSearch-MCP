"""FastMCP entry point for DeepSearch-MCP.

Run with:
    python -m deepsearch_mcp.server
or via MCP config:
    {"command": "uv", "args": ["run", "python", "-m", "deepsearch_mcp.server"]}
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "deepsearch-mcp",
    instructions=(
        "DeepSearch-MCP: An intelligent web-search and content extraction server "
        "optimized for LLM Deep Research workflows. "
        "Tools: read_article (fetch + clean extraction), search_web (DDG search), "
        "suggest_queries (lateral research paths)."
    ),
)

# Register tools by importing their modules (side-effect: registers with mcp)
from .tools import extractor as _ext  # noqa: E402, F401
from .tools import search as _search  # noqa: E402, F401
from .tools import suggest as _suggest  # noqa: E402, F401

if __name__ == "__main__":
    mcp.run()
