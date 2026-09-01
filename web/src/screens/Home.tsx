import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { useMapLibre } from "../lib/useMapLibre";
import { liveRadarFrames, RADAR_ATTRIBUTION } from "../lib/radar";
import { prefersReducedMotion } from "../lib/motion";
import {
  ncFloodForecasts,
  ncAlerts,
  ncStreamflow,
  ncStormTracks,
  ncFires,
  ncFemaHistory,
  NC_SEV_COLOR,
  type NCResult,
  type NCPointFC,
  type NCGeomFC,
  type NCHistory,
} from "../lib/nc";
import { DAMAGE } from "../lib/damage";
import StatNumber from "../components/StatNumber";
import type { EventConfig } from "../lib/types";

interface Props {
  areas: { event: EventConfig; area: EventConfig["areas"][number] }[];
  online: boolean | null;
  onOpenArea: (areaId: string) => void;
  onOpenMonitor: () => void;
  onOpenAssess: () => void;
  onOpenAbout: () => void;
}

const rgb = (s: number) => {
  const [r, g, b] = NC_SEV_COLOR[Math.max(-1, Math.min(3, s))];
  return `rgb(${r},${g},${b})`;
};

/** a quiet contour backdrop for the hero: cartographic texture that reads as a
 * topo map. Always present, and the fallback if the WebGL map can't paint. */
