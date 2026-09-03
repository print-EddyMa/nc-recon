import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { useMapLibre } from "../lib/useMapLibre";
import {
  assessCommands,
  intersectsNC,
  inNC,
  NC_BBOX,
  loadCoverage,
  coverageToGeoJSON,
  pointCovered,
  type CatalogEvent,
  type EventCoverage,
} from "../lib/catalog";
import type { AssessTarget, IngestState } from "../lib/useAssess";
import type { EventConfig } from "../lib/types";

interface Props {
  areas: { event: EventConfig; area: EventConfig["areas"][number] }[];
  catalog: CatalogEvent[];
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onIngest: (t: AssessTarget) => void;
  onOpenArea: (areaId: string) => void;
  onBack: () => void;
}

const NC_CENTER: [number, number] = [-79.2, 35.55];

/** the app accent, resolved from the CSS custom property so the marker + the
 * coverage grid track the light / dark palette */
function accentCSS(): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  return v ? `rgb(${v})` : "#2563eb";
}

/** an NC-inset test on a coverage cell centre — the raw NC bbox grazes north
 * Georgia / east Tennessee, which used to pull the Assess view off toward
 * Atlanta whenever an event's footprint spilled across the line */
const cellInNC = ([w, s, e, n]: [number, number, number, number]) => {
  const cx = (w + e) / 2;
  const cy = (s + n) / 2;
  return cx >= -84.3 && cx <= -75.4 && cy >= 34.9 && cy <= 36.6;
};

/** rough great-circle distance in km, fine for ranking */
function distKm(a: [number, number], b: [number, number]) {
  const k = Math.PI / 180;
  const dLat = (b[1] - a[1]) * 111;
  const dLon = (b[0] - a[0]) * 111 * Math.cos(((a[1] + b[1]) / 2) * k);
  return Math.hypot(dLat, dLon);
}

function centerOf(ev: CatalogEvent): [number, number] | null {
  if (ev.center) return ev.center;
  if (ev.bbox) return [(ev.bbox[0] + ev.bbox[2]) / 2, (ev.bbox[1] + ev.bbox[3]) / 2];
  return null;
}

