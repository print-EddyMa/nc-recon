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
import { useSettings } from "../lib/settings";
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
  const { settings, set } = useSettings();
  const [keyDraft, setKeyDraft] = useState("");
  const [selectedHazard, setSelectedHazard] = useState<{
    title: string;
    source: string;
    coord: [number, number];
  } | null>(null);
  const [on, setOn] = useState<Record<LayerId, boolean>>(() => {
    try {
      const s = JSON.parse(localStorage.getItem("terratriage:layers") || "");
      return { quakes: true, multi: true, fires: true, radar: false, ...s };
    } catch {
      return { quakes: true, multi: true, fires: true, radar: false };
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("terratriage:layers", JSON.stringify(on));
    } catch {
      /* private window */
    }
  }, [on]);

  // fetch on mount, then refresh every 5 min (these are live feeds)
  useEffect(() => {
    const pull = () => {
      usgsQuakes().then(setQuakes);
      gdacsEvents().then(setMulti);
    };
    pull();
    const t = window.setInterval(pull, 5 * 60_000);
    return () => window.clearInterval(t);
  }, []);
  // FIRMS re-fetches whenever the key changes
  useEffect(() => {
    setFires(null);
    firmsFires().then(setFires);
  }, [settings.firmsKey]);

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
      // quakes read as hollow rings, GDACS as filled discs, FIRMS as dense dots —
      // so the layers stay legible where they overlap, not just by hue
      const hollow = id === "quakes";
      const dense = id === "fires";
      out.push(
        new ScatterplotLayer({
          id: `hz-${id}`,
          data: res.features.features,
          pickable: true,
          stroked: true,
          filled: !hollow,
          radiusUnits: "pixels",
          getPosition: (f: HazardFC["features"][number]) => f.geometry.coordinates as [number, number],
          getRadius: (f: HazardFC["features"][number]) =>
            dense ? 2.5 : (hollow ? 4 : 3) + (f.properties.severity ?? 0) * 3.5,
          getFillColor: (f: HazardFC["features"][number]) => {
            const [r, g, b] = LAYER_COLOR[id];
            return [r, g, b, dense ? 150 : 80 + (f.properties.severity ?? 0) * 45];
          },
          getLineColor: (f: HazardFC["features"][number]) => {
            const [r, g, b] = LAYER_COLOR[id];
            return [r, g, b, hollow ? 180 + (f.properties.severity ?? 0) * 25 : 200];
          },
          lineWidthUnits: "pixels",
          getLineWidth: hollow ? 1.5 : 0.75,
          onClick: (info) => {
            const f = info.object as HazardFC["features"][number] | undefined;
            if (f) {
              flyTo(f.geometry.coordinates as [number, number]);
              setSelectedHazard({
                title: f.properties.title,
                source: f.properties.source,
                coord: f.geometry.coordinates as [number, number],
              });
            }
          },
        }),
      );
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quakes, multi, fires, on]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({
        interleaved: false,
        layers: [],
        getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
        getTooltip: (info) => {
          const f = info.object as HazardFC["features"][number] | undefined;
          if (!f) return null;
          return {
            text: f.properties.title,
            style: {
              background: "#161d26",
              border: "1px solid #28313d",
              color: "#ccd5df",
              fontSize: "11px",
              borderRadius: "4px",
              padding: "4px 7px",
            },
          };
        },
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

          {fires && fires.disabled && !settings.firmsKey && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                set("firmsKey", keyDraft.trim());
              }}
              className="mt-2.5 flex gap-1.5 border-t border-line pt-2.5"
            >
              <input
                value={keyDraft}
                onChange={(e) => setKeyDraft(e.target.value)}
                placeholder="NASA FIRMS key (optional)"
                className="min-w-0 flex-1 rounded-md border border-line bg-canvas px-2 py-1 text-2xs text-ink outline-none placeholder:text-ink-faint focus-visible:border-accent"
              />
              <button
                type="submit"
                disabled={!keyDraft.trim()}
                className="pressable rounded-md border border-line px-2 py-1 text-2xs text-ink-dim hover:text-ink disabled:opacity-40"
              >
                add
              </button>
            </form>
          )}
          {settings.firmsKey && (
            <button
              onClick={() => set("firmsKey", undefined)}
              className="pressable mt-2 border-t border-line pt-2 text-2xs text-ink-faint hover:text-ink"
            >
              remove FIRMS key
            </button>
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
                      background:
                        it.severity >= 3
                          ? "#d1495b"
                          : it.severity === 2
                            ? "#e8894a"
                            : it.severity === 1
                              ? "#f5d76e"
                              : "#5a7c86",
                    }}
                    title={["low", "moderate", "high", "severe"][it.severity] ?? "low"}
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

      {/* selected hazard — clicked on the map */}
      {selectedHazard && (
        <div className="absolute bottom-16 left-1/2 z-20 w-[min(420px,calc(100%-1.5rem))] -translate-x-1/2 sm:bottom-14">
          <div className="panel enter-pop px-3.5 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-ink">{selectedHazard.title}</div>
                <div className="tnum text-2xs text-ink-faint">
                  {selectedHazard.source.toUpperCase()} · {selectedHazard.coord[1].toFixed(2)},{" "}
                  {selectedHazard.coord[0].toFixed(2)}
                </div>
              </div>
              <button
                onClick={() => setSelectedHazard(null)}
                className="pressable -m-1 grid h-6 w-6 shrink-0 place-items-center rounded-md text-ink-faint hover:text-ink"
                aria-label="Dismiss"
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
                  <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            {(() => {
              const near = catalog
                .map((e) => {
                  if (!e.center) return null;
                  const dx = (e.center[0] - selectedHazard.coord[0]) * 111 *
                    Math.cos((selectedHazard.coord[1] * Math.PI) / 180);
                  const dy = (e.center[1] - selectedHazard.coord[1]) * 111;
                  return { e, km: Math.hypot(dx, dy) };
                })
                .filter((x): x is { e: (typeof catalog)[number]; km: number } => !!x && x.km < 250)
                .sort((a, b) => a.km - b.km)[0];
              if (!near)
                return (
                  <p className="mt-2 text-2xs leading-relaxed text-ink-faint">
                    No Maxar Open Data imagery within 250 km. Damage assessment isn't
                    possible here until a provider publishes post-event imagery.
                  </p>
                );
              const ing = events.some((x) => x.id === near.e.id);
              return (
                <div className="mt-2 flex items-center justify-between gap-2 border-t border-line pt-2 text-2xs">
                  <span className="text-ink-dim">
                    Imagery {near.km.toFixed(0)} km away ·{" "}
                    <span className="text-ink">{near.e.name}</span>
                  </span>
                  <button
                    onClick={() =>
                      ing
                        ? (onOpenEvent(near.e.id), onNavMap())
                        : onIngest({ id: near.e.id, name: near.e.name, center: near.e.center })
                    }
                    className="pressable shrink-0 rounded-md border border-accent/60 px-2 py-0.5 text-ink hover:bg-accent hover:text-[#05171a]"
                  >
                    {ing ? "Open" : "Ingest"}
                  </button>
                </div>
              );
            })()}
          </div>
        </div>
      )}

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
