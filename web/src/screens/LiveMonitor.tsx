import { useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer } from "@deck.gl/layers";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import { prefersReducedMotion } from "../lib/motion";
import {
  usgsQuakes,
  gdacsEvents,
  firmsFires,
  sentinel1,
  type HazardResult,
  type HazardFC,
} from "../lib/hazards";
import HazardIcon from "../components/HazardIcon";
import AssessPanel from "../components/AssessPanel";
import type { CatalogEvent } from "../lib/catalog";
import type { IngestState } from "../lib/useAssess";
import type { EventConfig } from "../lib/types";

interface Props {
  events: EventConfig[];
  catalog: CatalogEvent[];
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onOpenEvent: (id: string) => void;
  onNavMap: () => void;
  onIngest: (ev: { id: string; name: string; center: [number, number] | null }) => void;
  onOpenAbout: () => void;
}

type LayerId = "quakes" | "multi" | "fires" | "radar";

const LAYER_COLOR: Record<LayerId, [number, number, number]> = {
  quakes: [63, 182, 196],
  multi: [232, 137, 74],
  fires: [209, 73, 91],
  radar: [139, 148, 163],
};

export default function LiveMonitor({
  events,
  catalog,
  online,
  jobs,
  onOpenEvent,
  onNavMap,
  onIngest,
  onOpenAbout,
}: Props) {
  const { containerRef, mapRef, ready } = useMapLibre({ center: [10, 25], zoom: 1.4 });
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const reduced = prefersReducedMotion();

  const [quakes, setQuakes] = useState<HazardResult | null>(null);
  const [multi, setMulti] = useState<HazardResult | null>(null);
  const [fires, setFires] = useState<HazardResult | null>(null);
  const radar = useMemo(() => sentinel1(), []);
  const [on, setOn] = useState<Record<LayerId, boolean>>({
    quakes: true,
    multi: true,
    fires: true,
    radar: false,
  });

  useEffect(() => {
    usgsQuakes().then(setQuakes);
    gdacsEvents().then(setMulti);
    firmsFires().then(setFires);
  }, []);

  const results: Record<LayerId, HazardResult | null> = {
    quakes,
    multi,
    fires,
    radar,
  };

  const layers = useMemo(() => {
    const out: ScatterplotLayer[] = [];
    for (const id of ["quakes", "multi", "fires"] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      out.push(
        new ScatterplotLayer({
          id: `hz-${id}`,
          data: res.features.features,
          pickable: true,
          stroked: true,
          filled: true,
          radiusUnits: "pixels",
          getPosition: (f: HazardFC["features"][number]) => f.geometry.coordinates as [number, number],
          getRadius: (f: HazardFC["features"][number]) => 3 + (f.properties.severity ?? 0) * 3.5,
          getFillColor: (f: HazardFC["features"][number]) => {
            const [r, g, b] = LAYER_COLOR[id];
            return [r, g, b, 90 + (f.properties.severity ?? 0) * 45];
          },
          getLineColor: LAYER_COLOR[id],
          lineWidthUnits: "pixels",
          getLineWidth: 1,
        }),
      );
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quakes, multi, fires, on]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({ interleaved: false, layers: [] });
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
          /* torn down */
        }
      }
      overlayRef.current = null;
    },
    [mapRef],
  );

  // ranked list across the enabled sources
  const items = useMemo(() => {
    const all: {
      id: string;
      title: string;
      source: string;
      coord: [number, number];
      severity: number;
      time: number | null;
    }[] = [];
    for (const id of ["quakes", "multi", "fires"] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      for (const f of res.features.features) {
        all.push({
          id: `${id}-${f.properties.id}`,
          title: f.properties.title,
          source: f.properties.source.toUpperCase(),
          coord: f.geometry.coordinates as [number, number],
          severity: f.properties.severity ?? 0,
          time: f.properties.time ?? null,
        });
      }
    }
    all.sort((a, b) => b.severity - a.severity || (b.time ?? 0) - (a.time ?? 0));
    return all.slice(0, 40);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quakes, multi, fires, on]);

  // one combined FeatureCollection of everything currently shown, for the
  // "assess a live hazard" cross-reference against the Maxar catalogue
  const allHazards = useMemo(() => {
    const feats = [];
    for (const id of ["quakes", "multi", "fires"] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      feats.push(...res.features.features);
    }
    return { type: "FeatureCollection" as const, features: feats };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quakes, multi, fires, on]);

  const flyTo = (coord: [number, number]) =>
    mapRef.current?.flyTo({
      center: coord,
      zoom: 6,
      duration: reduced ? 0 : 1200,
      essential: true,
    });

  const anyStale =
    quakes?.stale || multi?.stale || (fires && fires.stale && !fires.disabled);

  return (
    <div className="relative h-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Live global hazard monitor" />

      {/* detection-vs-assessment disclaimer — always visible */}
      <div className="absolute left-1/2 top-3 z-20 w-[min(700px,calc(100%-1.5rem))] -translate-x-1/2">
        <div className="panel flex items-start gap-2.5 px-3.5 py-2.5 text-xs leading-relaxed text-ink-dim">
          <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>
            <span className="text-ink">Live hazard detection.</span> These are hazards
            happening now. Building-level damage assessment is available only after a
            provider publishes post-event imagery, typically 24 to 72 hours after a
            major disaster. This layer is not a real-time damage claim.
            {anyStale && (
              <span className="ml-2 rounded-sm bg-dmg1/15 px-1.5 py-0.5 text-2xs text-dmg1">
                cached · offline
              </span>
            )}
          </span>
        </div>
      </div>

      {/* left: layers */}
      <aside className="absolute left-3 top-20 z-20 flex max-h-[calc(100%-6rem)] w-[17rem] max-w-[calc(100vw-1.5rem)] flex-col overflow-y-auto sm:left-4">
        <section className="panel px-3.5 py-3.5">
          <h2 className="section-title mb-2.5">Layers</h2>
          <ul className="space-y-2 text-xs">
            {(
              [
                ["quakes", "Earthquakes", quakes],
                ["multi", "Multi-hazard (GDACS)", multi],
                ["fires", "Active fires (FIRMS)", fires],
                ["radar", "Radar (Sentinel-1)", radar],
              ] as const
            ).map(([id, label, res]) => {
              const disabled = !res || res.disabled;
              return (
                <li key={id}>
                  <label
                    className={`flex items-start gap-2 ${
                      disabled ? "opacity-45" : "cursor-pointer"
                    }`}
                    title={res?.reason ?? undefined}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 accent-accent"
                      checked={on[id] && !disabled}
                      disabled={disabled}
                      onChange={() => setOn((s) => ({ ...s, [id]: !s[id] }))}
                    />
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 text-ink">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ background: `rgb(${LAYER_COLOR[id].join(",")})` }}
                        />
                        {label}
                      </span>
                      <span className="tnum block text-2xs text-ink-faint">
                        {res
                          ? res.disabled
                            ? "not available"
                            : `${res.features.features.length} · ${res.source}`
                          : "loading…"}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          {radar.reason && on.radar === false && (
            <p className="mt-2 border-t border-line pt-2 text-2xs leading-relaxed text-ink-faint">
              {radar.reason}
            </p>
          )}
        </section>

        <div className="mt-3">
          <AssessPanel
            events={events}
            catalog={catalog}
            online={online}
            jobs={jobs}
            hazards={allHazards}
            onOpenEvent={(id) => {
              onOpenEvent(id);
              onNavMap();
            }}
            onIngest={onIngest}
          />
        </div>
      </aside>

      {/* right: ranked list */}
      <aside className="absolute right-3 top-20 z-20 hidden max-h-[calc(100%-6rem)] w-[19rem] flex-col overflow-y-auto md:flex lg:right-4">
        <section className="panel px-3.5 py-3.5">
          <div className="mb-2.5 flex items-baseline justify-between">
            <h2 className="section-title">Active now</h2>
            <span className="cap">{items.length} events</span>
          </div>
          <ol className="space-y-0.5">
            {items.map((it) => (
              <li key={it.id}>
                <button
                  onClick={() => flyTo(it.coord)}
                  className="pressable flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-2"
                >
                  <span
                    className="mt-1 h-2 w-2 shrink-0 rounded-full"
                    style={{
                      background: `hsl(${20 - it.severity * 8} 70% ${60 - it.severity * 8}%)`,
                    }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs text-ink">{it.title}</span>
                    <span className="tnum block text-2xs text-ink-faint">
                      {it.source}
                      {it.time ? ` · ${new Date(it.time).toISOString().slice(0, 10)}` : ""}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {items.length === 0 && (
              <li className="px-2 py-3 text-xs text-ink-faint">
                No active hazards in the enabled layers.
              </li>
            )}
          </ol>
        </section>
      </aside>

      {/* bottom-left: jump straight to an already-assessed event, + About */}
      <div className="absolute bottom-3 left-3 z-20 hidden max-w-[calc(100vw-1.5rem)] flex-wrap items-center gap-2 sm:flex">
        {events.length > 0 && <span className="cap mr-0.5">assessed</span>}
        {events.map((e) => (
          <button
            key={e.id}
            onClick={() => {
              onOpenEvent(e.id);
              onNavMap();
            }}
            className="pressable panel flex items-center gap-1.5 px-2.5 py-1.5 text-2xs text-ink-dim hover:text-ink"
          >
            <HazardIcon hazard={e.hazard} size={12} className="text-ink-faint" />
            {e.name}
          </button>
        ))}
        <button
          onClick={onOpenAbout}
          className="pressable panel px-2.5 py-1.5 text-2xs text-ink-faint hover:text-ink"
        >
          About TerraTriage
        </button>
      </div>
    </div>
  );
}
