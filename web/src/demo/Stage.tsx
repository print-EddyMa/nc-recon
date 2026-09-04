import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { Map as MLMap, IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer, BitmapLayer } from "@deck.gl/layers";
import { preload, type DemoAssets, type Sensor } from "./preload";
import { Timeline, easing, clamp01, lerp, type FrameCtx } from "./timeline";
import { BEATS, TOTAL, cameraAt, beatAt, within, OLDFORT, OLDFORT_IMG_BOUNDS } from "./beats";
import { DAMAGE } from "../lib/damage";
import { C, SEV } from "./theme";

export interface StageHandle {
  play(): void;
  pause(): void;
  restart(): void;
  toggle(): void;
  readonly timeline: Timeline | null;
}

interface Props {
  mode: "realtime" | "fixed";
  fixedStep?: number;
  onProgress: (p: number, label: string) => void;
  onReady: (info: { tilesWarmed: number; verifyLaps: number }) => void;
  onFrame?: (ctx: FrameCtx) => void;
}

// Regional box for the Beat-2 NEXRAD plate — wide enough that Helene is seen
// sweeping in and out over GA / SC / TN / VA / the Atlantic, with NC still the
// framed focus. MUST match BBOX4326 in scripts/demo_fetch.mjs `radar()` and
// public/demo/radar/manifest.json.
const RADAR_BBOX: [number, number, number, number] = [-88, 30, -74, 39.5];
const HIST_PX_PER_YEAR = 118;
const HIST_X = (year: number) => (year - 1990) * HIST_PX_PER_YEAR;

/**
 * Phase I — lower-third callouts (I1). All-caps; every figure is a real number
 * from the baked pipeline output (764 = old_fort.geojson feature count, 868 =
 * sensors.json length) or a plain label where there is no confirmed figure.
 * `{n}` marks the digits that get the brief "analyzing" settle (I4).
 */
const LOWER_THIRD: Record<string, string> = {
  descent: "",
  radar: "Hurricane Helene · NEXRAD archive",
  snap: "Old Fort · McDowell County, NC",
  reveal: "Maxar Open Data · 2022 / 2024",
  extrude: "{764} buildings assessed",
  network: "{868} live sensors",
  flood: "National Water Model · flood forecast",
  history: "",
};

/** deterministic 0..1 hash — used for the I4 digit scramble so playback stays
 *  frame-identical (no Math.random). Quantised so it is stable within a step. */
const hash01 = (seed: number) => {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};

/**
 * I4 — render a number with a sub-0.5s "system is computing" settle: each digit
 * scrambles, then locks left-to-right. `t` is ms since the number appeared.
 */
function analyzingDigits(value: number, t: number): string {
  const digits = String(value).split("");
  const LOCK = 120; // ms between each digit locking
  const SETTLE = LOCK * digits.length + 90;
  if (t >= SETTLE) return String(value);
  return digits
    .map((d, i) => {
      if (t >= (i + 1) * LOCK) return d;
      return String(Math.floor(hash01(Math.floor(t / 40) + i * 17.3) * 10));
    })
    .join("");
}

/** I2 — format a camera centre as a mission-style coordinate stamp. */
const fmtCoord = (lon: number, lat: number) =>
  `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? "N" : "S"}  ${Math.abs(lon).toFixed(4)}°${lon >= 0 ? "E" : "W"}`;

const MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
/**
 * I2 — during the radar timelapse the telemetry shows the ACTUAL archive time
 * of the frame on screen (Sept 2024), not now. Derived from the manifest epoch
 * in UTC, so it is identical on every playback.
 */
