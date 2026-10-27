"""Build, verify and import offline packs.

  PYTHONPATH=src .venv/bin/python -m terratriage.ops.offline pack --area swannanoa [--out DIR] [--tar]
  PYTHONPATH=src .venv/bin/python -m terratriage.ops.offline import PACK [--replace]
  (from pipeline/; see __main__.py)

A pack is a directory (or a .tar of one) holding everything one assessed area
needs to be reviewed with no network:

  manifest.json             format, area, event and area specs, every file with
                            its sha256 and size, licences, what was left out
  outputs/<area>.*          the assessment and its sidecars (never addresses)
  raw/<area>/               the before / after rasters as JPEG display copies
                            (q85; for viewing and review, never re-assessment)
                            and the imagery sidecar
  cache/openfema/dr_N.json  the event's declaration, so the event loads offline
  basemap/{z}/{x}/{y}.jpg   USGS The National Map topo tiles around the area
  web/                      optional: the built web app, for a laptop without one

Building only reads the live outputs and rasters; it writes nothing but the
pack. Importing checks every checksum first, extracts a tar safely (regular
files only, no absolute or parent paths, no links), never touches labels, and
refuses to replace a different copy of the same area unless asked.
"""
from __future__ import annotations

import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
from typing import Any

import yaml

from .. import BASEMAP_DIR, DATA_DIR, OPS_CACHE, OPS_OUT, RAW_DIR
from . import FORMAT, basemap

AREA_RE = re.compile(r"[a-z0-9_]{1,40}")
EVENT_RE = re.compile(r"[a-z0-9-]{3,40}")
MAX_MB_DEFAULT = 150
JPEG_QUALITY = 85
NEVER_PACKED = ("responder.json",)        # addresses: see docs/ops/SECURITY.md
LABELS_NOTE = ("Labels and Verify judgments made with this pack stay on that laptop: version 1 has no "
               "sync back to the EOC. Export them (data/labels/<area>.csv) and hand them over.")
OFFLINE_LIMITS = [
    "No new assessments: imagery, structures and hazard data are fetched from the network.",
    "No live conditions (river gauges, alerts, outages, shelters).",
    "No FEMA assistance by ZIP code and no Civil Air Patrol photos that were not cached.",
]


class PackError(ValueError):
    pass


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _specs(area: str) -> tuple[str, dict, dict, str]:
    """(event id, event spec, area spec, where the spec came from)."""
    from ..plan import events as ev

    found = ev.event_for_area(area)
    if not found:
        raise PackError(f"{area} is not a registered area")
    e, _aoi = found
    cfg = (_yaml(ev._config_path()).get("events") or {})
    reg = _yaml(ev.registry_path())
    if e.id in cfg:
        espec, origin = dict(cfg[e.id]), "config"
    else:
        espec, origin = dict((reg.get("events") or {}).get(e.id) or {}), "registry"
    aspec = dict((espec.get("aois") or {}).get(area) or (reg.get("aois") or {}).get(area) or {})
    espec.pop("aois", None)
    return e.id, espec, aspec, origin


def _bbox(fc: dict) -> tuple[float, float, float, float]:
    xs = [f["properties"]["centroid"] for f in fc.get("features", []) if (f.get("properties") or {}).get("centroid")]
    if xs:
        return (min(x for x, _ in xs), min(y for _, y in xs), max(x for x, _ in xs), max(y for _, y in xs))
    c = ((fc.get("properties") or {}).get("aoi") or {}).get("center")
    if not c:
        raise PackError("the assessment has no structures and no centre")
    return c[0], c[1], c[0], c[1]


def _display_copy(src: str, dst: str) -> None:
    """The raster as a tiled JPEG-in-GeoTIFF: same grid, a fraction of the size."""
    import rasterio

    with rasterio.open(src) as s:
        prof = s.profile.copy()
        prof.update(driver="GTiff", compress="JPEG", jpeg_quality=JPEG_QUALITY, tiled=True,
                    blockxsize=512, blockysize=512, nodata=None)
        prof.pop("predictor", None)
        if s.count == 3 and s.dtypes[0] == "uint8":
            prof["photometric"] = "YCBCR"
        with rasterio.open(dst, "w", **prof) as d:
            for _, win in s.block_windows(1):
                d.write(s.read(window=win), window=win)


