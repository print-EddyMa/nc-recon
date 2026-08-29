import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useMapLibre, type IControl, type RasterTileSource } from "../lib/useMapLibre";
import { DAMAGE } from "../lib/damage";
import { prefersReducedMotion } from "../lib/motion";
import type { AreaConfig, BuildingFeature, DamageCollection } from "../lib/types";

interface Props {
  area: AreaConfig;
  fc: DamageCollection | null;
  /** 0 = flat imagery/plan, 1 = full 3-D damage model */
  assessment: number;
  imagery: "pre" | "post";
  selectedId: string | null;
  filter: Set<number>;
  onSelect: (id: string | null, center?: [number, number]) => void;
  flyTarget: { center: [number, number]; zoom?: number; nonce: number } | null;
}

const EMPTY_RGBA: [number, number, number, number] = [0, 0, 0, 0];
type Hover = { x: number; y: number; f: BuildingFeature } | null;

export default function DeckMap({
  area,
  fc,
  assessment,
  imagery,
  selectedId,
  filter,
  onSelect,
  flyTarget,
}: Props) {
  const { containerRef, mapRef, ready } = useMapLibre({
    center: area.center,
    zoom: area.zoom,
    pitch: 0,
  });
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [hover, setHover] = useState<Hover>(null);
  const reduced = prefersReducedMotion();

  // --- imagery sources: add once, then just repoint tiles on area change ------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    for (const kind of ["pre", "post"] as const) {
      const sid = `imagery-${kind}`;
      const tiles = [`${import.meta.env.BASE_URL}tiles/${area.id}/${kind}/{z}/{x}/{y}.jpg`];
      const src = map.getSource(sid) as RasterTileSource | undefined;
      if (!src) {
        map.addSource(sid, {
          type: "raster", tiles, tileSize: 256, minzoom: 13, maxzoom: 17,
          attribution: "Maxar Open Data",
        });
        map.addLayer({
          id: sid, type: "raster", source: sid,
          paint: { "raster-opacity": 0, "raster-fade-duration": 200 },
        });
      } else if (typeof src.setTiles === "function") {
        src.setTiles(tiles);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, area.id]);

  // --- imagery opacity follows the slider ------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const vis = 1 - assessment;
    for (const kind of ["pre", "post"] as const) {
      const id = `imagery-${kind}`;
      if (map.getLayer(id)) {
        map.setPaintProperty(id, "raster-opacity", kind === imagery ? Math.max(0, Math.min(1, vis)) : 0);
      }
    }
  }, [ready, assessment, imagery, mapRef]);

  // --- pitch follows the slider --------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const targetPitch = 10 + assessment * 48;
    if (Math.abs(map.getPitch() - targetPitch) > 0.5) {
      map.easeTo({ pitch: targetPitch, duration: reduced ? 0 : 320 });
    }
  }, [ready, assessment, mapRef, reduced]);

  // --- recenter when the AOI changes (skip the initial mount) --------------
  const prevArea = useRef(area.id);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (area.id === prevArea.current) return;
    prevArea.current = area.id;
    setHover(null);
    map.flyTo({
      center: area.center, zoom: area.zoom, bearing: 0, pitch: map.getPitch(),
      duration: reduced ? 0 : 1200, essential: true,
    });
  }, [area.id, ready, mapRef, area.center, area.zoom, reduced]);

  // --- camera fly-to on hotspot / building selection ----------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !flyTarget) return;
    map.flyTo({
      center: flyTarget.center,
      zoom: flyTarget.zoom ?? Math.max(map.getZoom(), 16.5),
      pitch: Math.max(map.getPitch(), 45),
      duration: reduced ? 0 : 1400,
      essential: true,
    });
  }, [flyTarget, ready, mapRef, reduced]);

  const onHover = useCallback((info: PickingInfo) => {
    const f = info.object as BuildingFeature | undefined;
    setHover(f && info.x != null ? { x: info.x, y: info.y, f } : null);
  }, []);

  const layers = useMemo(() => {
    if (!fc) return [];
    const t = assessment;
    return [
      new GeoJsonLayer({
        id: "buildings",
        data: fc.features as BuildingFeature[],
        pickable: true,
        autoHighlight: true,
        highlightColor: [63, 182, 196, 90],
        stroked: true,
        filled: true,
        extruded: true,
        lineWidthUnits: "pixels",
        getLineWidth: (f) => (f.properties.id === selectedId ? 2.5 : 0.5),
        getElevation: (f) => {
          const base = DAMAGE[f.properties.damage_class].height * (0.04 + 0.96 * t);
          return f.properties.id === selectedId ? base + 12 : base;
        },
        getFillColor: (f) => {
          if (!filter.has(f.properties.damage_class)) return EMPTY_RGBA;
          const [r, g, b] = DAMAGE[f.properties.damage_class].rgb;
          const a = f.properties.id === selectedId ? 255 : 175 + Math.round(45 * t);
          return [r, g, b, a];
        },
        getLineColor: (f) =>
          f.properties.id === selectedId ? [63, 182, 196, 255] : [12, 16, 22, 140],
        material: { ambient: 0.55, diffuse: 0.6, shininess: 24, specularColor: [40, 55, 70] },
        transitions: reduced
          ? {}
          : { getElevation: { duration: 450 }, getFillColor: { duration: 250 } },
        updateTriggers: {
          getFillColor: [selectedId, t, [...filter].join()],
          getElevation: [selectedId, t],
          getLineWidth: [selectedId],
        },
        onClick: (info: PickingInfo) => {
          const f = info.object as BuildingFeature | undefined;
          onSelect(f ? f.properties.id : null, f?.properties.centroid);
        },
        onHover,
      }),
    ];
  }, [fc, assessment, selectedId, filter, onSelect, onHover, reduced]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({
        interleaved: false,
        layers: [],
        getTooltip: () => null,
      });
      mapRef.current.addControl(overlayRef.current as unknown as IControl);
    }
    overlayRef.current.setProps({ layers });
  }, [ready, mapRef, layers]);

  useEffect(
    () => () => {
      const map = mapRef.current;
      if (map && overlayRef.current) {
        try {
          map.removeControl(overlayRef.current as unknown as IControl);
        } catch {
          /* map already torn down */
        }
      }
      overlayRef.current = null;
    },
    [mapRef],
  );

  return (
    <div className="absolute inset-0">
      {/* maplibre-gl.css forces position:relative on this node, so size it explicitly */}
      <div ref={containerRef} className="h-full w-full" aria-label={`Damage map for ${area.name}`} />
      {hover && <HoverChip hover={hover} />}
    </div>
  );
}

function HoverChip({ hover }: { hover: NonNullable<Hover> }) {
  const d = DAMAGE[hover.f.properties.damage_class];
  return (
    <div
      className="pointer-events-none absolute z-30 -translate-x-1/2 -translate-y-[calc(100%+12px)] whitespace-nowrap rounded-sm border border-line bg-surface/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur"
      style={{ left: hover.x, top: hover.y }}
    >
      <span className="mr-1.5 inline-block h-2 w-2 rounded-[2px] align-middle" style={{ background: d.hex }} />
      <span className="font-medium" style={{ color: d.hex }}>{d.label}</span>
      <span className="tnum ml-2 text-ink-faint">{hover.f.properties.id}</span>
    </div>
  );
}
