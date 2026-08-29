import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export type { Map as MLMap, IControl, RasterTileSource } from "maplibre-gl";

const BASE_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

interface Options {
  center: [number, number];
  zoom: number;
  pitch?: number;
  bearing?: number;
}

/** Creates a MapLibre map once, into the returned container ref. */
export function useMapLibre({ center, zoom, pitch = 0, bearing = 0 }: Options) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE,
      center,
      zoom,
      pitch,
      bearing,
      attributionControl: { compact: true },
      dragRotate: true,
      maxPitch: 75,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    map.on("load", () => setReady(true));
    map.on("error", (e) => {
      // tile 404s (e.g. imagery layer before tiles are generated) are non-fatal
      if (import.meta.env.DEV) console.debug("[maplibre]", e.error?.message ?? e);
    });
    mapRef.current = map;
    return () => {
      try {
        map.remove();
      } catch {
        /* init may have failed (no WebGL2) — nothing to tear down */
      }
      mapRef.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { containerRef, mapRef, ready };
}