def build(area: str, out_root: str, *, allow_test: bool = False, with_web: str | None = None,
          as_tar: bool = False, max_mb: float = MAX_MB_DEFAULT, force: bool = False,
          fetch=None) -> tuple[str, dict[str, Any]]:
    if not AREA_RE.fullmatch(area):
        raise PackError("bad area id")
    gj = os.path.join(OPS_OUT, f"{area}.geojson")
    if not os.path.exists(gj):
        raise PackError(f"no assessment for {area}")
    with open(gj, encoding="utf-8") as fh:
        fc = json.load(fh)
    eid, espec, aspec, origin = _specs(area)
    role = str(aspec.get("role") or ((fc.get("properties") or {}).get("aoi") or {}).get("role") or "OPS")
    if role == "TEST" and not allow_test:
        raise PackError(f"{area} is a TEST (hold-out) area; refusing to pack it unless --allow-test")
    stamp = time.strftime("%Y%m%d", time.gmtime())
    root = os.path.join(out_root, f"groma-pack-{area}-{stamp}")
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    files: list[dict[str, Any]] = []
    left_out: list[str] = []

    def add(rel: str, kind: str, **extra) -> None:
        p = os.path.join(root, rel)
        files.append({"path": rel, "kind": kind, "bytes": os.path.getsize(p), "sha256": _sha256(p), **extra})

    # outputs: the assessment and every sidecar except addresses
    os.makedirs(os.path.join(root, "outputs"))
    for src in sorted(glob.glob(os.path.join(OPS_OUT, f"{area}.*"))):
        name = os.path.basename(src)
        if not os.path.isfile(src) or name.endswith(".tmp"):
            continue
        if any(name == f"{area}.{x}" for x in NEVER_PACKED):
            left_out.append(f"outputs/{name} (addresses)")
            continue
        shutil.copyfile(src, os.path.join(root, "outputs", name))
        add(f"outputs/{name}", "output")

    # rasters as display copies, plus their sidecars
    rdir = os.path.join(RAW_DIR, area)
    if os.path.isdir(rdir):
        os.makedirs(os.path.join(root, "raw", area))
        for src in sorted(glob.glob(os.path.join(rdir, "*"))):
            name = os.path.basename(src)
            dst = os.path.join(root, "raw", area, name)
            if name.endswith(".tif") and name.startswith(("pre_", "post_")):
                _display_copy(src, dst)
                add(f"raw/{area}/{name}", "raster", display_copy=True,
                    note=f"JPEG q{JPEG_QUALITY} copy for viewing and review; never re-assess from it")
            elif name in ("imagery.json", "meta.json"):
                with open(src, encoding="utf-8") as fh:
                    meta = json.load(fh)
                for role_ in ("pre", "post"):     # absolute paths from the building machine are meaningless
                    if isinstance(meta.get(role_), dict) and meta[role_].get("path"):
                        meta[role_]["path"] = os.path.basename(meta[role_]["path"])
                with open(dst, "w", encoding="utf-8") as fh:
                    json.dump(meta, fh, indent=1)
                add(f"raw/{area}/{name}", "imagery_meta")
    else:
        left_out.append("raw imagery (not stored for this area): the map shows structures without imagery")

    # the declaration, so the event loads with no network
    from ..collect.base import DiskCache
    from ..plan.events import fetch_declaration

    ofc = DiskCache("openfema")
    for n in espec.get("disaster_numbers") or []:
        try:
            fetch_declaration(int(n))     # cached, seeded, or fetched now
        except Exception:  # noqa: BLE001 - provisional or unreachable: the import falls back to the spec
            pass
        p = ofc.path(f"dr_{int(n)}")
        if os.path.exists(p):
            os.makedirs(os.path.join(root, "cache", "openfema"), exist_ok=True)
            shutil.copyfile(p, os.path.join(root, "cache", "openfema", f"dr_{int(n)}.json"))
            add(f"cache/openfema/dr_{int(n)}.json", "declaration")

    # basemap around the area
    bm = basemap.extract(_bbox(fc), os.path.join(root, "basemap"), reuse_from=BASEMAP_DIR,
                         **({"fetch": fetch} if fetch else {}))
    for dirpath, _dirs, names in os.walk(os.path.join(root, "basemap")):
        for name in sorted(names):
            add(os.path.relpath(os.path.join(dirpath, name), root), "basemap")

    if with_web:
        if not os.path.isfile(os.path.join(with_web, "index.html")):
            raise PackError(f"{with_web} is not a built web app (no index.html)")
        shutil.copytree(with_web, os.path.join(root, "web"))
        for dirpath, _dirs, names in os.walk(os.path.join(root, "web")):
            for name in sorted(names):
                add(os.path.relpath(os.path.join(dirpath, name), root), "web")

    total = sum(f["bytes"] for f in files)
    if total > max_mb * 1e6 and not force:
        shutil.rmtree(root)
        raise PackError(f"pack would be {total / 1e6:.0f} MB, over the {max_mb:.0f} MB cap (use --force)")
    try:
        from ..cachekey import code_version

        version = code_version()
    except Exception:  # noqa: BLE001
        version = None
    manifest = {
        "format": FORMAT, "area": area, "role": role, "event_id": eid, "event_spec": espec,
        "area_spec": aspec, "spec_origin": origin, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "groma_version": version, "bytes": total, "files": files, "basemap": bm,
        "left_out": left_out + ["labels, Verify judgments, the audit log, the registry and the service token"],
        "labels": LABELS_NOTE, "offline_limits": OFFLINE_LIMITS,
        "licences": {"imagery": "as recorded in the assessment provenance", "basemap": basemap.LICENSE,
                     "structures": "FEMA USA Structures (CC BY 4.0), OpenStreetMap (ODbL 1.0)"},
    }
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    if as_tar:
        tar_path = root + ".tar"
        with tarfile.open(tar_path, "w") as tf:
            tf.add(root, arcname=os.path.basename(root))
        shutil.rmtree(root)
        return tar_path, manifest
    return root, manifest


