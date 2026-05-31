"""Pydantic V2 data models for all internal data transfer objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str
    url: str
    body: str = Field(description="Snippet/Summary")
    published_date: str | None = Field(
        default=None, description="ISO 8601 format (YYYY-MM-DD)"
    )
    score: float | None = Field(default=None, description="Relevance score if available")
    source_tier: str = Field(
        default="unknown",
        description="'authoritative' (curated trusted domain / .gov / .edu) "
        "or 'unknown' (not on the trust list — NOT necessarily low quality). "
        "Read 'authoritative' results first; if none, corroborate carefully.",
    )
    near_duplicate: bool = Field(
        default=False,
        description="True if this result's title closely matches an earlier "
        "result (same story/topic). The first/authoritative copy is kept as "
        "primary (False). Skip RE-READING near-duplicates, but their COUNT is "
        "useful corroboration — they are kept, not removed.",
    )
    story_cluster: int | None = Field(
        default=None,
        description="Integer id grouping results that report the SAME STORY "
        "across outlets — looser than near_duplicate (it links paraphrased "
        "headlines sharing key entities, e.g. 'DuckDuckGo'+'Google'). Same id = "
        "same event: they CORROBORATE each other but are NOT independent "
        "sources, so read 1–2 per cluster and don't count N same-cluster hits "
        "as N confirmations. Unlike near_duplicate, these are worth reading "
        "ACROSS. null = no cluster detected.",
    )


class ArticleMetadata(BaseModel):
    title: str
    author: str | None = None
    published_date: str | None = None
    url: str
    hostname: str


class StructuredError(BaseModel):
    status: Literal["error"] = "error"
    code: str = Field(description="Machine-readable error code (e.g., BLOCKED_403)")
    message: str
    hint: str = Field(description="Actionable advice for the LLM agent")
    retryable: bool = False
