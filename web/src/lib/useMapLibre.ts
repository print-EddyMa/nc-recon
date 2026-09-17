import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { resolved } from "./theme";
import { prefersReducedMotion } from "./motion";

export type { Map as MLMap, IControl, RasterTileSource } from "maplibre-gl";

const STYLE = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

interface Options {
  center: [number, number];
  zoom: number;
  pitch?: number;
  bearing?: number;
  /** false = a calm, non-interactive backdrop (used for the home hero) */
  interactive?: boolean;
  /**
   * Tilt in as the viewer zooms past street level, easing back to flat above
   * it - the same "flat region, tilted city block" read as Google Maps, and
   * the only way `nc-building-depth`'s extrusion is actually visible (at
   * pitch 0 an extruded block looks identical to a flat fill). Opt-in: only
   * screens that don't already own the camera's pitch (a before/after slider,
   * say) should set this.
   */
  autoTilt?: boolean;
}

const AUTO_TILT_MIN_ZOOM = 13;
const AUTO_TILT_MAX_ZOOM = 17;
const AUTO_TILT_MAX_PITCH = 55;
function pitchForZoom(z: number): number {
  if (z <= AUTO_TILT_MIN_ZOOM) return 0;
  if (z >= AUTO_TILT_MAX_ZOOM) return AUTO_TILT_MAX_PITCH;
  const t =
    (z - AUTO_TILT_MIN_ZOOM) / (AUTO_TILT_MAX_ZOOM - AUTO_TILT_MIN_ZOOM);
  return t * AUTO_TILT_MAX_PITCH;
}

/**
 * CARTO's positron/dark-matter styles carry a real OSM-derived `building`
 * source-layer but render it as flat 2-D fill (the app's deliberately quiet
 * cartography). Standing it up as a low fill-extrusion, city-block height
 * where no per-building height is in the tile, gives close-in zooms real
 * urban depth (closer to the "every block is a real place" read of Google
 * Maps) without touching the style's colour language or adding a dependency.
 * Not a height dataset, just texture, so it stays a flat, muted block.
 */
function addBuildingDepth(map: maplibregl.Map) {
  try {
    if (!map.getSource("carto") || map.getLayer("nc-building-depth")) return;
    const dark = resolved() === "dark";
    map.addLayer(
      {
        id: "nc-building-depth",
        type: "fill-extrusion",
        source: "carto",
        "source-layer": "building",
        minzoom: 14,
        paint: {
          "fill-extrusion-color": dark ? "#22242b" : "#e7e7e5",
          "fill-extrusion-height": ["coalesce", ["get", "render_height"], 8],
          "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
          "fill-extrusion-opacity": dark ? 0.75 : 0.65,
        },
      },
      map.getLayer("building-top") ? "building-top" : undefined,
    );
  } catch {
    /* style has no "carto" source / no "building" source-layer (unexpected
       style, or mid-swap) - the flat 2-D building fill still renders fine */
  }
}

/** Creates a MapLibre map once, into the returned container ref. The basemap
 * follows the light / dark theme (switched live via setStyle). */
export function useMapLibre({
  center,
  zoom,
  pitch = 0,
  bearing = 0,
  interactive = true,
  autoTilt = false,
}: Options) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [styleEpoch, setStyleEpoch] = useState(0);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: STYLE[resolved()],
        center,
        zoom,
        pitch,
        bearing,
        interactive,
        attributionControl: { compact: true },
        dragRotate: interactive,
        maxPitch: 75,
      });
    } catch (err) {
      // no WebGL2 (some VMs / remote desktops / locked-down browsers). Leave
      // `ready` false so callers fall back to their non-map view instead of the
      // whole screen crashing into the error boundary.
      if (import.meta.env.DEV) console.warn("[maplibre] init failed:", err);
      return;
    }
    if (interactive) {
      map.addControl(
        new maplibregl.NavigationControl({ visualizePitch: true }),
        "bottom-right",
      );
    }
    let tiltTimer: ReturnType<typeof setTimeout> | undefined;
    map.on("load", () => {
      addBuildingDepth(map);
      // MapLibre's `compact: true` still starts EXPANDED - "compact" only
      // means "has a collapse toggle", not "starts collapsed" (see
      // attribution_control.ts `_updateCompact`). On a wide map the expanded
      // text fits on one line; on a narrow one it wraps tall enough to break
      // layouts that clip a map's overflow (Home's hero). Start collapsed.
      map
        .getContainer()
        .querySelector(".maplibregl-ctrl-attrib")
        ?.classList.remove("maplibregl-compact-show");
      setReady(true);
    });
    if (autoTilt && interactive) {
      // debounced + `stop()`-guarded: a burst of zoomend events (fast scroll,
      // repeated zoom-button clicks) firing `easeTo` back-to-back can hit a
      // MapLibre GL internal animation-frame race ("this._onEaseFrame is not
      // a function") if a new ease starts before the previous one's torn
      // down. `stop()` cleanly cancels any in-flight camera animation first.
      map.on("zoomend", () => {
        clearTimeout(tiltTimer);
        tiltTimer = setTimeout(() => {
          try {
            map.stop();
            map.easeTo({
              pitch: pitchForZoom(map.getZoom()),
              duration: prefersReducedMotion() ? 0 : 400,
            });
          } catch {
            /* mid-teardown */
          }
        }, 120);
      });
    }
    map.on("error", (e) => {
      if (import.meta.env.DEV)
        console.debug("[maplibre]", e.error?.message ?? e);
    });
    mapRef.current = map;

    // follow the theme
    let cur = resolved();
    const obs = new MutationObserver(() => {
      const next = resolved();
      if (next === cur) return;
      cur = next;
      map.setStyle(STYLE[next], { diff: false });
      map.once("styledata", () => {
        addBuildingDepth(map);
        setStyleEpoch((n) => n + 1);
      });
    });
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onSys = () => {
      const next = resolved();
      if (next === cur) return;
      cur = next;
      map.setStyle(STYLE[next], { diff: false });
      map.once("styledata", () => {
        addBuildingDepth(map);
        setStyleEpoch((n) => n + 1);
      });
    };
    mq?.addEventListener?.("change", onSys);

    return () => {
      clearTimeout(tiltTimer);
      obs.disconnect();
      mq?.removeEventListener?.("change", onSys);
      try {
        map.remove();
      } catch {
        /* init may have failed (no WebGL2) */
      }
      mapRef.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // styleEpoch bumps after a live basemap swap so consumers can re-add overlays
  return { containerRef, mapRef, ready, styleEpoch };
}