function HeroBackdrop() {
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden bg-surface-2">
      <svg
        className="absolute inset-0 h-full w-full text-ink-dim"
        style={{ opacity: 0.22 }}
        preserveAspectRatio="xMidYMid slice"
        viewBox="0 0 800 420"
      >
        {Array.from({ length: 13 }).map((_, i) => (
          <path
            key={i}
            d={`M-40 ${40 + i * 34} C 160 ${8 + i * 34 + (i % 3) * 16}, 320 ${120 + i * 34}, 540 ${44 + i * 34} S 900 ${4 + i * 34}, 940 ${72 + i * 34}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={i % 5 === 0 ? 1.6 : 0.7}
            strokeOpacity={i % 5 === 0 ? 1 : 0.6}
          />
        ))}
      </svg>
    </div>
  );
}

const centroid = (geom: GeoJSON.Geometry): [number, number] | null => {
  const acc: [number, number] = [0, 0];
  let n = 0;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
      acc[0] += c[0];
      acc[1] += c[1];
      n++;
    } else if (Array.isArray(c)) c.forEach(walk);
  };
  if ("coordinates" in geom) walk((geom as { coordinates: unknown }).coordinates);
  return n ? [acc[0] / n, acc[1] / n] : null;
};

export default function Home({
  areas,
  online,
  onOpenArea,
  onOpenMonitor,
  onOpenAssess,
  onOpenAbout,
}: Props) {
  const [flood, setFlood] = useState<NCResult<NCPointFC> | null>(null);
  const [alerts, setAlerts] = useState<NCResult<NCGeomFC> | null>(null);
  const [flow, setFlow] = useState<NCResult<NCPointFC> | null>(null);
  const [storm, setStorm] = useState<NCResult<NCGeomFC> | null>(null);
  const [fire, setFire] = useState<NCResult<NCPointFC> | null>(null);
  const [history, setHistory] = useState<NCHistory | null>(null);

  useEffect(() => {
    ncFloodForecasts().then(setFlood);
    ncAlerts().then(setAlerts);
    ncStreamflow().then(setFlow);
    ncStormTracks().then(setStorm);
    ncFires().then(setFire);
    ncFemaHistory().then(setHistory);
  }, []);

  const floodElevated = useMemo(
    () => (flood?.data.features ?? []).filter((f) => f.properties.severity >= 1),
    [flood],
  );
  const severeAlerts = useMemo(
    () => (alerts?.data.features ?? []).filter((f) => f.properties.severity >= 3),
    [alerts],
  );
  const activeStorms = storm && !storm.disabled ? storm.data.features : [];
  const worst = Math.max(
    0,
    ...floodElevated.map((f) => f.properties.severity),
    ...(severeAlerts.length ? [3] : []),
    ...(activeStorms.length ? [3] : []),
  );
  const anyStale = [flood, alerts, flow].some((r) => r && !r.disabled && r.stale);

  // ---- hero map ---------------------------------------------------------- //
  const { containerRef, mapRef, ready, styleEpoch } = useMapLibre({
    center: [-79.35, 35.45],
    zoom: 5.85,
    interactive: false,
  });

  // points to plot on the hero. The normal/offline gauges (~800 on a calm day)
  // are drawn as faint texture; anything carrying a signal — a gauge at or above
  // action stage, an active fire, a real weather alert — is drawn bold so the
  // hero stays quiet when NC is quiet and lights up during an event.
  const heroPoints = useMemo<GeoJSON.FeatureCollection>(() => {
    const feats: GeoJSON.Feature[] = [];
    for (const f of flood?.data.features ?? []) {
      const sev = f.properties.severity;
      feats.push({
        type: "Feature",
        geometry: f.geometry,
        properties: sev >= 1 ? { sev, r: 4, hot: 1 } : { sev: 0, r: 1.8, hot: 0 },
      });
    }
    for (const f of flow?.data.features ?? [])
      feats.push({ type: "Feature", geometry: f.geometry, properties: { sev: 0, r: 1.4, hot: 0 } });
    for (const f of fire && !fire.disabled ? fire.data.features : [])
      feats.push({ type: "Feature", geometry: f.geometry, properties: { sev: 3, r: 4, hot: 1 } });
    for (const f of alerts?.data.features ?? []) {
      const c = centroid(f.geometry);
      if (c)
        feats.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: c },
          properties: { sev: Math.max(1, f.properties.severity), r: 5, hot: 1 },
        });
    }
    return { type: "FeatureCollection", features: feats };
  }, [flood, flow, fire, alerts]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.resize();
    const SRC = "hero-hz";
    const gj = heroPoints as maplibregl.GeoJSONSourceSpecification["data"];
    const src = map.getSource(SRC) as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(gj);
      return;
    }
    map.addSource(SRC, { type: "geojson", data: gj });
    // the halo is only for points that carry a signal, so a calm day has no wash
    map.addLayer({
      id: `${SRC}-glow`,
      type: "circle",
      source: SRC,
      paint: {
        "circle-radius": ["+", ["get", "r"], 7],
        "circle-blur": 1,
        "circle-opacity": ["case", ["==", ["get", "hot"], 1], 0.42, 0],
        "circle-color": [
          "match",
          ["get", "sev"],
          3, rgb(3), 2, rgb(2), 1, rgb(1), 0, rgb(0),
          /* default */ rgb(-1),
        ],
      },
    });
    map.addLayer({
      id: `${SRC}-dot`,
      type: "circle",
      source: SRC,
      paint: {
        "circle-radius": ["get", "r"],
        "circle-opacity": ["case", ["==", ["get", "hot"], 1], 0.95, 0.32],
        "circle-color": [
          "match",
          ["get", "sev"],
          3, rgb(3), 2, rgb(2), 1, rgb(1), 0, rgb(0),
          rgb(-1),
        ],
        "circle-stroke-width": ["case", ["==", ["get", "hot"], 1], 0.75, 0],
        "circle-stroke-color": "rgba(255,255,255,0.55)",
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, mapRef, heroPoints, styleEpoch]);

  // a slow, quiet NEXRAD radar loop behind the hero — real weather, barely there
  const heroRadar = useRef(liveRadarFrames());
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const SRC = "hero-radar";
    const frames = heroRadar.current;
    let i = frames.length - 1;
    const paint = () => {
      try {
        if (!mapRef.current || !map.getStyle()) return;
        const src = map.getSource(SRC) as maplibregl.RasterTileSource | undefined;
        if (src?.setTiles) src.setTiles([frames[i].tileUrl]);
        else if (!src) {
          map.addSource(SRC, {
            type: "raster",
            tiles: [frames[i].tileUrl],
            tileSize: 256,
            attribution: RADAR_ATTRIBUTION,
          });
          const below = map.getLayer("hero-hz-glow") ? "hero-hz-glow" : undefined;
          map.addLayer(
            { id: SRC, type: "raster", source: SRC, paint: { "raster-opacity": 0.2, "raster-fade-duration": 300 } },
            below,
          );
        }
      } catch {
        /* style mid-swap or map torn down */
      }
    };
    paint();
    if (prefersReducedMotion()) return;
    const t = window.setInterval(() => {
      if (document.hidden) return;
      i = (i + 1) % frames.length;
      paint();
    }, 2000);
    return () => window.clearInterval(t);
  }, [ready, mapRef, styleEpoch]);

  const priority =
    worst >= 1
      ? [
          floodElevated.length &&
            `${floodElevated.length} flood gauge${floodElevated.length > 1 ? "s" : ""} at or above action stage`,
          severeAlerts.length &&
            `${severeAlerts.length} severe weather alert${severeAlerts.length > 1 ? "s" : ""}`,
          activeStorms.length &&
            `${activeStorms.length} active Atlantic storm${activeStorms.length > 1 ? "s" : ""}`,
        ]
          .filter(Boolean)
          .join(", ")
      : "No active flood, storm, or severe-weather threats in North Carolina right now.";

  const tiles: { label: string; value: string; sev: number; sub: string }[] = [
    {
      label: "River flood forecast",
      value: flood ? `${floodElevated.length}` : "…",
      sev: floodElevated.length ? Math.max(...floodElevated.map((f) => f.properties.severity)) : 0,
      sub: flood
        ? floodElevated.length
          ? `of ${flood.data.features.length} NWPS gauges above action stage`
          : `${flood.data.features.length} NWPS gauges, all below flood stage`
        : "NOAA National Water Prediction Service",
    },
    {
      label: "Official alerts",
      value: alerts ? `${alerts.data.features.length}` : "…",
      sev: severeAlerts.length ? 3 : alerts?.data.features.length ? 1 : 0,
      sub: alerts
        ? alerts.data.features.length
          ? `active NWS watches and warnings, ${severeAlerts.length} severe`
          : "no active NWS alerts for the state"
        : "National Weather Service",
    },
    {
      label: "Streamflow",
      value: flow ? `${flow.data.features.length}` : "…",
      sev: 0,
      sub: flow
        ? `USGS streamgages reporting${flow.stale ? ", cached" : ""}`
        : "USGS instantaneous values",
    },
    {
      label: "Active storms",
      value: `${activeStorms.length}`,
      sev: activeStorms.length ? 3 : 0,
      sub: activeStorms.length
        ? activeStorms.map((f) => f.properties.title).join(", ")
        : "National Hurricane Center, Atlantic basin",
    },
    {
      label: "Active fire",
      value: fire && !fire.disabled ? `${fire.data.features.length}` : "off",
      sev: fire && !fire.disabled ? Math.max(0, ...fire.data.features.map((f) => f.properties.severity)) : 0,
      sub: fire?.disabled
        ? "add a free NASA FIRMS key to turn on"
        : fire
          ? "NASA FIRMS VIIRS, past 24 hours"
          : "NASA FIRMS",
    },
  ];

  return (
    <main id="main" className="h-full overflow-y-auto">
      {/* -------- hero -------- */}
      <section className="relative h-[44vh] min-h-[330px] w-full overflow-hidden">
        {/* topographic backdrop, always present (and the fallback if WebGL fails) */}
        <HeroBackdrop />
        {/* the map bleeds ~40px below the hero clip so its attribution bar sits
            out of view; the section's overflow-hidden trims it */}
        <div
          ref={containerRef}
          aria-hidden
          className={`absolute inset-x-0 -bottom-10 top-0 transition-opacity duration-700 ${
            ready ? "opacity-100" : "opacity-0"
          }`}
        />
        {/* scrim so overlaid text stays legible on either basemap */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(to top, rgb(var(--canvas)) 6%, rgb(var(--canvas) / 0.95) 30%, rgb(var(--canvas) / 0.62) 58%, rgb(var(--canvas) / 0.2) 88%, rgb(var(--canvas) / 0.08) 100%)",
          }}
        />
        <div className="relative flex h-full flex-col justify-end px-5 pb-6 md:px-10 md:pb-9">
          <p className="flex items-center gap-2 text-xs font-medium text-ink-dim">
            <span className="h-3 w-0.5 rounded-full bg-accent" />
            North Carolina
          </p>
          <h1 className="mt-2 max-w-2xl font-display text-3xl font-semibold leading-[1.08] text-ink md:text-[2.6rem]">
            Track the disaster from the first flood warning to the last damaged roof.
          </h1>
          <p className="mt-3 flex items-center gap-2 text-sm text-ink-dim">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: rgb(worst), boxShadow: `0 0 0 4px ${rgb(worst)}22` }}
            />
            {priority}
          </p>
          <div className="mt-5 flex flex-wrap gap-2.5">
            <button
              onClick={onOpenMonitor}
              className="pressable rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink"
            >
              Open the live map
            </button>
            <button
              onClick={onOpenAssess}
              className="pressable rounded-md border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-dim hover:text-ink"
            >
              Assess an area
            </button>
          </div>
        </div>
        <span className="absolute right-4 top-4 flex items-center gap-1.5 rounded-full border border-line bg-surface/80 px-2.5 py-1 text-2xs text-ink-faint backdrop-blur">
          <span className={`h-1.5 w-1.5 rounded-full ${anyStale ? "bg-dmg1" : "bg-accent"}`} />
          {anyStale ? "feeds cached" : "feeds live"}
        </span>
      </section>

      {/* -------- content -------- */}
      <div className="mx-auto w-full max-w-6xl px-5 pb-14 md:px-10">
        {/* status */}
        <div className="-mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {tiles.map((t, i) => (
            <button
              key={t.label}
              onClick={onOpenMonitor}
              className="pressable panel reveal px-4 py-3.5 text-left"
              style={{ animationDelay: `${i * 45}ms` }}
            >
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ background: rgb(t.sev) }} />
                <span className="text-2xs font-medium text-ink-dim">{t.label}</span>
              </div>
              <StatNumber
                value={t.value}
                className="mt-1.5 block text-[1.6rem] font-semibold leading-none text-ink"
              />
              <div className="mt-1.5 text-2xs leading-snug text-ink-faint">{t.sub}</div>
            </button>
          ))}
        </div>

        {/* damage assessments */}
        <div className="mt-11 flex items-baseline justify-between">
          <h2 className="font-display text-base font-semibold text-ink">Damage assessments</h2>
          <span className="text-2xs text-ink-faint">
            {online === false
              ? "assessment service offline"
              : `${areas.length} area${areas.length === 1 ? "" : "s"} assessed`}
          </span>
        </div>
        <p className="mt-1 max-w-2xl text-sm text-ink-dim">
          Point the pipeline at a North Carolina area with post-event Maxar imagery.
          It locates every building, rates the damage, and flags the uncertain calls
          for a person to check.
        </p>

        <div className="mt-4 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {areas.map(({ event, area }, i) => {
            const c = area.counts ?? {};
            const total = area.n_buildings ?? 0;
            const severe = (c["2"] ?? 0) + (c["3"] ?? 0);
            const pct = total ? Math.round((severe / total) * 100) : 0;
            return (
              <button
                key={area.id}
                onClick={() => onOpenArea(area.id)}
                className="pressable panel reveal flex flex-col gap-2.5 px-4 py-4 text-left"
                style={{ animationDelay: `${i * 45}ms` }}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-display text-[0.95rem] font-semibold text-ink">
                    {area.name}
                  </span>
                  <span className="text-2xs text-ink-faint">{event.name}</span>
                </div>
                <div className="flex h-1.5 overflow-hidden rounded-full bg-surface-2">
                  {(["0", "1", "2", "3"] as const).map((k) =>
                    c[k] ? (
                      <span
                        key={k}
                        style={{ width: `${(c[k] / total) * 100}%`, background: DAMAGE[+k].hex }}
                      />
                    ) : null,
                  )}
                </div>
                <div className="flex flex-wrap items-baseline gap-x-3.5 gap-y-1 text-2xs text-ink-faint">
                  <span>
                    <span className="font-semibold text-ink">{total.toLocaleString()}</span> buildings
                  </span>
                  <span>
                    <span className="font-semibold text-dmg2">{severe}</span> major or destroyed, {pct}%
                  </span>
                  {area.review && (
                    <span>
                      <span className="font-semibold text-dmg1">{area.review.total_review}</span> in review
                    </span>
                  )}
                </div>
                <div className="text-2xs text-ink-faint">
                  Maxar imagery {area.pre_date} to {area.post_date}
                </div>
              </button>
            );
          })}

          <button
            onClick={onOpenAssess}
            className="pressable flex flex-col items-center justify-center gap-2 rounded-[10px] border border-dashed border-line-strong px-4 py-7 text-center text-ink-dim hover:border-accent hover:text-ink"
          >
            <span className="grid h-9 w-9 place-items-center rounded-full border border-line text-lg">
              +
            </span>
            <span className="text-xs font-medium">Assess a new area</span>
            <span className="text-2xs text-ink-faint">
              {online === true ? "one click with the service running" : "shows the CLI steps"}
            </span>
          </button>
        </div>

        {/* history */}
        {history && history.total > 0 && (
          <div className="mt-11">
            <h2 className="font-display text-base font-semibold text-ink">
              What has happened here before
            </h2>
            <p className="mt-1.5 text-sm text-ink-dim">
              <span className="font-semibold text-ink">{history.total}</span> federally-declared
              disasters in North Carolina since {history.sinceYear}:{" "}
              {history.byType
                .slice(0, 4)
                .map((t) => `${t.count} ${t.type.toLowerCase()}`)
                .join(", ")}
              .
            </p>
            <ul className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1.5">
              {history.recent.map((d) => (
                <li key={d.disasterNumber} className="text-2xs text-ink-faint">
                  <span className="font-medium text-ink-dim">{d.declarationDate.slice(0, 4)}</span>{" "}
                  {d.declarationTitle}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-12 border-t border-line pt-5 text-2xs leading-relaxed text-ink-faint">
          Live feeds from NOAA NWPS, USGS NWIS, the National Weather Service, the National
          Hurricane Center, NASA FIRMS, NCDOT DriveNC, and OpenFEMA. Imagery from Maxar
          Open Data, building footprints from OpenStreetMap. Damage model: the xView2 CMU
          baseline classifier fused with a change-detection pass.{" "}
          <button onClick={onOpenAbout} className="pressable text-accent hover:underline">
            About TerraTriage
          </button>
        </div>
      </div>
    </main>
  );
}
