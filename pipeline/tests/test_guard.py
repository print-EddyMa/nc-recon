"""Rate limits and security headers (terratriage.ops.guard)."""
import os

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def client():
    import sys
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server
    return TestClient(server.app)


@pytest.fixture(autouse=True)
def _fresh_limiter():
    from terratriage.ops import guard
    guard.LIMITER.reset()
    yield
    guard.LIMITER.reset()


def test_sliding_window_blocks_then_recovers():
    from terratriage.ops import guard
    rl = guard.RateLimiter()
    for i in range(3):
        assert rl.hit("k", 3, now=100.0 + i) == 0
    wait = rl.hit("k", 3, now=103.0)
    assert 0 < wait <= guard.WINDOW_S
    assert rl.hit("k", 3, now=100.0 + guard.WINDOW_S + 0.01) == 0  # oldest hit expired


def test_buckets_are_separate():
    from terratriage.ops import guard
    rl = guard.RateLimiter()
    assert rl.hit("write:1.2.3.4", 1, now=0) == 0
    assert rl.hit("write:1.2.3.4", 1, now=0) > 0
    assert rl.hit("read:1.2.3.4", 1, now=0) == 0     # another class, same client
    assert rl.hit("write:5.6.7.8", 1, now=0) == 0    # another client


def test_write_limit_answers_429(client, monkeypatch):
    from terratriage.ops import guard
    monkeypatch.setattr(guard, "WRITE_PER_MIN", 2)
    codes = [client.post("/ops/labels", json={}).status_code for _ in range(3)]
    assert codes[0] != 429 and codes[1] != 429 and codes[2] == 429
    r = client.post("/ops/labels", json={})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/health").status_code == 200          # exempt, and reads are a separate bucket


def test_forwarded_for_only_when_proxy_trusted(monkeypatch):
    from terratriage.ops import guard

    class Req:
        def __init__(self, headers, host):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    r = Req({"x-forwarded-for": "203.0.113.9, 10.0.0.2"}, "10.0.0.1")
    monkeypatch.delenv("NCR_TRUST_PROXY", raising=False)
    assert guard.client_ip(r) == "10.0.0.1"
    monkeypatch.setenv("NCR_TRUST_PROXY", "1")
    assert guard.client_ip(r) == "203.0.113.9"


def test_security_headers_on_api_and_health(client):
    for path in ("/health", "/ops/meta"):
        h = client.get(path).headers
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
        assert "script-src 'self'" in h["Content-Security-Policy"]
        assert "googleapis" not in h["Content-Security-Policy"]   # fonts are bundled
        assert h["Cache-Control"] == "no-store"


def test_csp_hashes_inline_bootstrap_script(tmp_path):
    from terratriage.ops import guard
    (tmp_path / "index.html").write_text(
        '<html><head><script>\n  try { x = 1 } catch (e) {}\n</script>'
        '<script type="module" src="/assets/a.js"></script></head></html>', encoding="utf-8")
    hashes = guard.inline_script_hashes(str(tmp_path))
    assert len(hashes) == 1 and hashes[0].startswith("'sha256-")
    assert hashes[0] in guard.csp(str(tmp_path))
    assert guard.inline_script_hashes(str(tmp_path / "missing")) == []
    assert "sha256" not in guard.csp(None)


def test_csp_connect_extension(monkeypatch):
    from terratriage.ops import guard
    monkeypatch.setenv("NCR_CSP_CONNECT", "https://tiles.example.gov https://api.example.gov")
    policy = guard.csp(None)
    assert "https://tiles.example.gov https://api.example.gov" in policy
    assert "connect-src 'self'" in policy
