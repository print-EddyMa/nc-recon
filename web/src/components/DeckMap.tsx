import { useEffect, useMemo, useRef } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import { DAMAGE } from "../lib/damage";
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

  // attach the deck.gl overlay once
  useEffect(() => {
    if (!ready || !mapRef.current || overlayRef.current) return;
    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    mapRef.current.addControl(overlay as unknown as IControl);
    overlayRef.current = overlay;
    return () => {
      overlayRef.current = null;
    };
  }, [ready, mapRef]);

  // pre/post raster imagery sources (silently absent until tiles are generated)
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    for (const kind of ["pre", "post"] as const) {
      const sid = `imagery-${kind}`;
      if (!map.getSource(sid)) {
        map.addSource(sid, {
          type: "raster",
          tiles: [`${import.meta.env.BASE_URL}tiles/${area.id}/${kind}/{z}/{x}/{y}.jpg`],
          tileSize: 256,
          minzoom: 13,
          maxzoom: 17,
          attribution: "Maxar Open Data",
        });
        map.addLayer({
          id: sid,
          type: "raster",
          source: sid,
          paint: { "raster-opacity": 0, "raster-fade-duration": 200 },
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, area.id]);

  // drive imagery opacity from the assessment slider
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const vis = 1 - assessment; // imagery fades out as the 3-D model comes up
    for (const kind of ["pre", "post"] as const) {
      const id = `imagery-${kind}`;
      if (map.getLayer(id)) {
        const on = kind === imagery ? vis : 0;
        map.setPaintProperty(id, "raster-opacity", Math.max(0, Math.min(1, on)));
      }
    }
  }, [ready, assessment, imagery, mapRef]);

  // pitch follows the assessment so buildings read as 3-D near t=1
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const targetPitch = 12 + assessment * 46;
    if (Math.abs(map.getPitch() - targetPitch) > 0.5) {
      map.easeTo({ pitch: targetPitch, duration: 300 });
    }
  }, [ready, assessment, mapRef]);

  // camera fly-to on hotspot / building selection
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !flyTarget) return;
    map.flyTo({
      center: flyTarget.center,
      zoom: flyTarget.zoom ?? Math.max(map.getZoom(), 16.5),
      pitch: Math.max(map.getPitch(), 45),
      duration: 1400,
      essential: true,
    });
  }, [flyTarget, ready, mapRef]);

  const layers = useMemo(() => {
    if (!fc) return [];
    const t = assessment;
    return [
      new GeoJsonLayer({
        id: "buildings",
        data: fc.features as BuildingFeature[],
        pickable: true,
        stroked: true,
        filled: true,
        extruded: true,
        wireframe: false,
        lineWidthUnits: "pixels",
        getLineWidth: (f) => (f.properties.id === selectedId ? 2.5 : 0.5),
        getElevation: (f) => {
          const d = DAMAGE[f.properties.damage_class];
          const base = d.height * (0.15 + 0.85 * t);
          return f.properties.id === selectedId ? base + 12 : base;
        },
        getFillColor: (f) => {
          if (!filter.has(f.properties.damage_class)) return EMPTY_RGBA;
          const [r, g, b] = DAMAGE[f.properties.damage_class].rgb;
          const a = f.properties.id === selectedId ? 255 : 180 + Math.round(40 * t);
          return [r, g, b, a];
        },
        getLineColor: (f) =>
          f.properties.id === selectedId ? [63, 182, 196, 255] : [12, 16, 22, 140],
        material: {
          ambient: 0.55,
          diffuse: 0.6,
          shininess: 24,
          specularColor: [40, 55, 70],
        },
        transitions: {
          getElevation: { duration: 450 },
          getFillColor: { duration: 250 },
        },
        updateTriggers: {
          getFillColor: [selectedId, t, [...filter].join()],
          getElevation: [selectedId, t],
          getLineWidth: [selectedId],
        },
        onClick: (info: PickingInfo) => {
          const f = info.object as BuildingFeature | undefined;
          if (f) onSelect(f.properties.id, f.properties.centroid);
          else onSelect(null);
        },
      }),
    ];
  }, [fc, assessment, selectedId, filter, onSelect]);

  useEffect(() => {
    overlayRef.current?.setProps({ layers });
  }, [layers]);

  return <div ref={containerRef} className="absolute inset-0" aria-label={`Damage map for ${area.name}`} />;
}