# --------------------------------------------------------------------------- #
# verify + import
# --------------------------------------------------------------------------- #
def _safe_rel(rel: str) -> bool:
    if not rel or rel.startswith(("/", "\\")) or "\\" in rel or "\x00" in rel:
        return False
    parts = rel.split("/")
    return all(p not in ("", ".", "..") for p in parts) and os.path.normpath(rel) == rel


def verify(root: str) -> dict[str, Any]:
    """The manifest, after every file's checksum has been checked and every
    file on disk has been accounted for."""
    mp = os.path.join(root, "manifest.json")
    if not os.path.isfile(mp):
        raise PackError("not a pack: no manifest.json")
    with open(mp, encoding="utf-8") as fh:
        m = json.load(fh)
    if m.get("format") != FORMAT:
        raise PackError(f"unsupported pack format {m.get('format')!r}")
    if not AREA_RE.fullmatch(str(m.get("area", ""))) or not EVENT_RE.fullmatch(str(m.get("event_id", ""))):
        raise PackError("bad area or event id in the manifest")
    listed = set()
    for f in m.get("files") or []:
        rel = f.get("path", "")
        if not _safe_rel(rel):
            raise PackError(f"unsafe path in the manifest: {rel!r}")
        p = os.path.join(root, rel)
        if not os.path.isfile(p) or os.path.islink(p):
            raise PackError(f"missing file: {rel}")
        if os.path.getsize(p) != f.get("bytes") or _sha256(p) != f.get("sha256"):
            raise PackError(f"checksum mismatch: {rel}")
        if rel.startswith("outputs/") and not os.path.basename(rel).startswith(m["area"] + "."):
            raise PackError(f"output belongs to another area: {rel}")
        if any(rel.endswith("." + x) for x in NEVER_PACKED):
            raise PackError(f"pack carries a file that is never packed: {rel}")
        listed.add(rel)
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if rel != "manifest.json" and rel not in listed:
                raise PackError(f"file not in the manifest: {rel}")
    return m


def _extract(tar_path: str, dest: str, max_bytes: int = 2_000_000_000) -> str:
    """Extract a pack tar: regular files and directories only, inside `dest`."""
    total = 0
    with tarfile.open(tar_path, "r") as tf:
        members = tf.getmembers()
        tops = set()
        for mem in members:
            if not (mem.isfile() or mem.isdir()):
                raise PackError(f"pack tar holds a link or device: {mem.name}")
            if not _safe_rel(mem.name.rstrip("/")):
                raise PackError(f"unsafe path in the pack tar: {mem.name}")
            total += mem.size
            tops.add(mem.name.split("/")[0])
        if total > max_bytes:
            raise PackError("pack tar is larger than the import cap")
        if len(tops) != 1:
            raise PackError("pack tar must hold exactly one top-level directory")
        tf.extractall(dest, filter="data")
    return os.path.join(dest, tops.pop())


