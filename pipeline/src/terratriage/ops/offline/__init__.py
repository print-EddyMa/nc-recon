"""Offline packs: one assessed area, carried to a laptop with no network.

  pack.py      build a pack from an area, verify it, and import it on
               another machine (`python -m terratriage.ops.offline`, see
               __main__.py for the exact command)
  basemap.py   a public-domain basemap extract (USGS The National Map) and the
               MapLibre style that shows it
  api.py       the routes that serve the local basemap and say what works
               offline (`/ops/offline`)

What a pack holds and what it never holds is in docs/ops/OFFLINE.md; the
security choices (addresses never packed, checksums, safe extraction) are in
docs/ops/SECURITY.md.
"""
from __future__ import annotations

import os

FORMAT = "groma-pack/1"


def offline_mode() -> bool:
    """NCR_OFFLINE=1: the server is running without a network on purpose."""
    return os.environ.get("NCR_OFFLINE", "").strip() == "1"