const radarStampAt = (epochMs: number) => {
  const d = new Date(epochMs);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${String(d.getUTCDate()).padStart(2, "0")} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()} · ${hh}${mm}Z`;
};

/** I6 — a 1° lat/long graticule across the wider region, as GeoJSON lines. */
function makeGraticule(): GeoJSON.FeatureCollection {
  const lines: GeoJSON.Feature[] = [];
  for (let lon = -92; lon <= -68; lon += 1) {
    lines.push({
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: [[lon, 26], [lon, 42]] },
    });
  }
  for (let lat = 26; lat <= 42; lat += 1) {
    lines.push({
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: [[-92, lat], [-68, lat]] },
    });
  }
  return { type: "FeatureCollection", features: lines };
}

const cleanStorm = (s: string) =>
  s
    .replace(/\s*(major disaster|emergency)\s+declarations?/i, "")
    .replace(/^remnants of\s+/i, "")
    .replace(/\b(hurricane|tropical storm|tropical depression|severe|winter|ice|snow)\b/gi, "")
    .replace(/\bstorm\b/gi, "")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

const Stage = forwardRef<StageHandle, Props>(function Stage(
  { mode, fixedStep, onProgress, onReady, onFrame },
  ref,
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const radarWrapRef = useRef<HTMLDivElement | null>(null);
  const radarImgsRef = useRef<HTMLImageElement[]>([]);
  const wipeRef = useRef<HTMLDivElement | null>(null);
  const beforeRef = useRef<HTMLImageElement | null>(null);
  const afterRef = useRef<HTMLDivElement | null>(null);
  const dividerRef = useRef<HTMLDivElement | null>(null);
  const floodRef = useRef<HTMLDivElement | null>(null);
  const floodFillRef = useRef<HTMLDivElement | null>(null);
  const histWrapRef = useRef<HTMLDivElement | null>(null);
  const histTrackRef = useRef<HTMLDivElement | null>(null);
  const titleRef = useRef<HTMLDivElement | null>(null);
  const titleLogoRef = useRef<HTMLImageElement | null>(null);
  const titleRuleRef = useRef<HTMLDivElement | null>(null);
  // Phase I overlays
  const l3Ref = useRef<HTMLDivElement | null>(null);
  const l3RuleRef = useRef<HTMLDivElement | null>(null);
  const l3TextRef = useRef<HTMLDivElement | null>(null);
  const telRef = useRef<HTMLDivElement | null>(null);
  const telCoordRef = useRef<HTMLDivElement | null>(null);
  const telTagRef = useRef<HTMLDivElement | null>(null);
  const scanRef = useRef<HTMLDivElement | null>(null);
  const scanFieldRef = useRef<HTMLDivElement | null>(null);
  const sitrepRef = useRef<HTMLDivElement | null>(null);
  const sitrepRuleRef = useRef<HTMLDivElement | null>(null);

  const mapRef = useRef<MLMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const assetsRef = useRef<DemoAssets | null>(null);
  const tlRef = useRef<Timeline | null>(null);

  const anim = useRef({ ext: 0, bldgA: 0, bmpA: 0, sweep: 0, sensorA: 0, floodFocus: 0 });
  const sensorsRef = useRef<(Sensor & { act: number })[]>([]);
  const floodSensorRef = useRef<Sensor | null>(null);
  const histMarksRef = useRef<{ year: number; landmark: boolean; label: HTMLDivElement }[]>([]);

  useImperativeHandle(ref, () => ({
    play: () => tlRef.current?.play(),
    pause: () => tlRef.current?.pause(),
    toggle: () => tlRef.current?.toggle(),
    restart: () => {
      const tl = tlRef.current;
      if (!tl) return;
      tl.pause();
      anim.current = { ext: 0, bldgA: 0, bmpA: 0, sweep: 0, sensorA: 0, floodFocus: 0 };
      overlayRef.current?.setProps({ layers: [] });
      tl.seek(0);
    },
    get timeline() {
      return tlRef.current;
    },
  }));

  // ---- deck layers, rebuilt from anim.current ---------------------------
  function buildLayers() {
    const a = assetsRef.current;
    if (!a) return [];
    const { ext, bldgA, bmpA, sweep, sensorA, floodFocus } = anim.current;
    const layers: (GeoJsonLayer | ScatterplotLayer | BitmapLayer)[] = [];

    if (bmpA > 0.001) {
      layers.push(
        new BitmapLayer({
          id: "maxar-post",
          image: a.afterImg,
          bounds: OLDFORT_IMG_BOUNDS,
          opacity: bmpA,
        }),
      );
    }

    if (bldgA > 0.001) {
      layers.push(
        new GeoJsonLayer({
          id: "damage",
          data: a.oldFort as unknown as string,
          extruded: true,
          filled: true,
          stroked: true,
          lineWidthUnits: "pixels",
          getLineWidth: 0.4,
          getElevation: (f: { properties: { damage_class: number } }) =>
            DAMAGE[f.properties.damage_class].height * (0.02 + 0.98 * ext),
          getFillColor: (f: { properties: { damage_class: number } }) => {
            const [r, g, b] = DAMAGE[f.properties.damage_class].rgb;
            return [r, g, b, Math.round((150 + 90 * ext) * bldgA)] as [number, number, number, number];
          },
          getLineColor: [12, 16, 22, Math.round(140 * bldgA)] as [number, number, number, number],
          material: { ambient: 0.6, diffuse: 0.6, shininess: 20, specularColor: [40, 55, 70] },
          updateTriggers: { getElevation: ext, getFillColor: [ext, bldgA], getLineColor: bldgA },
        }),
      );
    }

    if (sensorA > 0.001) {
      layers.push(
        new ScatterplotLayer({
          id: "sensors",
          data: sensorsRef.current,
          radiusUnits: "pixels",
          radiusMinPixels: 0.4,
          stroked: false,
          getPosition: (d: Sensor & { act: number }) => [d.lon, d.lat] as [number, number],
          getRadius: (d: Sensor & { act: number }) => {
            const lit = clamp01((sweep - d.act) / 0.12);
            return (0.6 + easing.out(lit) * 3.4) * (0.4 + 0.6 * sensorA);
          },
          getFillColor: (d: Sensor & { act: number }) => {
            const lit = clamp01((sweep - d.act) / 0.12);
            const base = d.kind === "flood" ? SEV[Math.min(3, Math.max(0, d.sev))] : C.accentRGB;
            const a2 = sensorA * (1 - 0.55 * floodFocus);
            return [base[0], base[1], base[2], Math.round((40 + 200 * easing.out(lit)) * a2)] as [
              number,
              number,
              number,
              number,
            ];
          },
          updateTriggers: {
            getRadius: [sweep, sensorA],
            getFillColor: [sweep, sensorA, floodFocus],
          },
        }),
      );
    }
    return layers;
  }
  const pushLayers = () => overlayRef.current?.setProps({ layers: buildLayers() });

  // ---- mount ----------------------------------------------------------
  useEffect(() => {
    let disposed = false;
    const host = hostRef.current;
    if (!host) return;

    (async () => {
      const { assets, map, tilesWarmed, verifyLaps } = await preload(host, onProgress);
      if (disposed) {
        map.remove();
        return;
      }
      assetsRef.current = assets;
      mapRef.current = map;
      (window as unknown as { __demoMap: unknown }).__demoMap = map;

      let maxD = 0;
      const withAct = assets.sensors.map((s) => {
        const d = Math.hypot(s.lon - OLDFORT[0], s.lat - OLDFORT[1]);
        maxD = Math.max(maxD, d);
        return { ...s, act: d };
      });
      withAct.forEach((s) => (s.act /= maxD));
      sensorsRef.current = withAct;
      // the flood-risk beat lands best on a western-NC river reach — the Helene
      // flood country. Prefer a named western river gauge; fall back to the
      // flood gauge nearest Old Fort.
      const west = assets.sensors.filter(
        (s) => s.kind === "flood" && s.lon < -80.5 && s.lat > 34.8 && s.lat < 36.4,
      );
      floodSensorRef.current =
        west.find((s) => /french broad|swannanoa|catawba|broad|pigeon/i.test(s.title)) ??
        west.find((s) => /river|creek/i.test(s.title)) ??
        west.sort(
          (a2, b2) =>
            Math.hypot(a2.lon - OLDFORT[0], a2.lat - OLDFORT[1]) -
            Math.hypot(b2.lon - OLDFORT[0], b2.lat - OLDFORT[1]),
        )[0] ??
        assets.sensors.find((s) => s.kind === "flood") ??
        null;

      // I6 — situation-map graticule. Added FIRST so it sits under nc-fill /
      // nc-line and under the deck overlay; a track fades line-opacity per beat.
      try {
        if (map.getStyle() && !map.getSource("graticule")) {
          map.addSource("graticule", {
            type: "geojson",
            data: makeGraticule() as unknown as GeoJSON.FeatureCollection,
          });
          map.addLayer({
            id: "graticule",
            type: "line",
            source: "graticule",
            paint: { "line-color": C.inkFaint, "line-width": 0.6, "line-opacity": 0 },
          });
        }
      } catch {
        /* teardown race — safe to skip */
      }

      map.addSource("nc", { type: "geojson", data: assets.ncOutline as unknown as string });
      map.addLayer({
        id: "nc-fill",
        type: "fill",
        source: "nc",
        paint: { "fill-color": C.accent, "fill-opacity": 0 },
      });
      map.addLayer({
        id: "nc-line",
        type: "line",
        source: "nc",
        paint: { "line-color": C.accent, "line-width": 1.5, "line-opacity": 0 },
      });

      // interleaved: deck draws into maplibre's own GL context on every map
      // render tick — no separate canvas, no separate render loop to keep in
      // sync, and `preserveDrawingBuffer` on the map covers deck too. (v5 only;
      // we're pinned to maplibre-gl v5.)
      overlayRef.current = new MapboxOverlay({ interleaved: true, layers: [] });
      map.addControl(overlayRef.current as unknown as IControl);
      map.resize();

      radarImgsRef.current = assets.radar.images.map((im, i) => {
        im.className = "demo-radar-frame";
        im.style.opacity = "0";
        im.dataset.i = String(i);
        radarWrapRef.current?.appendChild(im);
        return im;
      });
      if (beforeRef.current) beforeRef.current.src = assets.beforeImg.src;
      if (afterRef.current) afterRef.current.style.backgroundImage = `url(${assets.afterImg.src})`;
      if (titleLogoRef.current) titleLogoRef.current.src = assets.logo.src;
      buildHistoryStrip(assets);

      const tl = new Timeline({
        total: TOTAL,
        mode,
        step: fixedStep,
        onFrame: (ctx) => {
          driveMap(ctx.ms);
          onFrame?.(ctx);
        },
      });
      addTracks(tl);
      tlRef.current = tl;
      tl.seek(0);
      onReady({ tilesWarmed, verifyLaps });
    })();

    return () => {
      disposed = true;
      tlRef.current?.dispose();
      try {
        mapRef.current?.remove();
      } catch {
        /* noop */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- camera + radar plate, every frame -----------------------------
  function driveMap(ms: number) {
    const map = mapRef.current;
    if (!map) return;
    const inTitle = ms >= BEATS[8].t0;
    if (!inTitle) {
      const cam = cameraAt(ms);
      map.jumpTo({ center: cam.center, zoom: cam.zoom, pitch: cam.pitch, bearing: cam.bearing });
    }
    const rw = radarWrapRef.current;
    if (rw && !rw.hidden) {
      const p0 = map.project([RADAR_BBOX[0], RADAR_BBOX[3]]);
      const p1 = map.project([RADAR_BBOX[2], RADAR_BBOX[1]]);
      rw.style.transform = `translate(${p0.x}px,${p0.y}px)`;
      rw.style.width = `${p1.x - p0.x}px`;
      rw.style.height = `${p1.y - p0.y}px`;
    }
  }

  // ---- tracks -------------------------------------------------------
  function addTracks(tl: Timeline) {
    const B = BEATS;
    const show = (el: HTMLElement | null, v: boolean) => {
      if (el) el.hidden = !v;
    };

    // NC outline (B1 in, B2 hold, B3 out)
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const map = mapRef.current;
        if (!map || !map.getLayer("nc-line")) return;
        let o = 0;
        if (ms < B[0].t1) o = easing.out(clamp01(ms / B[0].t1));
        else if (ms < B[1].t1) o = 1;
        else if (ms < B[2].t0 + 600) o = 1 - clamp01((ms - B[2].t0) / 600);
        map.setPaintProperty("nc-line", "line-opacity", 0.95 * o);
        map.setPaintProperty("nc-line", "line-width", 1.75);
        map.setPaintProperty("nc-fill", "fill-opacity", 0.11 * o);
      },
    });

    // I6 — graticule opacity. Visible on the two WIDE establishing beats (the
    // descent, and the pull-back to the statewide sensor view); hidden through
    // the radar plate and the Old Fort close-ups where a 1° grid is meaningless.
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const map = mapRef.current;
        if (!map || !map.getLayer("graticule")) return;
        const descent = clamp01(ms / 700) * (1 - clamp01((ms - B[1].t0) / 500));
        const wide =
          clamp01((ms - (B[4].t1 - 300)) / 800) * (1 - clamp01((ms - (B[8].t0 - 220)) / 200));
        map.setPaintProperty("graticule", "line-opacity", 0.16 * Math.max(descent, wide));
      },
    });

    // radar timelapse (B2)
    tl.add({
      start: B[1].t0 - 150,
      end: B[2].t0 + 200,
      update: (_p, { ms }) => {
        const wrap = radarWrapRef.current;
        const imgs = radarImgsRef.current;
        if (!wrap || !imgs.length) return;
        const active = ms >= B[1].t0 - 150 && ms <= B[2].t0 + 200;
        show(wrap, active);
        if (!active) return;
        const local = within(ms, B[1]);
        const fade =
          clamp01((ms - (B[1].t0 - 150)) / 300) * (1 - clamp01((ms - (B[1].t1 - 250)) / 450));
        wrap.style.opacity = String(0.92 * fade);
        const f = Math.min(imgs.length - 1, Math.floor(local * imgs.length));
        for (let i = 0; i < imgs.length; i++) imgs[i].style.opacity = i === f ? "1" : "0";
      },
    });

    // Old Fort imagery (deck BitmapLayer) picks up from the DOM wipe at the
    // B4→B5 boundary; the extrude rides on top; all fade out through B6.
    tl.add({
      start: B[4].t0 - 250,
      end: B[5].t1,
      update: (_p, { ms }) => {
        anim.current.bmpA =
          clamp01((ms - (B[4].t0 - 150)) / 400) * (1 - clamp01((ms - (B[5].t0 + 250)) / 850));
        anim.current.ext = easing.out(within(ms, B[4]));
        anim.current.bldgA =
          clamp01((ms - (B[4].t0 + 120)) / 420) * (1 - clamp01((ms - (B[5].t0 + 400)) / 850));
        pushLayers();
      },
    });

    // before / after wipe (B4) — DOM <img> clip wipe. The "before" plate fades
    // in over the dark Old Fort basemap right after the snap lands (~6650),
    // then the wipe reveals "after" across B4.
    tl.add({
      start: B[3].t0 - 350,
      end: B[4].t0 + 420,
      update: (_p, { ms }) => {
        const wipe = wipeRef.current;
        if (!wipe) return;
        const active = ms >= B[3].t0 - 350 && ms <= B[4].t0 + 420;
        show(wipe, active);
        if (!active) return;
        const inA = clamp01((ms - (B[3].t0 - 350)) / 300);
        const outA = 1 - clamp01((ms - B[4].t0) / 360); // fade to the deck post-bitmap
        wipe.style.opacity = String(Math.min(inA, outA));
        const wp = easing.inOut(within(ms, B[3]));
        if (afterRef.current) afterRef.current.style.clipPath = `inset(0 ${(1 - wp) * 100}% 0 0)`;
        if (dividerRef.current) {
          dividerRef.current.style.left = `${wp * 100}%`;
          dividerRef.current.style.opacity = wp > 0.002 && wp < 0.998 ? "1" : "0";
        }
      },
    });

    // sensor cascade (B6)
    tl.add({
      start: B[5].t0 - 100,
      end: B[7].t0,
      update: (_p, { ms }) => {
        const active = ms >= B[5].t0 - 100 && ms < B[7].t0;
        if (!active) {
          if (anim.current.sensorA !== 0) {
            anim.current.sensorA = 0;
            pushLayers();
          }
          return;
        }
        anim.current.sweep = easing.out(within(ms, B[5]));
        anim.current.sensorA =
          clamp01((ms - (B[5].t0 - 100)) / 500) * (1 - clamp01((ms - (B[6].t1 - 250)) / 400));
        pushLayers();
      },
    });

    // flood flash (B7)
    tl.add({
      start: B[6].t0 - 120,
      end: B[7].t0,
      update: (_p, { ms }) => {
        const el = floodRef.current;
        const map = mapRef.current;
        if (!el || !map) return;
        const active = ms >= B[6].t0 - 120 && ms < B[7].t0;
        show(el, active);
        // focus factor also dims the wider sensor field (read in buildLayers)
        anim.current.floodFocus = active
          ? clamp01((ms - (B[6].t0 - 120)) / 300) * (1 - clamp01((ms - (B[6].t1 - 220)) / 260))
          : 0;
        if (!active) return;
        const fs = floodSensorRef.current;
        if (fs) {
          const pt = map.project([fs.lon, fs.lat]);
          el.style.transform = `translate(${pt.x}px, ${pt.y}px)`;
        }
        const appear = clamp01((ms - (B[6].t0 - 120)) / 260);
        const leave = 1 - clamp01((ms - (B[6].t1 - 200)) / 200);
        el.style.opacity = String(Math.min(appear, leave));
        // rise fills across the beat and is still climbing when it cuts away
        const rise = easing.out(clamp01((ms - (B[6].t0 - 60)) / 1150));
        if (floodFillRef.current) floodFillRef.current.style.height = `${16 + rise * 62}%`;
        pushLayers();
      },
    });

    // history scrub (B8)
    tl.add({
      start: B[7].t0 - 150,
      end: B[8].t0,
      update: (_p, { ms }) => {
        const wrap = histWrapRef.current;
        const track = histTrackRef.current;
        if (!wrap || !track) return;
        const active = ms >= B[7].t0 - 150 && ms < B[8].t0;
        show(wrap, active);
        if (!active) return;
        wrap.style.opacity = String(clamp01((ms - (B[7].t0 - 150)) / 260));
        const q = easing.inOut(within(ms, B[7]));
        const centreYear = lerp(1996.5, 2025.2, q);
        track.style.transform = `translateX(${-lerp(HIST_X(1996.5), HIST_X(2025.2), q)}px)`;
        for (const m of histMarksRef.current) {
          const k = clamp01(1 - Math.abs(m.year - centreYear) / 1.1);
          m.label.style.opacity = String(m.landmark ? 0.25 + 0.75 * k : 0);
          m.label.style.transform = `translateX(-50%) scale(${0.9 + 0.25 * k})`;
        }
      },
    });

    // -------- Phase I overlays (all playhead-driven; no CSS transitions) -----

    // I1 + I4 — lower-third data callout. Sharp slide-in from the left, hard
    // cut out; the {digits} in LOWER_THIRD get a brief "analyzing" settle.
    let lastL3 = " ";
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const wrap = l3Ref.current;
        const rule = l3RuleRef.current;
        const text = l3TextRef.current;
        if (!wrap || !rule || !text) return;
        const b = beatAt(ms);
        const raw = ms >= B[8].t0 ? "" : LOWER_THIRD[b.id] ?? "";
        if (!raw) {
          wrap.style.opacity = "0";
          lastL3 = "";
          return;
        }
        const local = ms - b.t0;
        const beatDur = b.t1 - b.t0;
        // sharp slide-in over 170ms, hard cut out over the last 110ms
        const slide = easing.out(clamp01(local / 170));
        const outK = 1 - clamp01((local - (beatDur - 200)) / 110);
        wrap.style.opacity = String(clamp01(local / 70) * outK);
        wrap.style.transform = `translateX(${(1 - slide) * -44}px)`;
        rule.style.transform = `scaleX(${easing.out(clamp01(local / 150))})`;

        // I4 — digit settle. Rebuild innerHTML only when the rendered string
        // actually changes (keeps playback cheap and deterministic).
        const m = raw.match(/^\{(\d+)\}(.*)$/);
        let str: string;
        if (m) {
          const shown = analyzingDigits(Number(m[1]), local - 150);
          str = `<span class="num">${shown}</span>${m[2].toUpperCase()}`;
        } else {
          str = raw.toUpperCase();
        }
        if (str !== lastL3) {
          text.innerHTML = str;
          lastL3 = str;
        }
      },
    });

    // I2 — persistent telemetry readout. Real coordinates on live beats; the
    // real Sept-2024 archive time during the radar timelapse; the scrubbed
    // year during the history beat. Never `Date.now()`.
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const wrap = telRef.current;
        const coord = telCoordRef.current;
        const tag = telTagRef.current;
        if (!wrap || !coord || !tag) return;
        if (ms >= B[8].t0) {
          wrap.style.opacity = "0";
          return;
        }
        wrap.style.opacity = String(clamp01(ms / 400) * (1 - clamp01((ms - (B[8].t0 - 220)) / 200)) * 0.92);

        const b = beatAt(ms);
        if (b.id === "radar") {
          const frames = assetsRef.current?.radar.manifest.frames ?? [];
          if (frames.length) {
            const f = Math.min(frames.length - 1, Math.floor(within(ms, b) * frames.length));
            coord.textContent = radarStampAt(frames[f].at);
          }
          tag.textContent = "NEXRAD Level III";
        } else if (b.id === "history") {
          const q = easing.inOut(within(ms, b));
          coord.textContent = `${Math.round(lerp(1996.5, 2025.2, q))}`;
          tag.textContent = "FEMA declarations";
        } else {
          const c = cameraAt(ms).center;
          coord.textContent = fmtCoord(c[0], c[1]);
          tag.textContent =
            b.id === "reveal"
              ? "Maxar Open Data"
              : b.id === "extrude"
                ? "xView2 · xBD"
                : b.id === "network"
                  ? "NWPS · USGS · NWS"
                  : b.id === "flood"
                    ? "Nat'l Water Model"
                    : "SITREP // active";
        }
      },
    });

    // I3 — scan-line wipe on the cut INTO the analysis beat (extrude). One
    // crisp accent line sweeping top→bottom; a flat, faint accent field as it
    // passes. Callback to the logo / radar-ring scan motif.
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const line = scanRef.current;
        const field = scanFieldRef.current;
        if (!line || !field) return;
        const t0 = B[4].t0 - 160;
        const local = ms - t0;
        const on = local >= 0 && local <= 520;
        show(line, on);
        show(field, on);
        if (!on) return;
        const p = clamp01(local / 420);
        line.style.transform = `translateY(${(p * 100).toFixed(2)}vh)`;
        line.style.opacity = p > 0.01 && p < 0.99 ? "0.9" : "0";
        field.style.opacity = String(0.06 * Math.sin(p * Math.PI));
      },
    });

    // I5 — opening situation-report header. Flat document title, hard cut in
    // and out, does not slow the descent.
    tl.add({
      start: 0,
      end: 1600,
      update: (_p, { ms }) => {
        const wrap = sitrepRef.current;
        const rule = sitrepRuleRef.current;
        if (!wrap || !rule) return;
        const on = ms < 1450;
        show(wrap, on);
        if (!on) return;
        wrap.style.opacity = ms >= 60 && ms < 1280 ? "1" : "0";
        wrap.style.transform = `translateX(${(1 - easing.out(clamp01(ms / 240))) * -22}px)`;
        rule.style.transform = `scaleX(${easing.out(clamp01((ms - 120) / 300))})`;
      },
    });

    // title card (B9) — hard cut, then held dead still (I5 close)
    tl.add({
      start: B[8].t0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const active = ms >= B[8].t0;
        show(titleRef.current, active);
        if (!active) return;
        for (const el of [radarWrapRef.current, wipeRef.current, floodRef.current, histWrapRef.current])
          show(el, false);
        if (l3Ref.current) l3Ref.current.style.opacity = "0";
        if (telRef.current) telRef.current.style.opacity = "0";
        const k = easing.out(clamp01((ms - (B[8].t0 + 120)) / 420));
        if (titleLogoRef.current) {
          titleLogoRef.current.style.opacity = String(k);
          titleLogoRef.current.style.transform = `translateY(${(1 - k) * 8}px)`;
        }
        if (titleRuleRef.current)
          titleRuleRef.current.style.transform = `scaleX(${easing.out(clamp01((ms - (B[8].t0 + 340)) / 440))})`;
      },
    });
  }

  function buildHistoryStrip(a: DemoAssets) {
    const track = histTrackRef.current;
    if (!track) return;
    track.innerHTML = "";
    histMarksRef.current = [];
    const LM = /helene|florence|matthew|michael|floyd|fran|hugo|isabel|dorian|isaias|fred|frances/i;
    for (const row of a.history) {
      const dt = new Date(row.date);
      const year = dt.getUTCFullYear() + dt.getUTCMonth() / 12;
      if (year < 1993 || year > 2026) continue;
      const landmark = row.dr && LM.test(row.title);
      const x = HIST_X(year);
      const tick = document.createElement("div");
      tick.className = "demo-hist-tick";
      tick.style.left = `${x}px`;
      tick.style.background = landmark ? C.accent : C.inkFaint;
      tick.style.height = landmark ? "24px" : "10px";
      track.appendChild(tick);
      const label = document.createElement("div");
      label.className = "demo-hist-label";
      label.style.left = `${x}px`;
      label.textContent = cleanStorm(row.title);
      label.style.opacity = "0";
      track.appendChild(label);
      histMarksRef.current.push({ year, landmark, label });
    }
    for (let y = 1994; y <= 2026; y += 4) {
      const g = document.createElement("div");
      g.className = "demo-hist-year";
      g.style.left = `${HIST_X(y)}px`;
      g.textContent = String(y);
      track.appendChild(g);
    }
  }

  return (
    <div className="demo-stage">
      <div ref={hostRef} className="demo-map" />

      <div ref={radarWrapRef} className="demo-radar" hidden />

      <div ref={wipeRef} className="demo-wipe" hidden>
        <img ref={beforeRef} className="demo-wipe-img" alt="" />
        <div ref={afterRef} className="demo-wipe-img demo-wipe-after" />
        <div ref={dividerRef} className="demo-wipe-divider" />
        <div className="demo-wipe-tags">
          <span>2022 · before</span>
          <span>2024 · after Helene</span>
        </div>
      </div>

      <div ref={floodRef} className="demo-flood" hidden>
        <div className="demo-flood-gauge">
          <div ref={floodFillRef} className="demo-flood-fill" />
        </div>
        <div className="demo-flood-label">
          Flood forecast<b>rising · moderate</b>
        </div>
      </div>

      <div ref={histWrapRef} className="demo-hist" hidden>
        <div className="demo-hist-centre" />
        <div ref={histTrackRef} className="demo-hist-track" />
        <div className="demo-hist-cap">North Carolina · federally declared disasters</div>
      </div>

      {/* I3 — scan-line wipe */}
      <div ref={scanFieldRef} className="demo-scanline-field" hidden />
      <div ref={scanRef} className="demo-scanline" hidden />

      {/* I5 — opening situation-report header */}
      <div ref={sitrepRef} className="demo-sitrep" hidden>
        <div className="demo-sitrep-kicker">Situation report</div>
        <div ref={sitrepRuleRef} className="demo-sitrep-rule" />
        <div className="demo-sitrep-place">North Carolina</div>
      </div>

      {/* I2 — persistent telemetry readout */}
      <div ref={telRef} className="demo-telemetry">
        <div ref={telCoordRef} className="demo-telemetry-coord" />
        <div ref={telTagRef} className="demo-telemetry-tag" />
      </div>

      {/* I1 — lower-third data callout */}
      <div ref={l3Ref} className="demo-l3">
        <div ref={l3RuleRef} className="demo-l3-rule" />
        <div ref={l3TextRef} className="demo-l3-text" />
      </div>

      <div ref={titleRef} className="demo-title" hidden>
        <img ref={titleLogoRef} className="demo-title-logo" alt="NC Recon" />
        <div ref={titleRuleRef} className="demo-title-rule" />
      </div>
    </div>
  );
});

export default Stage;
