import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { Map as MLMap, IControl } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer } from "@deck.gl/core";
import { BitmapLayer, ColumnLayer, ScatterplotLayer, SolidPolygonLayer } from "@deck.gl/layers";
import { Timeline, easing, clamp01, lerp, type FrameCtx } from "../demo/timeline";
import { preloadIntro, type AreaRow, type IntroAssets, type Structure } from "./preload";
import { B, TOTAL, OLDFORT, OLDFORT_IMG_BOUNDS, beatAt, cameraAt } from "./beats";

export interface StageHandle {
  play(): void;
  pause(): void;
  toggle(): void;
  restart(): void;
  seek(ms: number): void;
  readonly timeline: Timeline | null;
}

interface Props {
  mode: "realtime" | "fixed";
  dense: boolean;
  onProgress: (p: number, label: string) => void;
  onReady: () => void;
  onError: (message: string) => void;
  onFrame?: (ctx: FrameCtx) => void;
  onEnd?: () => void;
}

type RGB = [number, number, number];
type RGBA = [number, number, number, number];

// FEMA damage levels in the product's own colours (ColorBrewer YlOrRd,
// web/src/lib/ops.ts). "No damage" is a slate here, not the product's grey,
// so it sits back on the dark stage and damage reads against it.
const LEVEL_RGB: RGB[] = [
  [128, 140, 156],
  [254, 204, 92],
  [253, 141, 60],
  [240, 59, 32],
  [189, 0, 38],
];
const LEVEL_NAME = ["No damage", "Affected", "Minor", "Major", "Destroyed"];
const LEVEL_KEY = ["no_damage", "affected", "minor", "major", "destroyed"];
// A severity skyline: height says how bad, not how tall the building is.
const LEVEL_HEIGHT = [6, 14, 26, 48, 76];
const ACCENT: RGB = [74, 128, 246];
const NOT_ASSESSED: RGB = [96, 102, 112];
/** metres of column per structure expected at Major or Destroyed (region beat) */
const COLUMN_M = 112;
const SWEEP_SOFT = 0.0009; // degrees of longitude over which a structure lights up