export default function Assess({
  areas,
  catalog,
  online,
  jobs,
  onIngest,
  onOpenArea,
  onBack,
}: Props) {
  const { containerRef, mapRef, ready, styleEpoch } = useMapLibre({ center: NC_CENTER, zoom: 6 });
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const [point, setPoint] = useState<[number, number] | null>(null);
  const [eventId, setEventId] = useState<string>("");
  const [name, setName] = useState<string>("");

  // NC-only catalogue subset
  const ncCatalog = useMemo(
    () => catalog.filter(intersectsNC).filter((e) => centerOf(e) !== null),
    [catalog],
  );

  // clamp the map to NC and wire click-to-drop once it's ready
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setMaxBounds([
      [NC_BBOX[0] - 0.6, NC_BBOX[1] - 0.6],
      [NC_BBOX[2] + 0.6, NC_BBOX[3] + 0.6],
    ]);
    const onClick = (e: maplibregl.MapMouseEvent) => {
      setPoint([e.lngLat.lng, e.lngLat.lat]);
    };
    map.on("click", onClick);
    return () => {
      map.off("click", onClick);
    };
  }, [ready, mapRef]);

  // reflect the dropped point as a marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!point) {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }
    if (!markerRef.current) {
      markerRef.current = new maplibregl.Marker({ color: accentCSS() });
    }
    markerRef.current.setLngLat(point).addTo(map);
  }, [point, mapRef]);

  const outside = point ? !inNC(point[0], point[1]) : false;

  // rank NC events by proximity to the dropped point, then imagery recency
  const ranked = useMemo(() => {
    if (!point) return ncCatalog;
    return [...ncCatalog].sort((a, b) => {
      const da = distKm(point, centerOf(a)!);
      const db = distKm(point, centerOf(b)!);
      return da - db;
    });
  }, [ncCatalog, point]);

  // the select is uncontrolled-ish: fall back to the nearest event until the
  // user picks one, without a state-sync effect
  const effEventId = ranked.some((e) => e.id === eventId) ? eventId : (ranked[0]?.id ?? "");
  const chosen = ncCatalog.find((e) => e.id === effEventId) ?? null;
  const effName =
    name.trim() ||
    (point ? `NC AOI ${point[1].toFixed(3)}, ${point[0].toFixed(3)}` : "NC AOI");
  const job = chosen ? jobs[chosen.id] : undefined;
  const running = job?.phase === "running";

  // assessable footprint of the chosen event (before + after imagery)
  const [coverage, setCoverage] = useState<EventCoverage | null>(null);
  useEffect(() => {
    setCoverage(null);
    if (!effEventId || online !== true) return;
    let cancelled = false;
    loadCoverage(effEventId).then((c) => !cancelled && setCoverage(c));
    return () => {
      cancelled = true;
    };
  }, [effEventId, online]);

  // draw the coverage cells + fit the map to the NC part of them
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const SRC = "assess-coverage";
    const gj = coverageToGeoJSON(coverage);
    const accent = accentCSS();
    const src = map.getSource(SRC) as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(gj);
      map.setPaintProperty(`${SRC}-fill`, "fill-color", accent);
      map.setPaintProperty(`${SRC}-line`, "line-color", accent);
    } else {
      map.addSource(SRC, { type: "geojson", data: gj });
      map.addLayer({
        id: `${SRC}-fill`,
        type: "fill",
        source: SRC,
        paint: { "fill-color": accent, "fill-opacity": 0.12 },
      });
      map.addLayer({
        id: `${SRC}-line`,
        type: "line",
        source: SRC,
        paint: { "line-color": accent, "line-opacity": 0.5, "line-width": 1 },
      });
    }
    // frame the NC portion of the coverage (fall back to the whole state so the
    // view never drifts across the line into GA / TN)
    if (!point) {
      const ncCells = (coverage?.cells ?? []).filter(cellInNC);
      if (ncCells.length) {
        let w = 180, s = 90, e = -180, n = -90;
        for (const [cw, cs, ce, cn] of ncCells) {
          w = Math.min(w, cw); s = Math.min(s, cs);
          e = Math.max(e, ce); n = Math.max(n, cn);
        }
        map.fitBounds([w, s, e, n], { padding: 90, duration: 400, maxZoom: 12 });
      } else {
        map.fitBounds(NC_BBOX, { padding: 40, duration: 400 });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coverage, ready, mapRef, styleEpoch]);

  const pointOk = pointCovered(coverage, point?.[0] ?? 0, point?.[1] ?? 0);
  const canAssess = !!point && !outside && !!chosen && !running;

  const commands =
    point && chosen
      ? assessCommands({ id: chosen.id, name: effName, center: point })
      : "";

  return (
    <div className="relative h-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Pick an area to assess" />

      <div className="absolute left-1/2 top-3 z-20 w-[min(720px,calc(100%-1.5rem))] -translate-x-1/2">
        <div className="panel flex items-start gap-2.5 px-3.5 py-2.5 text-xs leading-relaxed text-ink-dim">
          <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>
            <span className="text-ink">Assess an area.</span> Click anywhere in
            North Carolina to drop an AOI, pick the Maxar event that covers it, and
            run the damage pipeline for that footprint.{" "}
            <button onClick={onBack} className="pressable text-accent hover:underline">
              back to the monitor
            </button>
          </span>
        </div>
      </div>

      <aside className="absolute right-3 top-16 z-20 flex max-h-[calc(100%-5rem)] w-[22rem] max-w-[calc(100vw-1.5rem)] flex-col gap-3 overflow-y-auto lg:right-4">
        <section className="panel px-3.5 py-3.5">
          <h2 className="section-title mb-2.5">New assessment</h2>

          {!point && (
            <p className="text-2xs leading-relaxed text-ink-faint">
              Click the map to place an area of interest.
            </p>
          )}

          {point && outside && (
            <p className="rounded-sm bg-dmg2/15 px-2 py-1.5 text-2xs text-dmg1">
              That point is outside North Carolina. NC Recon only assesses NC areas.
            </p>
          )}

          {point && !outside && (
            <div className="space-y-2.5">
              <label className="block">
                <span className="cap mb-1 block">Area name</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value.slice(0, 80))}
                  placeholder={effName}
                  className="w-full rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink outline-none"
                />
              </label>

              <label className="block">
                <span className="cap mb-1 block">Maxar event covering this point</span>
                <select
                  value={effEventId}
                  onChange={(e) => setEventId(e.target.value)}
                  className="w-full rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink-dim outline-none"
                >
                  {ranked.length === 0 && <option value="">no NC-covering events in the catalogue</option>}
                  {ranked.map((e) => {
                    const c = centerOf(e)!;
                    return (
                      <option key={e.id} value={e.id}>
                        {e.name} · {distKm(point, c).toFixed(0)} km · {e.capture_dates?.[e.capture_dates.length - 1] ?? "-"}
                      </option>
                    );
                  })}
                </select>
              </label>

              {chosen && (
                <p className="text-2xs leading-relaxed text-ink-faint">
                  {chosen.n_captures} captures, {chosen.capture_dates?.[0]} →{" "}
                  {chosen.capture_dates?.[chosen.capture_dates.length - 1]}.
                  {coverage && ` ${coverage.n_cells} tiles with before + after imagery.`}
                </p>
              )}

              {coverage && !pointOk && (
                <p className="rounded-sm bg-dmg1/15 px-2 py-1.5 text-2xs text-dmg1">
                  This spot is outside the event&rsquo;s before/after coverage (shaded on
                  the map). Move the marker into a shaded tile.
                </p>
              )}

              {online ? (
                <button
                  disabled={!canAssess}
                  onClick={() =>
                    chosen &&
                    onIngest({
                      id: chosen.id,
                      name: effName,
                      center: centerOf(chosen),
                      point,
                      subtitle: "North Carolina",
                    })
                  }
                  className="pressable w-full rounded-md bg-accent py-2 text-xs font-semibold text-accent-ink disabled:opacity-40"
                >
                  {running ? job?.step ?? "assessing…" : "Assess this area"}
                </button>
              ) : (
                <div>
                  <p className="cap mb-1">no assessment service, run these</p>
                  <pre className="overflow-x-auto rounded-md border border-line bg-surface-2 p-2 text-[10px] leading-relaxed text-ink-dim">
                    {commands}
                  </pre>
                  <button
                    onClick={() => navigator.clipboard?.writeText(commands)}
                    className="pressable mt-1.5 rounded-md border border-line px-2 py-1 text-2xs text-ink-faint hover:text-ink"
                  >
                    copy commands
                  </button>
                </div>
              )}

              {job?.phase === "error" && (
                <p className="rounded-sm bg-dmg2/15 px-2 py-1.5 text-2xs text-dmg1">{job.error}</p>
              )}
            </div>
          )}

          <p className="mt-3 border-t border-line pt-2 text-2xs text-ink-faint">
            Service:{" "}
            {online == null ? "checking…" : online ? "connected" : "not connected"}
          </p>
        </section>

        <section className="panel px-3.5 py-3.5">
          <h2 className="section-title mb-2">Assessed NC areas</h2>
          {areas.length === 0 ? (
            <p className="text-2xs leading-relaxed text-ink-faint">
              None yet. Assessed areas show up here and on the damage map.
            </p>
          ) : (
            <ul className="space-y-1">
              {areas.map(({ event: ev, area: a }) => (
                <li key={a.id}>
                  <button
                    onClick={() => onOpenArea(a.id)}
                    className="pressable flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs text-ink-dim hover:bg-surface-2 hover:text-ink"
                  >
                    <span className="truncate">
                      {a.name} <span className="text-2xs text-ink-faint">· {ev.name}</span>
                    </span>
                    <span className="text-2xs text-ink-faint">open</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </div>
  );
}
