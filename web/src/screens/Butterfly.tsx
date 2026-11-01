import { useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { LineLayer, PathLayer, ScatterplotLayer, SolidPolygonLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import { resolved as resolvedTheme } from "../lib/theme";
import StatTile from "../components/ui/StatTile";
import {
  loadButterflyCase,
  loadButterflyIndex,
  sensRGB,
  ivtRGB,
  tempRGB,
  runRGB,
  css,
  ring,
  SENS_STOPS,
  IVT_STOPS,
  type ButterflyCase,
  type ButterflyIndexEntry,
  type ButterflyRun,
  type Cell,
} from "../lib/butterfly";

interface Props {
  onOpenAbout: () => void;
}

type View = "sensitivity" | "nudge" | "moisture";

const VIEW_META: Record<View, { label: string; blurb: string }> = {
  sensitivity: {
    label: "Where to push",
    blurb:
      "How strongly the storm's impact on the target depends on each column of the atmosphere at the start of the forecast. Darker = a small change there matters more.",
  },
  nudge: {
    label: "The nudge",
    blurb:
      "The smallest change to the starting weather (temperature shaded, wind arrows) that most reduces the impact, kept outside the storm's own no-touch zone.",
  },
  moisture: {
    label: "Moisture",
    blurb:
      "The forecast moisture transport for the selected run, the fuel for Helene's flood-producing rain, at the hour the core reached the southern Appalachians.",
  },
};

const utc = (iso: string) => {
  const d = new Date(iso.length === 16 ? `${iso}:00Z` : iso);
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} ${String(d.getUTCHours()).padStart(2, "0")}Z`;
};
const pct = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x).toFixed(Math.abs(x) < 10 ? 1 : 0)}%`;
type LonLat = [number, number];
const cellPoly = (c: Cell): LonLat[] => [
  [c[0], c[1]],
  [c[2], c[1]],
  [c[2], c[3]],
  [c[0], c[3]],
];

type Hover = { kind: "cell"; text: string } | { kind: "track"; text: string };

export default function Butterfly({ onOpenAbout }: Props) {
  const { containerRef, mapRef, ready, styleEpoch } = useMapLibre({
    center: [-83.5, 29.5],
    zoom: 3.7,
  });
  const overlayRef = useRef<MapboxOverlay | null>(null);

  const [index, setIndex] = useState<ButterflyIndexEntry[] | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [doc, setDoc] = useState<ButterflyCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("sensitivity");
  const [level, setLevel] = useState(0);
  const [runId, setRunId] = useState("away_1");
  const [showObserved, setShowObserved] = useState(true);
  const [showAllRuns, setShowAllRuns] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);
  // phones: the controls fold away so the map is visible (md+ always shows them)
  const [controlsOpen, setControlsOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    loadButterflyIndex()
      .then((idx) => {
        if (!alive) return;
        setIndex(idx);
        setCaseId((c) => c ?? idx[0]?.id ?? null);
      })
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!caseId) return;
    let alive = true;
    loadButterflyCase(caseId)
      .then((d) => alive && setDoc(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [caseId]);

  const runs = useMemo(() => doc?.runs ?? [], [doc]);
  const baseline = runs.find((r) => r.s === 0) ?? null;
  const run: ButterflyRun | null = runs.find((r) => r.id === runId) ?? baseline;
  const ivtMax = useMemo(
    () => Math.max(1, ...runs.flatMap((r) => r.impact.cells.map((c) => c[4]))),
    [runs],
  );
  const nudgeLevel = doc?.nudge.levels[level] ?? null;

  // frame the Gulf -> southern Appalachians between the two docked panels
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const wide = map.getContainer().clientWidth >= 768;
    try {
      map.fitBounds(
        [
          [-99, 14],
          [-66, 40],
        ],
        {
          padding: wide ? { left: 340, right: 350, top: 30, bottom: 30 } : { left: 20, right: 20, top: 220, bottom: 80 },
          duration: 0,
        },
      );
    } catch {
      /* container not measured yet */
    }
  }, [ready, mapRef]);

  // ---- deck layers ------------------------------------------------------------ //
  const layers = useMemo(() => {
    if (!doc) return [] as Layer[];
    const dark = resolvedTheme() === "dark";
    const ink: [number, number, number] = dark ? [233, 234, 232] : [28, 29, 33];
    const out: Layer[] = [];

    if (view === "sensitivity") {
      out.push(
        new SolidPolygonLayer<Cell>({
          id: "sens",
          data: doc.sensitivity.cells,
          getPolygon: cellPoly,
          getFillColor: (c) => [...sensRGB(c[4]), Math.round(60 + 150 * Math.sqrt(c[4]))],
          pickable: true,
        }),
      );
    } else if (view === "nudge" && nudgeLevel) {
      const m = nudgeLevel.max_abs_T || 1;
      const k = 2.6 / (nudgeLevel.max_wind || 1); // longest arrow ~2.6 deg
      out.push(
        new SolidPolygonLayer<Cell>({
          id: "nudge-T",
          data: nudgeLevel.cells,
          getPolygon: cellPoly,
          getFillColor: (c) => [...tempRGB(c[4] / m), 170],
          pickable: true,
        }),
        new LineLayer<[number, number, number, number]>({
          id: "nudge-wind",
          data: nudgeLevel.arrows,
          getSourcePosition: (a) => [a[0], a[1]],
          getTargetPosition: (a) => [a[0] + a[2] * k, a[1] + a[3] * k],
          getColor: [...ink, 200],
          getWidth: 1.4,
          widthUnits: "pixels",
        }),
        new ScatterplotLayer<[number, number, number, number]>({
          id: "nudge-wind-head",
          data: nudgeLevel.arrows,
          getPosition: (a) => [a[0] + a[2] * k, a[1] + a[3] * k],
          getRadius: 2.2,
          radiusUnits: "pixels",
          getFillColor: [...ink, 220],
        }),
      );
    } else if (view === "moisture" && run) {
      out.push(
        new SolidPolygonLayer<Cell>({
          id: `ivt-${run.id}`,
          data: run.impact.cells,
          getPolygon: cellPoly,
          getFillColor: (c) => [...ivtRGB(c[4] / ivtMax), 175],
          pickable: true,
        }),
      );
    }

    // the target region and the storm's no-touch zone
    const t = doc.case.target;
    out.push(
      new PathLayer({
        id: "target",
        data: [ring(t.lat, t.lon, t.radius_km)],
        getPath: (p: [number, number][]) => p,
        getColor: [...ink, 230],
        getWidth: 2,
        widthUnits: "pixels",
      }),
      new PathLayer({
        id: "keepout",
        data: [ring(doc.case.storm0[0], doc.case.storm0[1], doc.case.keep_out_km)],
        getPath: (p: [number, number][]) => p,
        getColor: [...ink, 90],
        getWidth: 1,
        widthUnits: "pixels",
      }),
    );

    // tracks: model runs (selected on top), then the observed best track
    const shown = (showAllRuns ? runs : runs.filter((r) => r.id === run?.id || r.s === 0)).slice();
    shown.sort((a) => (a.id === run?.id ? 1 : -1));
    out.push(
      new PathLayer<ButterflyRun>({
        id: "runs",
        data: shown,
        getPath: (r) => r.track.map((p): LonLat => [p.lon, p.lat]),
        getColor: (r) => [...runRGB(r, dark), r.id === run?.id ? 255 : 110],
        getWidth: (r) => (r.id === run?.id ? 3.5 : 1.8),
        widthUnits: "pixels",
        jointRounded: true,
        capRounded: true,
        pickable: true,
        updateTriggers: { getColor: run?.id, getWidth: run?.id },
      }),
    );
    if (run) {
      out.push(
        new ScatterplotLayer({
          id: "run-pts",
          data: run.track.map((p) => ({ ...p, run: run.label })),
          getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
          getRadius: 3.5,
          radiusUnits: "pixels",
          getFillColor: [...runRGB(run, dark), 255],
          getLineColor: dark ? [23, 25, 30] : [255, 255, 255],
          lineWidthMinPixels: 1,
          stroked: true,
          pickable: true,
        }),
      );
    }
    if (showObserved) {
      out.push(
        new PathLayer({
          id: "best",
          data: [doc.best_track],
          getPath: (bt: ButterflyCase["best_track"]) => bt.map((p): LonLat => [p.lon, p.lat]),
          getColor: [...ink, 255],
          getWidth: 2.5,
          widthUnits: "pixels",
          jointRounded: true,
        }),
        new ScatterplotLayer({
          id: "best-pts",
          data: doc.best_track.map((p) => ({ ...p, observed: true })),
          getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
          getRadius: 3,
          radiusUnits: "pixels",
          getFillColor: [...ink, 255],
          pickable: true,
        }),
      );
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, view, level, run?.id, showObserved, showAllRuns, ivtMax, styleEpoch]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({
        interleaved: false,
        layers: [],
        getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
        getTooltip: (info: PickingInfo) => {
          const h = describe(info);
          if (!h) return null;
          const cs = getComputedStyle(document.documentElement);
          return {
            text: h.text,
            style: {
              background: `rgb(${cs.getPropertyValue("--surface")})`,
              border: `1px solid rgb(${cs.getPropertyValue("--line")})`,
              color: `rgb(${cs.getPropertyValue("--ink-dim")})`,
              fontSize: "11px",
              borderRadius: "6px",
              padding: "4px 7px",
            },
          };
        },
      });
      mapRef.current.addControl(overlayRef.current as unknown as IControl);
    }
    overlayRef.current.setProps({ layers });
  }, [ready, mapRef, layers, styleEpoch]);

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

  // ---- empty / error states ------------------------------------------------------ //
  if (error && !doc) {
    return (
      <div className="mx-auto grid h-full max-w-md place-items-center px-6 text-center">
        <div>
          <div className="section-title mb-2">No storm-sensitivity runs yet</div>
          <p className="text-sm text-ink-dim">
            Butterfly runs are computed offline by the pipeline (NeuralGCM from ERA5), then exported here. Run
          </p>
          <code className="tnum mt-2 inline-block rounded bg-surface-2 px-1.5 py-0.5 text-xs">
            python -m butterfly.run all --case helene
          </code>
          <p className="mt-3 text-2xs text-ink-faint">{error}</p>
        </div>
      </div>
    );
  }

  const dark = resolvedTheme() === "dark";
  const ae = doc?.case.analysis_error;
  const away = runs.filter((r) => r.s > 0).sort((a, b) => a.s - b.s);
  const toward = runs.find((r) => r.s < 0);
  const barMax = Math.max(
    1,
    ...runs.map((r) => Math.max(Math.abs(r.change_pct), Math.abs(r.linear_change_pct ?? 0))),
  );
  const hasLinear = runs.some((r) => r.linear_change_pct != null);

  const resultPanels = doc && (
    <>
      <section className="panel px-4 py-3.5">
        <h2 className="section-title mb-2.5">Result</h2>
        <div className="grid grid-cols-2 gap-x-4 gap-y-3.5">
          <StatTile
            label="Moisture into WNC"
            value={run ? pct(run.change_pct) : "-"}
            tone={run && run.change_pct > 0 ? "severe" : "neutral"}
            sub={run?.s ? `selected run vs no nudge` : "pick a nudged run"}
          />
          <StatTile
            label="Nudge peak"
            value={run?.peak ? `${run.peak.T_K.toFixed(2)} K` : "-"}
            sub={
              run?.peak
                ? `${run.peak.wind_ms.toFixed(2)} m/s · humidity ${run.peak.q_gkg < 0.01 ? "negligible" : `${run.peak.q_gkg.toFixed(2)} g/kg`}`
                : "no nudge"
            }
          />
          <StatTile
            label="Hindcast track error"
            value={doc.skill.mean_track_err_km != null ? `${doc.skill.mean_track_err_km} km` : "-"}
            sub="mean over 78 h vs NOAA best track"
          />
          <StatTile
            label="Nudge cap (1×)"
            value={ae ? `${ae.T_K} K` : "-"}
            sub={
              ae
                ? `${ae.wind_ms} m/s · humidity ≤${ae.q_relative ? ` ${Math.round(ae.q_relative * 100)}% of local,` : ""} ${ae.q_gkg} g/kg · rough analysis error`
                : undefined
            }
          />
        </div>
      </section>

      <section className="panel px-4 py-3.5">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="section-title">Effect by nudge size</h2>
          <span className="cap">full forecasts</span>
        </div>
        <ul className="space-y-2">
          {[...(toward ? [toward] : []), ...(baseline ? [baseline] : []), ...away].map((r) => (
            <li key={r.id}>
              <button
                onClick={() => setRunId(r.id)}
                className={`pressable w-full text-left ${r.id === run?.id ? "" : "opacity-80 hover:opacity-100"}`}
              >
                <div className="flex items-baseline justify-between text-2xs">
                  <span className={r.id === run?.id ? "text-ink" : "text-ink-dim"}>{shortLabel(r)}</span>
                  <span className="tnum text-ink">{r.s === 0 ? "baseline" : pct(r.change_pct)}</span>
                </div>
                <div className="relative mt-1 h-1.5 rounded-sm bg-surface-2">
                  <span className="absolute left-1/2 top-[-2px] h-[10px] w-px bg-line-strong" />
                  {r.s !== 0 && (
                    <span
                      className="absolute top-0 h-1.5 rounded-sm"
                      style={{
                        background: css(runRGB(r, dark)),
                        width: `${(50 * Math.abs(r.change_pct)) / barMax}%`,
                        left: r.change_pct < 0 ? `${50 - (50 * Math.abs(r.change_pct)) / barMax}%` : "50%",
                      }}
                    />
                  )}
                  {r.linear_change_pct != null && (
                    <span
                      title={`gradient predicted ${pct(r.linear_change_pct)}`}
                      className="absolute top-[-3px] h-[12px] w-[2px] rounded-full bg-ink"
                      style={{ left: `calc(${50 + (50 * r.linear_change_pct) / barMax}% - 1px)` }}
                    />
                  )}
                </div>
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-2.5 text-2xs leading-relaxed text-ink-faint">
          Change in {doc.case.objective_label}, averaged over forecast hours{" "}
          {doc.case.window_hours.join(", ")}. Every bar is a full nonlinear NeuralGCM forecast.
          {hasLinear && (
            <>
              {" "}
              <span className="inline-block h-2.5 w-[2px] translate-y-0.5 rounded-full bg-ink" /> marks what the
              gradient alone predicted: where tick and bar disagree, the linear sensitivity stops being trustworthy.
            </>
          )}
        </p>
      </section>

      <section className="panel px-4 py-3.5">
        <h2 className="section-title mb-2">Which altitude matters</h2>
        <Profile levels={doc.sensitivity.levels_hpa} profile={doc.sensitivity.profile} />
      </section>

      <section className="panel px-4 py-3.5">
        <button
          onClick={() => setDetailsOpen((v) => !v)}
          aria-expanded={detailsOpen}
          className="pressable flex w-full items-center justify-between"
        >
          <span className="section-title">How it works, and what it isn&rsquo;t</span>
          <span className="cap">{detailsOpen ? "hide" : "show"}</span>
        </button>
        {detailsOpen && (
          <div className="mt-2 space-y-2 text-2xs leading-relaxed text-ink-dim">
            <p>
              <span className="text-ink">1 · Start from reality.</span> The real ERA5 state of the atmosphere at{" "}
              {utc(doc.case.init)} goes into {doc.case.model}, Google&rsquo;s differentiable weather model.
            </p>
            <p>
              <span className="text-ink">2 · Ask the model why.</span> Backpropagating the forecast impact on{" "}
              {doc.case.target.label} to the starting weather gives the sensitivity map (an adjoint, the same idea as
              ECMWF&rsquo;s singular vectors).
            </p>
            <p>
              <span className="text-ink">3 · Check the answer.</span> The steepest nudge, each field capped at a
              rough analysis error, confined to the troposphere
              {doc.case.nudge_levels_hpa ? ` (${doc.case.nudge_levels_hpa[1]}–${doc.case.nudge_levels_hpa[0]} hPa)` : ""}{" "}
              and kept {doc.case.keep_out_km} km from the storm, is put back in and the whole forecast re-run. The bars
              are those re-runs; the ticks are the gradient&rsquo;s own prediction.
            </p>
            <p className="border-t border-line pt-2">
              <span className="text-ink">Not a weather-control tool.</span> It shows how sensitive a forecast is,
              which is how forecasters decide where extra observations (aircraft, dropsondes) would help most.
            </p>
            <p>
              <span className="text-ink">Limits.</span> 2.8° model (~300 km): the storm&rsquo;s core and its
              intensity aren&rsquo;t resolved, only its track and large-scale moisture. Model storm positions carry
              ~±150 km of grid noise, more after landfall, and the model&rsquo;s Helene runs slow: it is{" "}
              {doc.skill.window_track_err_km.filter((x) => x != null).slice(-2).join("–")} km from the observed
              storm by +72–78 h. The nudge is judged by the same
              model that designed it; an independent physics model (WRF) is the next check. One storm is a case
              study, not a statistic.
            </p>
            <p className="text-ink-faint">
              Data: ERA5 (ECMWF / Copernicus) via Google ARCO-ERA5 · NOAA IBTrACS · NeuralGCM (Kochkov et al.,
              Nature 2024). Computed {doc.generated}.
            </p>
            <button onClick={onOpenAbout} className="pressable text-accent hover:underline">
              About NC Recon
            </button>
          </div>
        )}
      </section>
    </>
  );

  return (
    <div className="relative h-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Storm sensitivity map" />

      <aside className="absolute left-3 top-3 z-20 flex max-h-[calc(100%-1.5rem)] w-[19rem] max-w-[calc(100vw-1.5rem)] flex-col gap-3 overflow-y-auto sm:left-4 sm:top-4">
        <section className="panel px-4 py-3.5">
          <div className="eyebrow">Butterfly · storm sensitivity</div>
          <div className="mt-1 flex items-baseline justify-between gap-2">
            <h1 className="font-display text-lg font-semibold leading-tight text-ink">
              {doc?.case.name ?? "Loading…"}
            </h1>
            {index && index.length > 1 && (
              <select
                value={caseId ?? ""}
                onChange={(e) => {
                  setDoc(null);
                  setCaseId(e.target.value);
                }}
                className="rounded-sm border border-line bg-surface-2 px-1.5 py-0.5 text-2xs text-ink"
                aria-label="Storm"
              >
                {index.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          <p className="mt-1.5 hidden text-xs leading-relaxed text-ink-dim sm:block">
            {doc
              ? `Which small differences in the weather ${Math.round(doc.case.window_hours[0] / 24)} days earlier would have changed how much moisture Helene drove into ${doc.case.target.label.replace(/\s*\(.*\)$/, "")}?`
              : "Loading the run…"}
          </p>
          {doc && (
            <p className="mt-1.5 text-2xs text-ink-faint">
              {doc.case.model} · ERA5 start {utc(doc.case.init)}
            </p>
          )}
          {doc && (
            <button
              onClick={() => setControlsOpen((v) => !v)}
              aria-expanded={controlsOpen}
              className="pressable mt-2 text-2xs font-medium text-accent md:hidden"
            >
              {controlsOpen ? "Hide map controls" : "Map controls"}
            </button>
          )}
        </section>

        {doc && (
          <section className={`panel px-4 py-3.5 ${controlsOpen ? "" : "hidden"} md:block`}>
            <h2 className="section-title mb-2">Show</h2>
            <div role="radiogroup" aria-label="Map view" className="grid grid-cols-3 gap-1 rounded-md bg-surface-2 p-0.5">
              {(Object.keys(VIEW_META) as View[]).map((v) => (
                <button
                  key={v}
                  role="radio"
                  aria-checked={view === v}
                  onClick={() => setView(v)}
                  className={`pressable rounded-sm px-1.5 py-1 text-2xs ${view === v ? "bg-surface text-ink shadow-sm" : "text-ink-dim hover:text-ink"}`}
                >
                  {VIEW_META[v].label}
                </button>
              ))}
            </div>
            {view === "nudge" && doc.nudge.levels.length > 1 && (
              <div className="mt-2 flex gap-3 text-2xs">
                {doc.nudge.levels.map((l, i) => (
                  <label key={l.level_hpa} className="flex cursor-pointer items-center gap-1.5 text-ink-dim">
                    <input
                      type="radio"
                      name="lvl"
                      className="accent-accent"
                      checked={level === i}
                      onChange={() => setLevel(i)}
                    />
                    {l.level_hpa} hPa
                  </label>
                ))}
              </div>
            )}
            <p className="mt-2 text-2xs leading-relaxed text-ink-faint">{VIEW_META[view].blurb}</p>
            <Legend view={view} doc={doc} level={level} ivtMax={ivtMax} />
          </section>
        )}

        {doc && (
          <section className={`panel px-4 py-3.5 ${controlsOpen ? "" : "hidden"} md:block`}>
            <h2 className="section-title mb-2">Forecast runs</h2>
            <ul className="space-y-1.5 text-xs">
              {[...(baseline ? [baseline] : []), ...away, ...(toward ? [toward] : [])].map((r) => (
                <li key={r.id}>
                  <label className="flex cursor-pointer items-center gap-2">
                    <input
                      type="radio"
                      name="run"
                      className="accent-accent"
                      checked={run?.id === r.id}
                      onChange={() => setRunId(r.id)}
                    />
                    <span className="h-0.5 w-4 shrink-0 rounded-full" style={{ background: css(runRGB(r, dark)) }} />
                    <span className="min-w-0 flex-1 truncate text-ink">{shortLabel(r)}</span>
                    <span className="tnum text-2xs text-ink-faint">{r.s === 0 ? "" : pct(r.change_pct)}</span>
                  </label>
                </li>
              ))}
            </ul>
            <div className="mt-2.5 space-y-1.5 border-t border-line pt-2.5 text-2xs">
              <label className="flex cursor-pointer items-center gap-2 text-ink-dim">
                <input
                  type="checkbox"
                  className="accent-accent"
                  checked={showObserved}
                  onChange={() => setShowObserved((v) => !v)}
                />
                <span className="h-0.5 w-4 rounded-full bg-ink" />
                Observed track (NOAA best track)
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-ink-dim">
                <input
                  type="checkbox"
                  className="accent-accent"
                  checked={showAllRuns}
                  onChange={() => setShowAllRuns((v) => !v)}
                />
                All runs (unselected faded)
              </label>
              <p className="flex items-center gap-2 text-ink-faint">
                <span className="h-2.5 w-2.5 rounded-full border-2 border-ink" /> target: {doc.case.target.label}
              </p>
              <p className="flex items-center gap-2 text-ink-faint">
                <span className="h-2.5 w-2.5 rounded-full border border-ink-faint" /> storm&rsquo;s no-touch zone (
                {doc.case.keep_out_km} km)
              </p>
            </div>
          </section>
        )}
      </aside>

      <aside className="absolute right-3 top-3 z-20 hidden max-h-[calc(100%-1.5rem)] w-[20rem] flex-col gap-3 overflow-y-auto md:flex lg:right-4 lg:top-4">
        {resultPanels}
      </aside>

      {doc && (
        <div className="absolute bottom-3 left-3 right-14 z-20 md:hidden">
          <details className="panel p-3">
            <summary className="cursor-pointer text-xs text-ink">
              Result · {run ? (run.s === 0 ? "no nudge" : pct(run.change_pct)) : "-"}
            </summary>
            <div className="mt-3 flex max-h-[60vh] flex-col gap-3 overflow-y-auto">{resultPanels}</div>
          </details>
        </div>
      )}
    </div>
  );

  function describe(info: PickingInfo): Hover | null {
    const o = info.object as unknown;
    if (!o || !info.layer) return null;
    const id = info.layer.id;
    if (id === "sens") return { kind: "cell", text: `Sensitivity ${((o as Cell)[4] * 100).toFixed(0)}% of max` };
    if (id === "nudge-T")
      return { kind: "cell", text: `Temperature nudge ${(o as Cell)[4] > 0 ? "+" : ""}${(o as Cell)[4].toFixed(3)} K` };
    if (id.startsWith("ivt-"))
      return { kind: "cell", text: `Moisture transport ${(o as Cell)[4].toFixed(0)} kg m⁻¹ s⁻¹` };
    if (id === "runs") return { kind: "track", text: (o as ButterflyRun).label };
    if (id === "run-pts") {
      const p = o as { time: string; err_km?: number; run: string };
      return { kind: "track", text: `${p.run} · ${utc(p.time)}${p.err_km != null ? ` · ${p.err_km} km from observed` : ""}` };
    }
    if (id === "best-pts") {
      const p = o as { time: string; wind_kt: number | null; pres_mb: number | null };
      return {
        kind: "track",
        text: `Observed · ${utc(p.time)}${p.wind_kt ? ` · ${p.wind_kt} kt` : ""}${p.pres_mb ? ` · ${p.pres_mb} mb` : ""}`,
      };
    }
    return null;
  }
}

function shortLabel(r: ButterflyRun) {
  if (r.s === 0) return "No nudge";
  if (r.s < 0) return `Reversed · ${Math.abs(r.s)}× analysis error`;
  return `Away · ${r.s}× analysis error`;
}

function Legend({ view, doc, level, ivtMax }: { view: View; doc: ButterflyCase; level: number; ivtMax: number }) {
  let grad = "";
  let lo = "";
  let hi = "";
  if (view === "sensitivity") {
    grad = SENS_STOPS.map((c) => css(c)).join(",");
    lo = "low";
    hi = "high sensitivity";
  } else if (view === "moisture") {
    grad = IVT_STOPS.map((c) => css(c)).join(",");
    lo = "0";
    hi = `${Math.round(ivtMax)} kg m⁻¹ s⁻¹`;
  } else {
    const m = doc.nudge.levels[level]?.max_abs_T ?? 0;
    grad = [-1, -0.5, 0, 0.5, 1].map((t) => css(tempRGB(t))).join(",");
    lo = `−${m.toFixed(2)} K`;
    hi = `+${m.toFixed(2)} K`;
  }
  return (
    <div className="mt-2.5">
      <div className="h-2 rounded-sm" style={{ background: `linear-gradient(90deg, ${grad})` }} />
      <div className="mt-1 flex justify-between text-2xs text-ink-faint">
        <span className="tnum">{lo}</span>
        <span className="tnum">{hi}</span>
      </div>
    </div>
  );
}

const PROFILE_VARS: [string, string, string][] = [
  ["temperature", "temperature", "#e56a2b"],
  ["u_component_of_wind", "east-west wind", "#4a80f6"],
  ["v_component_of_wind", "north-south wind", "#2f9e8f"],
  ["specific_humidity", "humidity", "#8b5cf6"],
];

/** sensitivity by pressure level, one small line per variable (each normalised) */
function Profile({ levels, profile }: { levels: number[]; profile: Record<string, number[]> }) {
  const W = 260;
  const H = 130;
  const pTop = Math.min(...levels.filter((p) => p >= 100), 1000);
  const pBot = 1000;
  const y = (p: number) => ((Math.log(p) - Math.log(pTop)) / (Math.log(pBot) - Math.log(pTop))) * (H - 12) + 4;
  const idx = levels.map((p, i) => [p, i] as const).filter(([p]) => p >= pTop);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Sensitivity by altitude">
        {[200, 500, 850].map((p) => (
          <g key={p}>
            <line x1={34} x2={W} y1={y(p)} y2={y(p)} stroke="rgb(var(--line))" strokeWidth={1} />
            <text x={0} y={y(p) + 3} fontSize={9} fill="rgb(var(--ink-faint))" className="tnum">
              {p} hPa
            </text>
          </g>
        ))}
        {PROFILE_VARS.map(([k, , color]) => {
          const vals = profile[k];
          if (!vals) return null;
          const d = idx.map(([p, i], n) => `${n ? "L" : "M"}${34 + vals[i] * (W - 40)},${y(p)}`).join(" ");
          return <path key={k} d={d} fill="none" stroke={color} strokeWidth={1.6} />;
        })}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
        {PROFILE_VARS.map(([k, label, color]) => (
          <span key={k} className="flex items-center gap-1.5 text-2xs text-ink-faint">
            <span className="h-0.5 w-3 rounded-full" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