def _same(a: str, b: str) -> bool:
    return os.path.exists(b) and os.path.getsize(a) == os.path.getsize(b) and _sha256(a) == _sha256(b)


def _register(m: dict[str, Any]) -> list[str]:
    """Add the event and area to the ops registry when this install does not
    know them; areas from config are already here."""
    from ..plan import events as ev

    done = []
    known = ev.load_events()
    eid, area = m["event_id"], m["area"]
    if eid in known and area in known[eid].aois:
        return done
    path = ev.registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        reg = _yaml(path)
        if eid not in known:
            reg.setdefault("events", {})[eid] = m["event_spec"]
            done.append(f"event {eid}")
        if area not in (known.get(eid).aois if eid in known else {}):
            a = dict(m["area_spec"])
            a["event"] = eid
            a.pop("role", None)               # imported areas are operational, never TUNE/TEST data
            reg.setdefault("aois", {})[area] = a
            done.append(f"area {area}")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(reg, fh, sort_keys=False)
        os.replace(tmp, path)
    return done


def import_pack(path: str, *, replace: bool = False) -> dict[str, Any]:
    work = None
    root = path
    if os.path.isfile(path):
        work = tempfile.mkdtemp(prefix="groma-pack-")
        root = _extract(path, work)
    try:
        m = verify(root)
        area = m["area"]
        plan: list[tuple[str, str]] = []     # (source, destination)
        for f in m["files"]:
            rel = f["path"]
            src = os.path.join(root, rel)
            if rel.startswith("outputs/"):
                plan.append((src, os.path.join(OPS_OUT, os.path.basename(rel))))
            elif rel.startswith(f"raw/{area}/"):
                plan.append((src, os.path.join(RAW_DIR, area, os.path.basename(rel))))
            elif rel.startswith("cache/openfema/"):
                plan.append((src, os.path.join(OPS_CACHE, "openfema", os.path.basename(rel))))
            elif rel.startswith("basemap/"):
                plan.append((src, os.path.join(BASEMAP_DIR, rel[len("basemap/"):])))
        # the imagery sidecar is rewritten on import (local paths), so it is
        # never a conflict by itself; everything else must match or be replaced
        conflicts = [d for s, d in plan if (d.startswith((OPS_OUT, RAW_DIR)) and os.path.exists(d)
                                            and os.path.basename(d) != "imagery.json" and not _same(s, d))]
        if conflicts and not replace:
            raise PackError(f"{area} already exists here with different data ({len(conflicts)} files); "
                            "use --replace to overwrite it")
        written = 0
        for src, dst in plan:
            if os.path.basename(dst) == "imagery.json" and os.path.exists(dst) and not conflicts:
                continue                      # already imported: keep this machine's paths
            if _same(src, dst):
                continue
            if dst.startswith(os.path.join(OPS_CACHE, "openfema")) and os.path.exists(dst):
                continue                      # a declaration already cached here is at least as fresh
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst), suffix=".tmp")
            os.close(fd)
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            written += 1
        # the imagery sidecar points at this machine's copies
        side = os.path.join(RAW_DIR, area, "imagery.json")
        if os.path.exists(side):
            with open(side, encoding="utf-8") as fh:
                meta = json.load(fh)
            for role_ in ("pre", "post"):
                if isinstance(meta.get(role_), dict) and meta[role_].get("path"):
                    meta[role_]["path"] = os.path.join(RAW_DIR, area, os.path.basename(meta[role_]["path"]))
                    meta[role_]["display_copy"] = True
            with open(side + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=1)
            os.replace(side + ".tmp", side)
        registered = _register(m)
        basemap.merge_index(BASEMAP_DIR, area, {**m["basemap"], "pack_created_utc": m["created_utc"],
                                                "event_id": m["event_id"],
                                                "imported_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return {"area": area, "event_id": m["event_id"], "files": len(plan), "written": written,
                "registered": registered, "labels": LABELS_NOTE, "data_dir": DATA_DIR}
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)
