"""Tests for the stealth fetcher's fingerprint rotation (B17).

Reuters (and similar anti-bot setups) return 401/403 to Chrome's TLS
fingerprint but 200 to Safari's. `fetch` must rotate fingerprints on a block.
Mocks `curl_cffi`'s `AsyncSession` so there is no network.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.deepsearch_mcp.core import http
from src.deepsearch_mcp.core.errors import BLOCKED_403, CONN_ERROR
from src.deepsearch_mcp.core.http import FetchError, decode_html, fetch


def _install_fake_session(monkeypatch, behavior, used):
    """Patch AsyncSession. `behavior(impersonate)` returns an int status or
    raises; `used` collects the impersonate targets actually tried."""

    class FakeSession:
        def __init__(self, *args, impersonate=None, **kwargs):
            self.impersonate = impersonate

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            used.append(self.impersonate)
            result = behavior(self.impersonate)
            if isinstance(result, Exception):
                raise result
            resp = MagicMock()
            resp.status_code = result
            resp.text = f"body-{result}"
            return resp

    monkeypatch.setattr(http, "AsyncSession", FakeSession)


class TestFingerprintRotation:
    async def test_rotates_to_safari_on_401(self, monkeypatch):
        used = []
        _install_fake_session(
            monkeypatch,
            lambda imp: 200 if imp == "safari17_0" else 401,
            used,
        )
        resp = await fetch("https://jp.reuters.com/x")
        assert resp.status_code == 200
        assert used == ["chrome131", "safari17_0"]  # tried chrome, then rotated

    async def test_403_also_rotates(self, monkeypatch):
        used = []
        _install_fake_session(
            monkeypatch, lambda imp: 200 if imp == "safari17_0" else 403, used
        )
        resp = await fetch("https://x.example/")
        assert resp.status_code == 200
        assert "safari17_0" in used

    async def test_all_fingerprints_blocked_raises_blocked_403(self, monkeypatch):
        used = []
        _install_fake_session(monkeypatch, lambda imp: 401, used)
        with pytest.raises(FetchError) as ei:
            await fetch("https://x.example/")
        assert ei.value.code == BLOCKED_403
        assert used == list(http._IMPERSONATE_TARGETS)  # all tried

    async def test_success_on_first_does_not_rotate(self, monkeypatch):
        used = []
        _install_fake_session(monkeypatch, lambda imp: 200, used)
        resp = await fetch("https://x.example/")
        assert resp.status_code == 200
        assert used == ["chrome131"]  # no rotation needed

    async def test_401_maps_to_blocked_not_conn_error(self, monkeypatch):
        # Regression: 401 previously mis-mapped to CONN_ERROR.
        used = []
        _install_fake_session(monkeypatch, lambda imp: 401, used)
        with pytest.raises(FetchError) as ei:
            await fetch("https://x.example/")
        assert ei.value.code == BLOCKED_403

    async def test_network_error_not_multiplied_across_fingerprints(self, monkeypatch):
        # A non-transient connection error surfaces immediately (no rotation),
        # so we don't waste a second fingerprint on a genuinely-down host.
        used = []
        _install_fake_session(
            monkeypatch, lambda imp: ValueError("malformed url thing"), used
        )
        with pytest.raises(FetchError) as ei:
            await fetch("https://x.example/")
        assert ei.value.code == CONN_ERROR
        assert used == ["chrome131"]  # only one fingerprint tried


class _Resp:
    """Minimal stand-in for a curl_cffi Response."""

    def __init__(self, content, headers=None, text="FALLBACK-TEXT"):
        self.content = content
        self.headers = headers or {}
        self.text = text


class TestDecodeHtml:
    """B20: charset-aware decoding (Shift_JIS / EUC-JP gov & legacy pages)."""

    def test_shift_jis_via_meta(self):
        raw = ("<html><head><meta charset=\"Shift_JIS\"></head>"
               "<body>テレビ共同施設</body></html>").encode("cp932")
        out = decode_html(_Resp(raw, {"content-type": "text/html"}))
        assert "テレビ共同施設" in out
        assert "�" not in out  # no mojibake

    def test_euc_jp_via_meta(self):
        raw = ("<html><head><meta charset='euc-jp'></head>"
               "<body>日本語テスト</body></html>").encode("euc-jp")
        assert "日本語テスト" in decode_html(_Resp(raw, {"content-type": "text/html"}))

    def test_header_charset_takes_priority(self):
        raw = "日本語UTF8".encode()
        out = decode_html(_Resp(raw, {"content-type": "text/html; charset=utf-8"}))
        assert "日本語UTF8" in out

    def test_utf8_default_when_no_declaration(self):
        raw = b"<html><body>plain ascii content</body></html>"
        assert "plain ascii content" in decode_html(_Resp(raw, {}))

    def test_non_bytes_content_falls_back_to_text(self):
        # A test mock whose .content isn't bytes must not crash.
        assert decode_html(_Resp(object(), {}, text="MOCK")) == "MOCK"

    def test_empty_content(self):
        assert decode_html(_Resp(b"", {})) == ""

    def test_bogus_declared_charset_does_not_crash(self):
        raw = b"hello"
        out = decode_html(_Resp(raw, {"content-type": "text/html; charset=not-a-real-charset"}))
        assert "hello" in out  # fell back to utf-8
