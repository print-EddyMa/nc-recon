/* The 3D view of an area: MapLibre's own fill-extrusion layers (so buildings
 * sit on the terrain when it is on), never a second engine.
 *
 *   known height    stories from the USACE inventory x 3 m, coloured by the
 *                   most likely FEMA level
 *   height unknown  a faint 0.5 m slab with a dashed outline, so a building
 *                   with no inventory height never passes for a one-storey
 *                   block
 *
 * Terrain is optional: AWS Terrain Tiles (terrarium encoding, keyless). If the
 * tiles fail to load, the buildings simply stay on flat ground. */
import { useEffect } from "react";
import type { MLMap } from "../../lib/useMapLibre";
import { prefersReducedMotion } from "../../lib/motion";
import { FEMA_HEX, NOT_ASSESSED_HEX, type OpsFeature } from "../../lib/ops";

export const STOREY_M = 3;
/** The terrain host as the server's Content Security Policy allows it
 * (pipeline ops/guard.py, connect-src and img-src). Change both together. */
export const TERRAIN_HOST = "https://s3.amazonaws.com/elevation-tiles-prod/";
const TERRAIN_URL = `${TERRAIN_HOST}terrarium/{z}/{x}/{y}.png`;
const SRC = "ops-3d";
const L_KNOWN = "ops-3d-known";
const L_UNKNOWN = "ops-3d-unknown";
const L_UNKNOWN_EDGE = "ops-3d-unknown-edge";
const L_SELECTED = "ops-3d-selected";
const DEM = "ops-terrain";
export const LAYERS_3D = [L_KNOWN, L_UNKNOWN];

const colour: unknown = [
  "match",
  ["get", "lvl"],
  ...Object.entries(FEMA_HEX).flat(),
  NOT_ASSESSED_HEX,
];

/** Building height from the inventory, or null when it is not known. */
export const heightOf = (f: OpsFeature): number | null => {
  const s = f.properties.stories;
  return typeof s === "number" && s > 0 ? s * STOREY_M : null;
};

