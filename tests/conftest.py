"""Shared pytest configuration.

Sets `DEEPSEARCH_TELEMETRY=0` so the @track decorator becomes a no-op during
tests — no telemetry.db writes, no fire-and-forget tasks dangling at loop close.
Individual telemetry tests opt back in via a fixture that overrides the env var
and points at a tmp directory.

Also isolates `DEEPSEARCH_CACHE_DIR` to a throwaway temp dir so the test suite
never reads or pollutes the real `./.cache/cache.db`. Without this, a live
`search_web` run (which caches real results) could leak into error-path tests
that expect a cache miss → flaky, order-dependent failures. (Must be set
before `core.cache` is imported, which reads the env at module load.)
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DEEPSEARCH_TELEMETRY", "0")
os.environ.setdefault(
    "DEEPSEARCH_CACHE_DIR",
    tempfile.mkdtemp(prefix="deepsearch-test-cache-"),
)