const NUM_WORD = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"];
const fmt = (n: number) => Math.round(n).toLocaleString("en-US");
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmtDate = (iso: string | null) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MON[m - 1]} ${y}`;
};
const radarStamp = (epochMs: number) => {
  const d = new Date(epochMs);
  return {
    day: `${String(d.getUTCDate()).padStart(2, "0")} ${MON[d.getUTCMonth()].toUpperCase()} ${d.getUTCFullYear()}`,
    time: `${String(d.getUTCHours()).padStart(2, "0")}${String(d.getUTCMinutes()).padStart(2, "0")}Z`,
  };
};
const fmtCoord = (lon: number, lat: number) =>
  `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? "N" : "S"}  ${Math.abs(lon).toFixed(4)}°${lon >= 0 ? "E" : "W"}`;

interface Caption {
  t0: number;
  t1: number;
  text: string;
  sub?: string;
}

interface StatView {
  big: string;
  label: string;
  sub?: string;
  rows: { v: string; l: string }[];
  /** 0..1 reveal of the FEMA-level bar, or -1 to hide it */
  bar: number;
  alpha: number;
}

const NC_MARK =
  "M 92.04,0.0 L 294.65,1.34 L 298.66,15.28 L 288.92,13.94 L 274.03,19.67 L 266.2,20.24 L 266.58,22.72 L 287.97,20.81 L 291.41,24.06 L 297.71,22.72 L 300.0,31.13 L 297.9,35.14 L 293.7,35.52 L 284.91,44.11 L 273.27,44.49 L 271.36,50.41 L 276.32,56.33 L 280.33,57.48 L 272.88,67.22 L 266.58,66.07 L 247.87,69.13 L 235.84,75.81 L 226.29,84.6 L 221.32,95.67 L 214.07,93.19 L 201.46,95.48 L 161.94,62.25 L 122.79,61.68 L 123.36,57.67 L 118.01,51.75 L 114.39,53.85 L 114.19,50.22 L 71.23,48.5 L 42.2,55.38 L 0.0,55.76 L 0.95,47.55 L 7.83,46.79 L 10.5,41.06 L 19.1,35.9 L 28.64,35.71 L 37.24,30.36 L 46.21,28.45 L 53.85,20.62 L 58.63,18.33 L 59.58,21.77 L 73.33,15.09 L 79.63,16.42 L 84.02,9.93 L 90.52,8.21 L 92.04,0.0 Z";

const Stage = forwardRef<StageHandle, Props>(function Stage(
  { mode, dense, onProgress, onReady, onError, onFrame, onEnd },
  ref,
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const radarRef = useRef<HTMLDivElement | null>(null);
  const radarImgs = useRef<HTMLImageElement[]>([]);
  const stampRef = useRef<HTMLDivElement | null>(null);
  const stampDayRef = useRef<HTMLDivElement | null>(null);
  const stampTimeRef = useRef<HTMLDivElement | null>(null);
  const plateRef = useRef<HTMLDivElement | null>(null);
  const beforeRef = useRef<HTMLImageElement | null>(null);
  const afterRef = useRef<HTMLDivElement | null>(null);
  const dividerRef = useRef<HTMLDivElement | null>(null);
  const tagBeforeRef = useRef<HTMLSpanElement | null>(null);
  const tagAfterRef = useRef<HTMLSpanElement | null>(null);
  const sweepRef = useRef<HTMLDivElement | null>(null);
  const scrimRef = useRef<HTMLDivElement | null>(null);
  const capRef = useRef<HTMLDivElement | null>(null);
  const capTextRef = useRef<HTMLDivElement | null>(null);
  const capSubRef = useRef<HTMLDivElement | null>(null);
  const statRef = useRef<HTMLDivElement | null>(null);
  const statBigRef = useRef<HTMLDivElement | null>(null);
  const statLabelRef = useRef<HTMLDivElement | null>(null);
  const statSubRef = useRef<HTMLDivElement | null>(null);
  const statRowsRef = useRef<HTMLDivElement | null>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  const barFillRef = useRef<HTMLDivElement | null>(null);
  const barLegendRef = useRef<HTMLDivElement | null>(null);
  const telRef = useRef<HTMLDivElement | null>(null);
  const telCoordRef = useRef<HTMLDivElement | null>(null);
  const telTagRef = useRef<HTMLDivElement | null>(null);
  const brandRef = useRef<HTMLDivElement | null>(null);
  const noteRef = useRef<HTMLDivElement | null>(null);
  const townsRef = useRef<HTMLDivElement | null>(null);
  const townEls = useRef<HTMLDivElement[]>([]);
  const cutRef = useRef<HTMLDivElement | null>(null);
  const scanRef = useRef<HTMLDivElement | null>(null);
  const titleRef = useRef<HTMLDivElement | null>(null);
  const ringARef = useRef<SVGCircleElement | null>(null);
  const ringBRef = useRef<SVGCircleElement | null>(null);
  const ringCRef = useRef<SVGCircleElement | null>(null);
  const markRef = useRef<SVGSVGElement | null>(null);
  const wordRef = useRef<HTMLDivElement | null>(null);
  const descRef = useRef<HTMLDivElement | null>(null);
  const discRef = useRef<HTMLDivElement | null>(null);
  const progRef = useRef<HTMLDivElement | null>(null);

  const mapRef = useRef<MLMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const assetsRef = useRef<IntroAssets | null>(null);
  const tlRef = useRef<Timeline | null>(null);
  const capsRef = useRef<Caption[]>([]);
  const polysRef = useRef<(Structure & { d: number })[]>([]);
  const lonsRef = useRef<number[]>([]);

  const fresh = () => ({
    wideA: 0,
    sharpA: 0,
    desat: 0,
    dotA: 0,
    polyA: 0,
    sweepLon: -Infinity,
    rise: 0,
    reviewK: 0,
    colA: 0,
    colRise: 0,
  });
  const anim = useRef(fresh());

  useImperativeHandle(ref, () => ({
    play: () => tlRef.current?.play(),
    pause: () => tlRef.current?.pause(),
    toggle: () => tlRef.current?.toggle(),
    restart: () => {
      const tl = tlRef.current;
      if (!tl) return;
      tl.pause();
      anim.current = fresh();
      tl.seek(0);
    },
    seek: (ms: number) => tlRef.current?.seek(ms),
    get timeline() {
      return tlRef.current;
    },
  }));

  // ---- deck layers, rebuilt from anim.current ------------------------------
  const lit = (d: Structure) => clamp01((anim.current.sweepLon - d.c[0]) / SWEEP_SOFT);

  function levelColor(d: Structure, alpha: number): RGBA {
    const { reviewK } = anim.current;
    if (d.l < 0) return [...NOT_ASSESSED, Math.round(alpha * 0.7 * (1 - 0.7 * reviewK))];
    const base = LEVEL_RGB[d.l];
    if (reviewK > 0) {
      if (d.v)
        return [
          Math.round(lerp(base[0], ACCENT[0], reviewK)),
          Math.round(lerp(base[1], ACCENT[1], reviewK)),
          Math.round(lerp(base[2], ACCENT[2], reviewK)),
          Math.round(alpha),
        ];
      return [base[0], base[1], base[2], Math.round(alpha * (1 - 0.78 * reviewK))];
    }
    return [base[0], base[1], base[2], Math.round(alpha * (d.l === 0 ? 0.72 : 1))];
  }

  function buildLayers() {
    const a = assetsRef.current;
    if (!a) return [];
    const s = anim.current;
    const ground = { depthWriteEnabled: false, depthCompare: "always" } as const;
    const layers: Layer[] = [];
    const tint = Math.round(lerp(255, 150, s.desat));

    if (s.wideA > 0.001)
      layers.push(
        new BitmapLayer({
          id: "plate-wide",
          image: a.wideImg,
          bounds: a.wideBounds,
          opacity: s.wideA,
          desaturate: s.desat * 0.85,
          tintColor: [tint, tint, tint],
          parameters: ground,
        }),
      );
    if (s.sharpA > 0.001)
      layers.push(
        new BitmapLayer({
          id: "plate-sharp",
          image: a.afterImg,
          bounds: OLDFORT_IMG_BOUNDS,
          opacity: s.sharpA,
          desaturate: s.desat * 0.85,
          tintColor: [tint, tint, tint],
          parameters: ground,
        }),
      );

    // the read: every structure lights as the sweep passes its longitude
    if (s.dotA > 0.001)
      layers.push(
        new ScatterplotLayer<Structure>({
          id: "structure-dots",
          data: a.structures,
          radiusUnits: "pixels",
          stroked: true,
          lineWidthUnits: "pixels",
          getLineWidth: 1,
          getPosition: (d) => d.c,
          getRadius: (d) => {
            const k = lit(d);
            // a flare as the line crosses, settling to a mark sized by severity
            const rest = d.l >= 3 ? 3.6 : d.l >= 1 ? 2.9 : 2.2;
            return k <= 0 ? 0 : rest + (k < 1 ? 6.5 * Math.sin(k * Math.PI) : 0);
          },
          getFillColor: (d) => levelColor(d, 255 * Math.min(1, lit(d) * 1.6) * s.dotA),
          getLineColor: (d) => [15, 17, 21, Math.round(210 * Math.min(1, lit(d) * 1.6) * s.dotA)] as RGBA,
          parameters: ground,
          updateTriggers: {
            getRadius: s.sweepLon,
            getFillColor: [s.sweepLon, s.dotA, s.reviewK],
            getLineColor: [s.sweepLon, s.dotA],
          },
        }),
      );

    if (s.polyA > 0.001)
      layers.push(
        new SolidPolygonLayer<Structure & { d: number }>({
          id: "structures",
          data: polysRef.current,
          extruded: true,
          getPolygon: (d) => d.r as [number, number][],
          getElevation: (d) => {
            // the rise radiates out from the town centre
            const k = easing.out(clamp01((s.rise - 0.5 * d.d) / 0.5));
            return 0.6 + LEVEL_HEIGHT[d.l] * k;
          },
          getFillColor: (d) => levelColor(d, (170 + 70 * s.rise) * lit(d) * s.polyA),
          material: { ambient: 0.62, diffuse: 0.6, shininess: 18, specularColor: [40, 55, 70] },
          updateTriggers: {
            getElevation: s.rise,
            getFillColor: [s.sweepLon, s.rise, s.polyA, s.reviewK],
          },
        }),
      );

    if (s.colA > 0.001) {
      const n = a.areas.areas.length;
      layers.push(
        new ScatterplotLayer<AreaRow>({
          id: "town-bases",
          data: a.areas.areas,
          radiusUnits: "meters",
          getRadius: 3400,
          stroked: true,
          filled: false,
          lineWidthUnits: "pixels",
          getLineWidth: 1.5,
          getPosition: (d) => d.center,
          getLineColor: [...ACCENT, Math.round(210 * s.colA)] as RGBA,
          parameters: ground,
          updateTriggers: { getLineColor: s.colA },
        }),
        new ColumnLayer<AreaRow>({
          id: "town-columns",
          data: a.areas.areas,
          diskResolution: 28,
          radius: 1900,
          extruded: true,
          getPosition: (d) => d.center,
          getElevation: (d) => {
            const i = a.areas.areas.indexOf(d);
            return d.severe * COLUMN_M * easing.out(clamp01(s.colRise * 1.6 - (i / n) * 0.6));
          },
          getFillColor: [...LEVEL_RGB[3], Math.round(238 * s.colA)] as RGBA,
          material: { ambient: 0.7, diffuse: 0.55, shininess: 12, specularColor: [60, 40, 30] },
          updateTriggers: { getElevation: s.colRise, getFillColor: s.colA },
        }),
      );
    }
    return layers;
  }
  const pushLayers = () => overlayRef.current?.setProps({ layers: buildLayers() });

  // ---- mount ----------------------------------------------------------------
  useEffect(() => {
    let disposed = false;
    const host = hostRef.current;
    if (!host) return;

    (async () => {
      let loaded: Awaited<ReturnType<typeof preloadIntro>>;
      try {
        loaded = await preloadIntro(host, onProgress, dense);
      } catch (ex) {
        onError((ex as Error).message);
        return;
      }
      const { assets, map } = loaded;
      if (disposed) {
        map.remove();
        return;
      }
      assetsRef.current = assets;
      mapRef.current = map;
      (window as unknown as { __introMap: unknown }).__introMap = map;

      // structures with outlines, each with its normalised distance from the
      // town centre (the rise radiates outward); and sorted longitudes so the
      // "structures found" counter is the real number the sweep has passed
      let maxD = 0;
      const polys = assets.structures
        .filter((s) => s.r && s.l >= 0)
        .map((s) => {
          const d = Math.hypot((s.c[0] - OLDFORT[0]) * 0.813, s.c[1] - OLDFORT[1]);
          maxD = Math.max(maxD, d);
          return { ...s, d };
        });
      polys.forEach((p) => (p.d /= maxD || 1));
      polysRef.current = polys;
      lonsRef.current = assets.structures.map((s) => s.c[0]).sort((x, y) => x - y);

      map.addSource("nc", { type: "geojson", data: assets.ncOutline as unknown as string });
      map.addLayer({
        id: "nc-fill",
        type: "fill",
        source: "nc",
        paint: { "fill-color": "#4a80f6", "fill-opacity": 0 },
      });
      map.addLayer({
        id: "nc-line",
        type: "line",
        source: "nc",
        paint: { "line-color": "#4a80f6", "line-width": 1.75, "line-opacity": 0 },
      });

      overlayRef.current = new MapboxOverlay({ interleaved: true, layers: [] });
      map.addControl(overlayRef.current as unknown as IControl);
      map.resize();

      radarImgs.current = assets.radar.images.map((im) => {
        im.className = "intro-radar-frame";
        im.style.opacity = "0";
        radarRef.current?.appendChild(im);
        return im;
      });
      if (beforeRef.current) beforeRef.current.src = assets.beforeImg.src;
      if (afterRef.current) afterRef.current.style.backgroundImage = `url(${assets.afterImg.src})`;

      const f = assets.areas.focus;
      const tot = assets.areas.total;
      if (tagBeforeRef.current) tagBeforeRef.current.textContent = `Before · ${fmtDate(f.pre_date)}`;
      if (tagAfterRef.current) tagAfterRef.current.textContent = `After Helene · ${fmtDate(f.post_date)}`;
      const under = Math.ceil(tot.max_runtime_s / 10) * 10;
      capsRef.current = [
        { t0: 450, t1: B.storm.t1 - 150, text: "Helene crosses North Carolina.", sub: "NEXRAD radar archive, 26 to 27 September 2024" },
        { t0: B.plunge.t0 + 150, t1: B.plunge.t1 - 100, text: "Every building in its path has to be checked." },
        { t0: B.reveal.t0 + 250, t1: B.reveal.t0 + 2950, text: "The picture already knows.", sub: `Maxar Open Data · ${f.name}, ${f.county} County` },
        { t0: B.reveal.t0 + 3050, t1: B.widen.t1 - 150, text: "Nobody has had time to read it." },
        { t0: B.read.t0 + 100, t1: B.read.t1 - 150, text: "NC Recon reads it.", sub: "Before and after imagery, every structure in the inventory" },
        { t0: B.rise.t0 + 150, t1: B.rise.t1 - 150, text: "Each structure gets a FEMA damage level, with a probability." },
        { t0: B.review.t0 + 150, t1: B.review.t1 - 200, text: "And it says what it is not sure of.", sub: "Uncertain and severe calls go to a human review queue" },
        {
          t0: B.region.t0 + 350,
          t1: B.region.t1 - 200,
          text: `${NUM_WORD[tot.areas] ?? tot.areas} towns assessed. Under ${under} seconds each.`,
          sub: "Assessment run time per town, imagery already fetched",
        },
      ];
      buildLegend(assets);
      buildTowns(assets);

      const tl = new Timeline({
        total: TOTAL,
        mode,
        onFrame: (ctx) => {
          drive(ctx.ms);
          onFrame?.(ctx);
        },
        onEnd,
      });
      addTracks(tl, assets);
      tlRef.current = tl;
      tl.seek(0);
      onReady();
    })();

    return () => {
      disposed = true;
      tlRef.current?.dispose();
      try {
        mapRef.current?.remove();
      } catch {
        /* torn down */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function buildLegend(a: IntroAssets) {
    const fill = barFillRef.current;
    const legend = barLegendRef.current;
    if (!fill || !legend) return;
    const exp = a.areas.focus.expected;
    const total = LEVEL_KEY.reduce((t, k) => t + (exp[k] ?? 0), 0) || 1;
    fill.innerHTML = "";
    legend.innerHTML = "";
    LEVEL_KEY.forEach((k, i) => {
      const seg = document.createElement("span");
      seg.style.width = `${((exp[k] ?? 0) / total) * 100}%`;
      seg.style.background = `rgb(${LEVEL_RGB[i].join(",")})`;
      fill.appendChild(seg);
      const row = document.createElement("div");
      row.className = "intro-legend-row";
      row.innerHTML = `<i style="background:rgb(${LEVEL_RGB[i].join(",")})"></i><span>${LEVEL_NAME[i]}</span><b>${fmt(exp[k] ?? 0)}</b>`;
      legend.appendChild(row);
    });
  }

  function buildTowns(a: IntroAssets) {
    const wrap = townsRef.current;
    if (!wrap) return;
    wrap.innerHTML = "";
    townEls.current = a.areas.areas.map((t) => {
      const el = document.createElement("div");
      el.className = "intro-town";
      el.innerHTML = `<b>~${fmt(t.severe)}</b><span>${t.name}</span>`;
      wrap.appendChild(el);
      return el;
    });
  }

  // ---- camera, radar plate, registered imagery plate: every frame ----------
  function drive(ms: number) {
    const map = mapRef.current;
    if (!map) return;
    if (ms < B.title.t0) map.jumpTo(cameraAt(ms));
    const place = (el: HTMLElement | null, box: readonly number[]) => {
      if (!el || el.hidden) return;
      const p0 = map.project([box[0], box[3]]);
      const p1 = map.project([box[2], box[1]]);
      el.style.transform = `translate(${p0.x}px,${p0.y}px)`;
      el.style.width = `${p1.x - p0.x}px`;
      el.style.height = `${p1.y - p0.y}px`;
    };
    place(radarRef.current, assetsRef.current?.radar.manifest.bbox4326 ?? [0, 0, 0, 0]);
    place(plateRef.current, OLDFORT_IMG_BOUNDS);
    if (progRef.current) progRef.current.style.transform = `scaleX(${ms / TOTAL})`;
  }

  // ---- tracks ---------------------------------------------------------------
  function addTracks(tl: Timeline, a: IntroAssets) {
    const show = (el: HTMLElement | SVGElement | null, v: boolean) => {
      if (el) (el as HTMLElement).hidden = !v;
    };
    const f = a.areas.focus;
    const tot = a.areas.total;
    const west = lonsRef.current[0] - SWEEP_SOFT;
    const east = lonsRef.current[lonsRef.current.length - 1] + SWEEP_SOFT * 2;
    const SWEEP_T0 = B.read.t0 + 450;
    const SWEEP_T1 = B.read.t1 - 1500;

    // NC outline: in over the descent, held under the radar, out on the plunge
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const map = mapRef.current;
        if (!map || !map.getLayer("nc-line")) return;
        const o =
          easing.out(clamp01(ms / 1500)) * (1 - clamp01((ms - B.plunge.t0) / 600));
        map.setPaintProperty("nc-line", "line-opacity", 0.95 * o);
        map.setPaintProperty("nc-fill", "fill-opacity", 0.1 * o);
      },
    });

    // radar timelapse + the archive time of the frame on screen, set large
    tl.add({
      start: 0,
      end: B.plunge.t0 + 300,
      update: (_p, { ms }) => {
        const wrap = radarRef.current;
        const imgs = radarImgs.current;
        const active = ms >= 250 && ms <= B.plunge.t0 + 300;
        show(wrap, active);
        show(stampRef.current, active);
        if (!active || !wrap || !imgs.length) return;
        const fade = clamp01((ms - 250) / 450) * (1 - clamp01((ms - (B.storm.t1 - 200)) / 500));
        wrap.style.opacity = String(0.94 * fade);
        const local = clamp01((ms - 400) / (B.storm.t1 - 500));
        const i = Math.min(imgs.length - 1, Math.floor(local * imgs.length));
        for (let k = 0; k < imgs.length; k++) imgs[k].style.opacity = k === i ? "1" : "0";
        const st = radarStamp(a.radar.manifest.frames[i].at);
        if (stampDayRef.current) stampDayRef.current.textContent = st.day;
        if (stampTimeRef.current) stampTimeRef.current.textContent = st.time;
        if (stampRef.current) stampRef.current.style.opacity = String(fade);
      },
    });

    // before / after: a plate registered to the map, wiped left to right
    tl.add({
      start: B.plunge.t1 - 500,
      end: B.widen.t0 + 500,
      update: (_p, { ms }) => {
        const plate = plateRef.current;
        if (!plate) return;
        const active = ms >= B.plunge.t1 - 500 && ms <= B.widen.t0 + 500;
        show(plate, active);
        if (!active) {
          if (tagBeforeRef.current) tagBeforeRef.current.style.opacity = "0";
          if (tagAfterRef.current) tagAfterRef.current.style.opacity = "0";
          return;
        }
        const inA = clamp01((ms - (B.plunge.t1 - 500)) / 380);
        const outA = 1 - clamp01((ms - B.widen.t0) / 420); // hands over to the deck imagery
        plate.style.opacity = String(Math.min(inA, outA));
        const wp = easing.inOut(clamp01((ms - (B.reveal.t0 + 450)) / 2300));
        if (afterRef.current) afterRef.current.style.clipPath = `inset(0 ${(1 - wp) * 100}% 0 0)`;
        if (dividerRef.current) {
          dividerRef.current.style.left = `${wp * 100}%`;
          dividerRef.current.style.opacity = wp > 0.002 && wp < 0.998 ? "1" : "0";
        }
        // the wipe uncovers "after" from the left edge; "before" is what is
        // still showing on the right, so each tag sits on its own side
        if (tagAfterRef.current)
          tagAfterRef.current.style.opacity = String(clamp01((wp - 0.14) / 0.2) * outA);
        if (tagBeforeRef.current)
          tagBeforeRef.current.style.opacity = String(inA * (1 - clamp01((wp - 0.72) / 0.2)));
      },
    });

    // the imagery as deck layers (wide tile + sharp still), the sweep, the
    // structures, the rise and the review recolour: one track owns anim state
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const s = anim.current;
        const inImg = clamp01((ms - (B.widen.t0 - 200)) / 500);
        const outAll = 1 - clamp01((ms - (B.region.t0 - 160)) / 160);
        // the imagery steps back twice: a little as the read starts (so the
        // marks carry), then further as the levels rise
        const dim =
          0.38 * clamp01((ms - (B.read.t0 + 200)) / 700) + 0.62 * clamp01((ms - B.rise.t0) / 1800);
        s.wideA = inImg * outAll * lerp(1, 0.5, dim);
        s.sharpA = inImg * outAll * lerp(1, 0.5, dim) * (1 - clamp01((ms - B.rise.t0) / 900));
        s.desat = dim;
        s.sweepLon =
          ms < SWEEP_T0
            ? -Infinity
            : ms >= SWEEP_T1
              ? Infinity
              : lerp(west, east, clamp01((ms - SWEEP_T0) / (SWEEP_T1 - SWEEP_T0)));
        s.dotA = (ms >= SWEEP_T0 ? 1 : 0) * (1 - clamp01((ms - (B.rise.t0 + 500)) / 900)) * outAll;
        s.polyA = clamp01((ms - (B.read.t1 - 700)) / 700) * outAll;
        s.rise = clamp01((ms - (B.rise.t0 + 250)) / 2700);
        s.reviewK =
          easing.inOut(clamp01((ms - (B.review.t0 + 200)) / 700)) * outAll;
        const rg = clamp01((ms - (B.region.t0 + 250)) / 400) * (1 - clamp01((ms - (B.title.t0 - 250)) / 250));
        s.colA = rg;
        s.colRise = clamp01((ms - (B.region.t0 + 450)) / 2200);
        pushLayers();

        // the sweep line itself, in screen space at the sweep's longitude
        const line = sweepRef.current;
        const map = mapRef.current;
        const sweeping = ms >= SWEEP_T0 && ms < SWEEP_T1;
        show(line, sweeping);
        if (sweeping && line && map) {
          const x = map.project([s.sweepLon, cameraAt(ms).center[1]]).x;
          line.style.transform = `translateX(${x.toFixed(1)}px)`;
        }
      },
    });

    // darkening scrims so type stays legible over imagery (edges only)
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        if (!scrimRef.current) return;
        const k = clamp01((ms - B.plunge.t0) / 800) * (1 - clamp01((ms - (B.title.t0 - 200)) / 200));
        scrimRef.current.style.opacity = String(0.78 + 0.22 * k);
      },
    });

    // captions: words rise in one after another, the block cuts out together
    let lastCap = -1;
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const wrap = capRef.current;
        const text = capTextRef.current;
        const sub = capSubRef.current;
        if (!wrap || !text || !sub) return;
        const i = capsRef.current.findIndex((c) => ms >= c.t0 && ms < c.t1);
        if (i < 0) {
          wrap.style.opacity = "0";
          lastCap = -1;
          return;
        }
        const c = capsRef.current[i];
        if (i !== lastCap) {
          text.innerHTML = c.text
            .split(" ")
            .map((w) => `<span>${w}</span>`)
            .join(" ");
          sub.textContent = c.sub ?? "";
          lastCap = i;
        }
        const local = ms - c.t0;
        wrap.style.opacity = String(1 - clamp01((ms - (c.t1 - 240)) / 240));
        const words = text.children;
        for (let w = 0; w < words.length; w++) {
          const k = easing.out(clamp01((local - w * 70) / 460));
          const el = words[w] as HTMLElement;
          el.style.opacity = String(k);
          el.style.transform = `translateY(${((1 - k) * 0.42).toFixed(3)}em)`;
        }
        sub.style.opacity = String(0.92 * clamp01((local - words.length * 70 - 120) / 400));
      },
    });

    // the figures: every number is read from the baked pipeline output
    const upto = (target: number, ms: number, t0: number, dur = 950) =>
      target * easing.out(clamp01((ms - t0) / dur));
    function statsAt(ms: number): StatView | null {
      const fade = (b: { t0: number; t1: number }, lead = 250) =>
        clamp01((ms - (b.t0 + lead)) / 350) * (1 - clamp01((ms - (b.t1 - 260)) / 260));
      if (ms >= B.read.t0 && ms < B.read.t1) {
        const s = anim.current.sweepLon;
        let n = 0;
        if (s === Infinity) n = lonsRef.current.length;
        else if (s !== -Infinity) {
          // how many structures the line has passed (binary search)
          let lo = 0;
          let hi = lonsRef.current.length;
          while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (lonsRef.current[mid] <= s) lo = mid + 1;
            else hi = mid;
          }
          n = lo;
        }
        const rows =
          ms >= SWEEP_T1 + 80
            ? [
                { v: fmt(f.assessed), l: "read from imagery" },
                { v: `${Math.round(f.runtime_s ?? 0)} s`, l: "assessment run time" },
              ]
            : [];
        return { big: fmt(n), label: "structures found", sub: `${f.name} · ${f.county} County`, rows, bar: -1, alpha: fade(B.read, 300) };
      }
      if (ms >= B.rise.t0 && ms < B.rise.t1) {
        const t0 = B.rise.t0 + 500;
        const rows =
          f.displaced != null && ms >= B.rise.t0 + 2900
            ? [{ v: `~${fmt(upto(f.displaced, ms, B.rise.t0 + 2900, 700))}`, l: "people likely displaced" }]
            : [];
        return {
          big: `~${fmt(upto(f.severe, ms, t0))}`,
          label: "likely Major or Destroyed",
          sub: `80% range ${fmt(f.severe_lo)} to ${fmt(f.severe_hi)}`,
          rows,
          bar: easing.out(clamp01((ms - (B.rise.t0 + 900)) / 1400)),
          alpha: fade(B.rise),
        };
      }
      if (ms >= B.review.t0 && ms < B.review.t1)
        return {
          big: fmt(upto(f.review, ms, B.review.t0 + 450)),
          label: "calls sent to a person",
          sub: `of ${fmt(f.assessed)} structures assessed`,
          rows: [],
          bar: -1,
          alpha: fade(B.review),
        };
      if (ms >= B.region.t0 && ms < B.region.t1) {
        const t0 = B.region.t0 + 700;
        return {
          big: fmt(upto(tot.structures, ms, t0, 1200)),
          label: "structures",
          sub: `across ${tot.areas} towns in western North Carolina`,
          rows: [
            { v: `~${fmt(upto(tot.severe, ms, t0 + 500, 1000))}`, l: "likely Major or Destroyed" },
            { v: fmt(upto(tot.review, ms, t0 + 900, 1000)), l: "awaiting human review" },
          ],
          bar: -1,
          alpha: fade(B.region, 500),
        };
      }
      return null;
    }
    let lastRows = "";
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const wrap = statRef.current;
        if (!wrap) return;
        const v = statsAt(ms);
        if (!v) {
          wrap.style.opacity = "0";
          return;
        }
        wrap.style.opacity = String(v.alpha);
        if (statBigRef.current && statBigRef.current.textContent !== v.big) statBigRef.current.textContent = v.big;
        if (statLabelRef.current && statLabelRef.current.textContent !== v.label) statLabelRef.current.textContent = v.label;
        if (statSubRef.current) statSubRef.current.textContent = v.sub ?? "";
        const rows = v.rows.map((r) => `<div><b>${r.v}</b><span>${r.l}</span></div>`).join("");
        if (statRowsRef.current && rows !== lastRows) {
          statRowsRef.current.innerHTML = rows;
          lastRows = rows;
        }
        show(barRef.current, v.bar >= 0);
        if (v.bar >= 0 && barFillRef.current && barLegendRef.current) {
          barFillRef.current.style.clipPath = `inset(0 ${(1 - v.bar) * 100}% 0 0)`;
          barLegendRef.current.style.opacity = String(clamp01(v.bar * 1.6 - 0.4));
        }
      },
    });

    // telemetry: where the camera is, and whose data is on screen
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const wrap = telRef.current;
        const coord = telCoordRef.current;
        const tag = telTagRef.current;
        if (!wrap || !coord || !tag) return;
        wrap.style.opacity = String(0.9 * clamp01(ms / 500) * (1 - clamp01((ms - (B.title.t0 - 220)) / 200)));
        if (brandRef.current)
          brandRef.current.style.opacity = String(clamp01((ms - 300) / 500) * (1 - clamp01((ms - (B.title.t0 - 220)) / 200)));
        const b = beatAt(ms);
        const c = cameraAt(ms).center;
        coord.textContent = fmtCoord(c[0], c[1]);
        tag.textContent =
          b.id === "storm"
            ? "NEXRAD · Iowa Environmental Mesonet archive"
            : b.id === "plunge"
              ? "Old Fort · McDowell County"
              : b.id === "reveal" || b.id === "widen"
                ? "Maxar Open Data · CC BY-NC 4.0"
                : b.id === "read"
                  ? "FEMA USA Structures · OpenStreetMap · USACE NSI"
                  : b.id === "rise"
                    ? "Imagery evidence fused per structure"
                    : b.id === "review"
                      ? "Human review queue"
                      : "NC OneMap · NOAA ERI · Maxar Open Data";
        if (noteRef.current)
          noteRef.current.style.opacity = String(
            0.85 * clamp01((ms - B.read.t0) / 500) * (1 - clamp01((ms - (B.title.t0 - 220)) / 200)),
          );
      },
    });

    // the cut to the region: a dark frame and one scan line, the logo's motif
    tl.add({
      start: 0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const cut = cutRef.current;
        const scan = scanRef.current;
        if (!cut || !scan) return;
        const local = ms - B.region.t0;
        const on = local >= -170 && local <= 520;
        show(cut, on);
        show(scan, on);
        if (!on) return;
        cut.style.opacity = String(local < 0 ? clamp01((local + 170) / 150) : 1 - clamp01((local - 40) / 440));
        const p = clamp01((local + 60) / 480);
        scan.style.transform = `translateY(${(p * 100).toFixed(2)}vh)`;
        scan.style.opacity = p > 0.01 && p < 0.99 ? "0.9" : "0";
      },
    });

    // town labels ride the top of each column
    tl.add({
      start: B.region.t0,
      end: B.title.t0,
      update: (_p, { ms }) => {
        const wrap = townsRef.current;
        const map = mapRef.current;
        const active = ms >= B.region.t0 + 200 && ms < B.title.t0;
        show(wrap, active);
        if (!active || !wrap || !map) return;
        const cam = cameraAt(ms);
        const n = a.areas.areas.length;
        const out = 1 - clamp01((ms - (B.title.t0 - 250)) / 250);
        a.areas.areas.forEach((t, i) => {
          const el = townEls.current[i];
          if (!el) return;
          const k = easing.out(clamp01(anim.current.colRise * 1.6 - (i / n) * 0.6));
          const p = map.project(t.center);
          const mpp = (40075016.686 * Math.cos((t.center[1] * Math.PI) / 180)) / (512 * 2 ** cam.zoom);
          const h = ((t.severe * COLUMN_M * k) / mpp) * Math.sin((cam.pitch * Math.PI) / 180);
          el.style.transform = `translate(${p.x.toFixed(1)}px, ${(p.y - h - 14).toFixed(1)}px) translate(-50%, -100%)`;
          el.style.opacity = String(clamp01(k * 2.2 - 0.6) * out);
        });
      },
    });

    // title card
    tl.add({
      start: B.title.t0,
      end: TOTAL,
      update: (_p, { ms }) => {
        const active = ms >= B.title.t0;
        show(titleRef.current, active);
        if (!active) return;
        const local = ms - B.title.t0;
        const k = easing.out(clamp01((local - 120) / 620));
        if (markRef.current) {
          markRef.current.style.opacity = String(k);
          markRef.current.style.transform = `translateY(${((1 - k) * 10).toFixed(2)}px)`;
        }
        // the two scan rings draw themselves, then one ping travels outward
        const ring = (el: SVGCircleElement | null, r: number, delay: number) => {
          if (!el) return;
          const c = 2 * Math.PI * r;
          el.style.strokeDasharray = String(c);
          el.style.strokeDashoffset = String(c * (1 - easing.inOut(clamp01((local - delay) / 900))));
        };
        ring(ringARef.current, 20, 500);
        ring(ringBRef.current, 38, 800);
        if (ringCRef.current) {
          const pp = clamp01((local - 1700) / 1500);
          ringCRef.current.setAttribute("r", String(38 + 46 * easing.out(pp)));
          ringCRef.current.style.opacity = String(0.7 * (1 - pp) * (pp > 0 ? 1 : 0));
        }
        const up = (el: HTMLElement | null, delay: number) => {
          if (!el) return;
          const q = easing.out(clamp01((local - delay) / 560));
          el.style.opacity = String(q);
          el.style.transform = `translateY(${((1 - q) * 12).toFixed(2)}px)`;
        };
        up(wordRef.current, 700);
        up(descRef.current, 1150);
        up(discRef.current, 1700);
      },
    });
  }

  return (
    <div className="intro-stage">
      <div ref={hostRef} className="intro-map" />
      <div ref={radarRef} className="intro-radar" hidden />

      <div ref={plateRef} className="intro-plate" hidden>
        <img ref={beforeRef} className="intro-plate-img" alt="" />
        <div ref={afterRef} className="intro-plate-img intro-plate-after" />
        <div ref={dividerRef} className="intro-plate-divider" />
      </div>
      <div ref={sweepRef} className="intro-sweep" hidden />

      <div ref={scrimRef} className="intro-scrim" />
      <div ref={townsRef} className="intro-towns" hidden />

      <div className="intro-tags">
        <span ref={tagAfterRef} />
        <span ref={tagBeforeRef} />
      </div>

      <div ref={stampRef} className="intro-stamp" hidden>
        <div ref={stampDayRef} className="intro-stamp-day" />
        <div ref={stampTimeRef} className="intro-stamp-time" />
      </div>

      <div ref={brandRef} className="intro-brand">
        <svg viewBox="0 0 300 96" aria-hidden="true">
          <path d={NC_MARK} />
        </svg>
        <span>NC Recon</span>
      </div>

      <div ref={telRef} className="intro-tel">
        <div ref={telCoordRef} className="intro-tel-coord" />
        <div ref={telTagRef} className="intro-tel-tag" />
      </div>

      <div ref={capRef} className="intro-cap">
        <div ref={capTextRef} className="intro-cap-text" />
        <div ref={capSubRef} className="intro-cap-sub" />
      </div>

      <div ref={statRef} className="intro-stat">
        <div ref={statBigRef} className="intro-stat-big" />
        <div ref={statLabelRef} className="intro-stat-label" />
        <div ref={statSubRef} className="intro-stat-sub" />
        <div ref={barRef} className="intro-bar" hidden>
          <div ref={barFillRef} className="intro-bar-fill" />
          <div ref={barLegendRef} className="intro-legend" />
        </div>
        <div ref={statRowsRef} className="intro-stat-rows" />
      </div>

      <div ref={noteRef} className="intro-note">
        Decision support. Estimates are not yet validated. Verify on the ground.
      </div>

      <div ref={cutRef} className="intro-cut" hidden />
      <div ref={scanRef} className="intro-scan" hidden />

      <div ref={titleRef} className="intro-title" hidden>
        <svg ref={markRef} className="intro-title-mark" viewBox="-12 -46 324 190" aria-hidden="true">
          <path d={NC_MARK} className="intro-title-state" />
          <circle ref={ringARef} cx="198.09" cy="28.24" r="20" className="intro-title-ring" />
          <circle ref={ringBRef} cx="198.09" cy="28.24" r="38" className="intro-title-ring" />
          <circle ref={ringCRef} cx="198.09" cy="28.24" r="38" className="intro-title-ring intro-title-ping" />
          <circle cx="198.09" cy="28.24" r="6" className="intro-title-dot" />
        </svg>
        <div ref={wordRef} className="intro-title-word">
          NC Recon
        </div>
        <div ref={descRef} className="intro-title-desc">
          Disaster damage decision support for North Carolina emergency management.
        </div>
        <div ref={discRef} className="intro-title-disc">
          Not an official FEMA or NC Emergency Management damage assessment. Accuracy is not
          yet validated: every call is a lead to verify on the ground.
        </div>
      </div>

      <div className="intro-progress">
        <div ref={progRef} />
      </div>
    </div>
  );
});

export default Stage;
