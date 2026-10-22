"""Offline packs from the command line (run from pipeline/):

  .venv/bin/python -m terratriage.ops.offline pack --area swannanoa [--out DIR] [--tar]
  .venv/bin/python -m terratriage.ops.offline verify PACK
  .venv/bin/python -m terratriage.ops.offline import PACK [--replace]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .pack import PackError, build, import_pack, verify


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m terratriage.ops.offline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="build an offline pack for one assessed area")
    p.add_argument("--area", required=True)
    p.add_argument("--out", default=".", help="directory to write the pack into (default: here)")
    p.add_argument("--tar", action="store_true", help="write one .tar instead of a directory")
    p.add_argument("--with-web", default=None, help="also carry a built web app (path to web/dist)")
    p.add_argument("--allow-test", action="store_true", help="permit a TEST (hold-out) area")
    p.add_argument("--max-mb", type=float, default=150.0)
    p.add_argument("--force", action="store_true", help="build even over the size cap")
    v = sub.add_parser("verify", help="check a pack's checksums and contents")
    v.add_argument("pack")
    i = sub.add_parser("import", help="verify a pack and add its area to this machine")
    i.add_argument("pack")
    i.add_argument("--replace", action="store_true", help="overwrite a different copy of the same area")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "pack":
            path, m = build(a.area, os.path.abspath(a.out), allow_test=a.allow_test, with_web=a.with_web,
                            as_tar=a.tar, max_mb=a.max_mb, force=a.force)
            b = m["basemap"]
            print(f"pack written: {path}\n  {len(m['files'])} files, {m['bytes'] / 1e6:.1f} MB; basemap "
                  f"{b['tiles']} tiles (z{b['minzoom']}-{b['maxzoom']}, {b['fetched']} fetched, {b['reused']} reused)")
            for x in m["left_out"]:
                print(f"  left out: {x}")
        elif a.cmd == "verify":
            if os.path.isfile(a.pack):
                import tempfile

                from .pack import _extract

                with tempfile.TemporaryDirectory() as t:
                    m = verify(_extract(a.pack, t))
            else:
                m = verify(a.pack)
            print(f"ok: {m['area']} ({m['event_id']}), {len(m['files'])} files, created {m['created_utc']}")
        else:
            r = import_pack(a.pack, replace=a.replace)
            print(json.dumps(r, indent=1))
    except PackError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
