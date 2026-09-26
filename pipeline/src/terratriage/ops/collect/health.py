"""`run.py ops-health`: live status of every data source (the Collection board).

Status: ok | stale (reachable but data older than the source's threshold) |
down (error) | unconfigured (needs a credential we do not have). Written to
data/output/ops/health.json for the web Collection-status panel.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from .. import DATA_DIR
from ..provenance import utc_now
from .base import Connector, Health, SchemaError, http_json, parse_utc
from .eri import ERI
from .nc_orthos import NCOrthos
from .nsi import NSI
from .usa_structures import USAStructures
from .usgs_water import USGSWater


class NWPS(Connector):
    name = "nwps"
    license = "US Government work (NOAA NWS)"
    homepage = "https://api.water.noaa.gov/nwps/v1/docs/"
    stale_after_s = 3 * 3600

    def probe(self):
        d = http_json("https://api.water.noaa.gov/nwps/v1/gauges/MICN7", timeout=30)
        if "lid" not in d:
            raise SchemaError("NWPS gauge response missing lid")
        return None


class NWSAlerts(Connector):
    name = "nws_alerts"
    license = "US Government work (NOAA NWS)"
    homepage = "https://api.weather.gov"
    stale_after_s = 3600

    def probe(self):
        d = http_json("https://api.weather.gov/alerts/active?area=NC", timeout=30,
                      headers={"Accept": "application/geo+json"})
        if "features" not in d:
            raise SchemaError("NWS alerts missing features")
        upd = parse_utc(d.get("updated"))
        return time.time() - upd.timestamp() if upd else None


class OpenFEMA(Connector):
    name = "openfema"
    license = "US Government work (FEMA)"
    homepage = "https://www.fema.gov/about/openfema/api"
    stale_after_s = 30 * 86400

    def probe(self):
        d = http_json("https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries",
                      params={"$top": 1, "$orderby": "declarationDate desc"}, timeout=30)
        rows = d.get("DisasterDeclarationsSummaries") or []
        if not rows:
            raise SchemaError("OpenFEMA returned no rows")
        return None


class USGSLegacy(Connector):
    """Kept only to show the decommissioning on the board; nothing reads it."""
    name = "usgs_waterservices_legacy"
    license = "US Government work (USGS)"
    homepage = "legacy NWIS WaterServices (decommission Q1 2027)"
    URL = "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=02138500&parameterCd=00065"  # legacy-probe

    def probe(self):
        http_json(self.URL, timeout=20, retries=1)
        return None


class GEE(Connector):
    name = "google_earth_engine"
    license = "per dataset; noncommercial quota tier"
    homepage = "https://earthengine.google.com"

    def configured(self):
        if not os.environ.get("NCR_GEE_PROJECT"):
            return False, "set NCR_GEE_PROJECT + authenticate (earthengine authenticate) to enable"
        return True, ""

    def probe(self):
        return None


class Earthdata(Connector):
    name = "nasa_earthdata"
    license = "NASA open data"
    homepage = "https://urs.earthdata.nasa.gov"

    def configured(self):
        if not (os.path.exists(os.path.expanduser("~/.netrc")) or os.environ.get("EARTHDATA_TOKEN")):
            return False, "needs an Earthdata Login (~/.netrc or EARTHDATA_TOKEN) for OPERA / HLS / NISAR"
        return True, ""

    def probe(self):
        return None


class DamageModel(Connector):
    """Not a data feed, but a component that must be present: without it every
    structure loses its imagery classifier and lands in review."""
    name = "damage_model"
    license = "xView2 challenge terms (non-commercial)"
    homepage = "weights/xview2_cmu_classifier.onnx (see MODEL_CARD.md)"

    def configured(self):
        from ..pipeline import ONNX

        if not os.path.exists(ONNX):
            return False, f"model file missing: {ONNX} (mount it or set NCR_MODEL_PATH)"
        return True, ""

    def health(self) -> Health:
        ok, why = self.configured()
        if not ok:
            return Health(self.name, "down", None, None, why)
        t0 = time.time()
        try:
            import numpy as np
            import onnxruntime as ort

            from ..pipeline import ONNX

            sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"])
            out = sess.run(None, {sess.get_inputs()[0].name: np.zeros((1, 128, 128, 3), "float32")})[0]
            if out.shape != (1, 4):
                raise SchemaError(f"unexpected model output shape {out.shape}")
        except Exception as ex:  # noqa: BLE001
            return Health(self.name, "down", None, None, str(ex)[:200])
        return Health(self.name, "ok", round((time.time() - t0) * 1000), None, "")

    def probe(self):
        return None


def connectors() -> list[Connector]:
    return [DamageModel(), USGSWater(), NWPS(), NWSAlerts(), OpenFEMA(), NSI(), USAStructures(), NCOrthos(),
            ERI(), USGSLegacy(), GEE(), Earthdata()]


def run(write: bool = True) -> list[Health]:
    cs = connectors()
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda c: c.health(), cs))
    for c, h in zip(cs, res):
        h.detail = h.detail or c.homepage
    if write:
        out = os.path.join(DATA_DIR, "output", "ops")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "health.json"), "w", encoding="utf-8") as fh:
            json.dump({"checked_utc": utc_now(), "sources": [h.to_dict() for h in res]}, fh, indent=2)
    return res


def print_table(res: list[Health]) -> None:
    for h in res:
        age = "" if h.data_age_s is None else f"age {h.data_age_s / 3600:.1f} h"
        lat = "" if h.latency_ms is None else f"{h.latency_ms:.0f} ms"
        print(f"{h.status:13} {h.source:28} {lat:>8}  {age:12} {h.detail[:90]}")


_ = Health