export function useBuildings3D({
  map,
  ready,
  styleEpoch,
  on,
  terrain,
  features,
  selected,
  dark,
  onSelect,
  onHover,
}: {
  map: MLMap | null;
  ready: boolean;
  styleEpoch: number;
  on: boolean;
  terrain: boolean;
  features: OpsFeature[];
  selected: string | null;
  dark: boolean;
  onSelect: (id: string | null) => void;
  onHover: (h: { x: number; y: number; title: string; sub: string } | null) => void;
}) {
  // camera: tilt in when 3D turns on, back to flat when it turns off. No
  // auto-rotation, and no animation at all under reduced motion.
  useEffect(() => {
    if (!ready || !map) return;
    const duration = prefersReducedMotion() ? 0 : 600;
    if (on) map.easeTo({ pitch: 58, bearing: map.getBearing() || -18, duration });
    else map.easeTo({ pitch: 0, bearing: 0, duration });
  }, [on, ready, map]);

  // the basemap's own decorative building blocks would read as data in 3D
  useEffect(() => {
    if (!ready || !map) return;
    try {
      if (map.getLayer("nc-building-depth"))
        map.setLayoutProperty("nc-building-depth", "visibility", on ? "none" : "visible");
    } catch {
      /* style mid-swap */
    }
  }, [on, ready, map, styleEpoch]);

  // building layers
  useEffect(() => {
    if (!ready || !map || !on) return;
    const data: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: features
        .filter((f) => f.geometry.type === "Polygon")
        .map((f) => {
          const h = heightOf(f);
          return {
            type: "Feature",
            geometry: f.geometry,
            properties: {
              id: f.properties.ncr_id,
              lvl: f.properties.damage_level ?? "none",
              h: h ?? 0.5,
              known: h != null,
              stories: f.properties.stories ?? null,
            },
          };
        }),
    };
    try {
      map.addSource(SRC, { type: "geojson", data });
      // above the drawn basemap and imagery, below the labels that close the style
      const layers = map.getStyle().layers;
      let lastDrawn = -1;
      layers.forEach((l, i) => {
        if (l.type !== "symbol") lastDrawn = i;
      });
      const before = layers[lastDrawn + 1]?.id;
      map.addLayer(
        {
          id: L_UNKNOWN,
          type: "fill-extrusion",
          source: SRC,
          filter: ["!", ["get", "known"]],
          paint: {
            "fill-extrusion-color": colour as never,
            "fill-extrusion-height": 0.5,
            "fill-extrusion-opacity": 0.35,
          },
        },
        before,
      );
      map.addLayer(
        {
          id: L_UNKNOWN_EDGE,
          type: "line",
          source: SRC,
          filter: ["!", ["get", "known"]],
          paint: {
            "line-color": colour as never,
            "line-width": 1.5,
            "line-dasharray": [2, 1.5],
          },
        },
        before,
      );
      map.addLayer(
        {
          id: L_KNOWN,
          type: "fill-extrusion",
          source: SRC,
          filter: ["get", "known"],
          paint: {
            "fill-extrusion-color": colour as never,
            "fill-extrusion-height": ["get", "h"],
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.92,
            "fill-extrusion-vertical-gradient": true,
          },
        },
        before,
      );
      map.addLayer(
        {
          id: L_SELECTED,
          type: "line",
          source: SRC,
          filter: ["==", ["get", "id"], selected ?? ""],
          paint: { "line-color": dark ? "#ffffff" : "#0c0e10", "line-width": 3 },
        },
        before,
      );
    } catch {
      /* style mid-swap: the styleEpoch bump re-runs this */
    }
    return () => {
      try {
        for (const id of [L_SELECTED, L_KNOWN, L_UNKNOWN_EDGE, L_UNKNOWN]) if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(SRC)) map.removeSource(SRC);
      } catch {
        /* map torn down */
      }
    };
    // `selected` and `dark` are applied by the effect below without a rebuild
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on, ready, map, styleEpoch, features]);

  useEffect(() => {
    if (!ready || !map || !on) return;
    try {
      if (!map.getLayer(L_SELECTED)) return;
      map.setFilter(L_SELECTED, ["==", ["get", "id"], selected ?? ""]);
      map.setPaintProperty(L_SELECTED, "line-color", dark ? "#ffffff" : "#0c0e10");
    } catch {
      /* style mid-swap */
    }
  }, [selected, dark, on, ready, map, styleEpoch]);

  // pick and hover on the extrusions
  useEffect(() => {
    if (!ready || !map || !on) return;
    const click = (e: { features?: { properties: Record<string, unknown> }[] }) => {
      const id = e.features?.[0]?.properties?.id;
      if (typeof id === "string") onSelect(id);
    };
    const move = (e: { point: { x: number; y: number }; features?: { properties: Record<string, unknown> }[] }) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      map.getCanvas().style.cursor = "pointer";
      const lvl = String(p.lvl);
      const known = p.known === true || p.known === "true";
      onHover({
        x: e.point.x,
        y: e.point.y,
        title: lvl === "none" ? "Not assessed" : lvl.replace("_", " ").replace(/^./, (c) => c.toUpperCase()),
        sub: known ? `${p.stories} storey${Number(p.stories) > 1 ? "s" : ""} · ${Number(p.h)} m (inventory)` : "height unknown",
      });
    };
    const leave = () => {
      map.getCanvas().style.cursor = "";
      onHover(null);
    };
    for (const id of LAYERS_3D) {
      map.on("click", id, click as never);
      map.on("mousemove", id, move as never);
      map.on("mouseleave", id, leave);
    }
    return () => {
      for (const id of LAYERS_3D) {
        map.off("click", id, click as never);
        map.off("mousemove", id, move as never);
        map.off("mouseleave", id, leave);
      }
    };
  }, [on, ready, map, styleEpoch, onSelect, onHover]);

  // optional terrain
  useEffect(() => {
    if (!ready || !map || !on || !terrain) return;
    try {
      if (!map.getSource(DEM))
        map.addSource(DEM, {
          type: "raster-dem",
          tiles: [TERRAIN_URL],
          encoding: "terrarium",
          tileSize: 256,
          maxzoom: 15,
          attribution: "Terrain: Mapzen / AWS Terrain Tiles (USGS 3DEP and others)",
        });
      map.setTerrain({ source: DEM, exaggeration: 1 });
    } catch {
      /* style mid-swap, or tiles unavailable: stay flat */
    }
    return () => {
      try {
        map.setTerrain(null);
        if (map.getSource(DEM)) map.removeSource(DEM);
      } catch {
        /* torn down */
      }
    };
  }, [on, terrain, ready, map, styleEpoch]);
}
