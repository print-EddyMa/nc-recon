"""Access control for responder-only data. Fails closed.

* `TERRATRIAGE_TOKEN` set  -> requests need `Authorization: Bearer <token>`
  (constant-time compare).
* no token                 -> responder endpoints are **refused**, unless the
  operator explicitly runs in development mode with `NCR_DEV_OPEN=1`.

There is deliberately no "localhost is trusted" rule: behind a reverse proxy
(Caddy / nginx on the same host, the normal way to add HTTPS) every internet
request arrives from 127.0.0.1, so a loopback exemption would make all
building-level data public.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException


def token() -> str:
    return os.environ.get("TERRATRIAGE_TOKEN", "").strip()


def dev_open() -> bool:
    return os.environ.get("NCR_DEV_OPEN", "").strip() == "1"


def check(authorization: str | None) -> None:
    t = token()
    if t:
        if not authorization or not hmac.compare_digest(authorization.encode(), f"Bearer {t}".encode()):
            raise HTTPException(401, "responder token required")
        return
    if dev_open():
        return
    raise HTTPException(403, "responder access is disabled: the server has no TERRATRIAGE_TOKEN configured")


def startup_check(host: str) -> None:
    """Refuse to serve beyond this machine without a token (unless dev mode)."""
    if token() or dev_open():
        if dev_open() and host not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit("NCR_DEV_OPEN=1 is for local development only; unset it or bind HOST=127.0.0.1")
        return
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("refusing to start on a non-loopback address without TERRATRIAGE_TOKEN "
                         "(responder data would be unprotected). Set TERRATRIAGE_TOKEN.")
