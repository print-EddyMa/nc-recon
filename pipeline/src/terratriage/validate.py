"""A6 sanity check: drop the output GeoJSON on a slippy map, coloured by damage
class, so a human can eyeball whether 'destroyed' clusters line up with the
river-adjacent parts of town that news coverage confirmed were devastated.
"""
from __future__ import annotations

import json

import folium

from .contract import COLORS, DAMAGE_CLASSES


def build_map(geojson_path: str, pre_path: str, post_path: str, out_html: str) -> str:
    with open(geojson_path) as fh:
        fc = json.load(fh)

    feats = fc["features"]
    lats = [f["properties"]["centroid"][1] for f in feats]
    lons = [f["properties"]["centroid"][0] for f in feats]
    center = [sum(lats) / len(lats), sum(lons) / len(lons)] if feats else [35.63, -82.18]

    m = folium.Map(location=center, zoom_start=15, tiles="CartoDB positron")

    def style(feat):
        c = COLORS[feat["properties"]["damage_class"]]
        return {"fillColor": c, "color": c, "weight": 1, "fillOpacity": 0.75}

    folium.GeoJson(
        fc, style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=["id", "damage_label", "confidence", "area_m2"]),
    ).add_to(m)

    counts = fc["properties"].get("counts", {})
    rows = "".join(
        f'<div><span style="display:inline-block;width:12px;height:12px;background:{h};'
        f'margin-right:6px"></span>{lbl} &mdash; {counts.get(str(i), 0)}</div>'
        for i, (_, lbl, h) in enumerate(DAMAGE_CLASSES)
    )
    legend = f"""
    <div style="position:fixed;bottom:24px;left:24px;z-index:9999;background:#fff;
      padding:12px 14px;border:1px solid #999;border-radius:6px;font:13px/1.5 system-ui">
      <b>{fc['properties'].get('area','')}</b> &mdash; {fc['properties'].get('n_buildings',0)} buildings<br>
      <span style="color:#666">{fc['properties'].get('model','')}</span><br>{rows}
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    m.save(out_html)
    print(f"[validate] wrote {out_html}")
    return out_html
