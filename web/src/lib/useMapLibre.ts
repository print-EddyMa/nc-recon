import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { resolved } from "./theme";

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
}

/** Creates a MapLibre map once, into the returned container ref. The basemap
 * follows the light / dark theme (switched live via setStyle). */
export function useMapLibre({ center, zoom, pitch = 0, bearing = 0, interactive = true }: Options) {
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
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    }
    map.on("load", () => setReady(true));
    map.on("error", (e) => {
      if (import.meta.env.DEV) console.debug("[maplibre]", e.error?.message ?? e);
    });
    mapRef.current = map;

    // follow the theme
    let cur = resolved();
    const obs = new MutationObserver(() => {
      const next = resolved();
      if (next === cur) return;
      cur = next;
      map.setStyle(STYLE[next], { diff: false });
      map.once("styledata", () => setStyleEpoch((n) => n + 1));
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onSys = () => {
      const next = resolved();
      if (next === cur) return;
      cur = next;
      map.setStyle(STYLE[next], { diff: false });
      map.once("styledata", () => setStyleEpoch((n) => n + 1));
    };
    mq?.addEventListener?.("change", onSys);

    return () => {
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
