"""Append-only audit trail of responder actions (data/audit.log, JSON lines).

Everyone authenticates with the same service token, so this log is how an
office reconstructs who exported what, when, from where: UTC time, action,
area, the labeler name when given, and the client address (the first
X-Forwarded-For hop when behind Caddy). Included in `run.py ops-backup`.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from . import DATA_DIR

PATH = os.environ.get("NCR_AUDIT_LOG") or os.path.join(DATA_DIR, "audit.log")
_lock = threading.Lock()


def client_addr(request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def record(action: str, request, area: str | None = None, **extra: Any) -> None:
    row = {"utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "action": action,
           "area": area, "client": client_addr(request),
           **{k: v for k, v in extra.items() if v is not None}}
    try:
        with _lock:
            os.makedirs(os.path.dirname(PATH), exist_ok=True)
            with open(PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
    except OSError as ex:  # never block an operation on the audit write
        print(f"[audit] write failed: {ex}")
