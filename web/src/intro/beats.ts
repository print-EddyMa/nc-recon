/**
 * The intro sequence as data: nine beats, one ~38 s run.
 *
 * Camera constraint: the self-hosted basemap (public/demo/basemap/) only
 * holds the tiles the pitch demo's camera path crosses. This path stays on
 * them: the statewide descent and the plunge into Old Fort are the demo's own
 * (STORM_WIDE -> OF_FLAT), everything at Old Fort stays at zoom >= 14 (baked),
 * and the regional view is reached by a CUT at zoom < 9 (baked), never by a
 * continuous pull-back through the un-baked zoom 9 to 13 tiles west of town.
 */
import { easing, lerp, clamp01, type Ease } from "../demo/timeline";

export const NC_CENTER: [number, number] = [-79.2, 35.55];
export const OLDFORT: [number, number] = [-82.1804, 35.6293];

export interface Cam {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface Beat {
  id: string;
  name: string;
  t0: number;
  t1: number;
}

export const BEATS: Beat[] = [
  { id: "storm", name: "Helene on radar", t0: 0, t1: 5200 },
  { id: "plunge", name: "Plunge to Old Fort", t0: 5200, t1: 7800 },
  { id: "reveal", name: "Before / after", t0: 7800, t1: 12000 },
  { id: "widen", name: "The whole picture", t0: 12000, t1: 13800 },
  { id: "read", name: "The read", t0: 13800, t1: 18200 },
  { id: "rise", name: "Damage levels rise", t0: 18200, t1: 23200 },
  { id: "review", name: "What it is not sure of", t0: 23200, t1: 27400 },
  { id: "region", name: "Every assessed town", t0: 27400, t1: 33400 },
  { id: "title", name: "Title", t0: 33400, t1: 38000 },
];
export const TOTAL = BEATS[BEATS.length - 1].t1;
export const B = Object.fromEntries(BEATS.map((b) => [b.id, b])) as Record<string, Beat>;

export const beatAt = (ms: number) =>
  BEATS.find((b) => ms >= b.t0 && ms < b.t1) ?? BEATS[BEATS.length - 1];
export const within = (ms: number, b: Beat) => clamp01((ms - b.t0) / (b.t1 - b.t0));

// --- cameras ---------------------------------------------------------------
const START: Cam = { center: [-80.6, 37.7], zoom: 4.7, pitch: 0, bearing: 0 };
const STATEWIDE: Cam = { center: NC_CENTER, zoom: 6.32, pitch: 0, bearing: 0 };
const STORM_WIDE: Cam = { center: [-80.5, 35.25], zoom: 6.02, pitch: 0, bearing: 0 };
const OF_FLAT: Cam = { center: OLDFORT, zoom: 16, pitch: 0, bearing: 0 };
/**
 * The before / after stills are 3200 x 2000 px at zoom 17. Zoom the flat Old
 * Fort shot so they just cover the stage, whatever its size, so the wipe is
 * full-bleed AND registered to the map (call before the timeline is built).
 */
export function fitFlat(width: number, height: number) {
  if (!width || !height) return;
  OF_FLAT.zoom = Math.max(15.2, 17 + Math.log2(Math.max(width / 3200, height / 2000)) + 0.03);
}

/** the whole post-event image as a plate: centred on the image, not the town */
export const PLATE_CENTER: [number, number] = [-82.1816, 35.6222];
const OF_WIDE: Cam = { center: PLATE_CENTER, zoom: 14.22, pitch: 0, bearing: 0 };
const OF_READ: Cam = { center: PLATE_CENTER, zoom: 14.42, pitch: 0, bearing: 0 };
const OF_3D: Cam = { center: OLDFORT, zoom: 15.25, pitch: 58, bearing: -26 };
const OF_ORBIT: Cam = { center: OLDFORT, zoom: 15.42, pitch: 60, bearing: -50 };
const REGION_A: Cam = { center: [-82.4, 35.66], zoom: 8.6, pitch: 40, bearing: -8 };
const REGION_B: Cam = { center: [-82.4, 35.66], zoom: 8.84, pitch: 44, bearing: -14 };

interface Seg {
  until: number;
  from: Cam;
  to: Cam;
  ease: Ease;
}

const SEGS: Seg[] = [
  { until: 1800, from: START, to: STATEWIDE, ease: easing.outExpo },
  { until: B.storm.t1, from: STATEWIDE, to: STORM_WIDE, ease: easing.out },
  { until: B.plunge.t1, from: STORM_WIDE, to: OF_FLAT, ease: easing.out },
  { until: B.reveal.t1, from: OF_FLAT, to: OF_FLAT, ease: easing.linear },
  { until: B.widen.t1, from: OF_FLAT, to: OF_WIDE, ease: easing.inOut },
  { until: B.read.t1, from: OF_WIDE, to: OF_READ, ease: easing.linear },
  { until: B.read.t1 + 2400, from: OF_READ, to: OF_3D, ease: easing.inOut },
  { until: B.review.t1, from: OF_3D, to: OF_ORBIT, ease: easing.linear },
  // CUT (see the note at the top): the region is its own shot
  { until: B.region.t1, from: REGION_A, to: REGION_B, ease: easing.out },
  { until: TOTAL, from: REGION_B, to: REGION_B, ease: easing.linear },
];

const mix = (a: Cam, b: Cam, t: number): Cam => ({
  center: [lerp(a.center[0], b.center[0], t), lerp(a.center[1], b.center[1], t)],
  zoom: lerp(a.zoom, b.zoom, t),
  pitch: lerp(a.pitch, b.pitch, t),
  bearing: lerp(a.bearing, b.bearing, t),
});

export function cameraAt(ms: number): Cam {
  let t0 = 0;
  for (const s of SEGS) {
    if (ms < s.until || s === SEGS[SEGS.length - 1]) {
      return mix(s.from, s.to, s.ease(clamp01((ms - t0) / (s.until - t0))));
    }
    t0 = s.until;
  }
  return SEGS[SEGS.length - 1].to;
}

/** Geographic bounds of public/demo/oldfort_pre|post.jpg (z17, 3200x2000 around
 * OLDFORT): the same math as src/demo/beats.ts and scripts/demo_fetch.mjs. */
function imgBounds(lon: number, lat: number, z: number, w: number, h: number) {
  const world = 256 * 2 ** z;
  const cx = ((lon + 180) / 360) * world;
  const latR = (lat * Math.PI) / 180;
  const cy = ((1 - Math.asinh(Math.tan(latR)) / Math.PI) / 2) * world;
  const lonOf = (px: number) => (px / world) * 360 - 180;
  const latOf = (py: number) =>
    (Math.atan(Math.sinh(Math.PI * (1 - (2 * py) / world))) * 180) / Math.PI;
  return [lonOf(cx - w / 2), latOf(cy + h / 2), lonOf(cx + w / 2), latOf(cy - h / 2)] as [
    number,
    number,
    number,
    number,
  ];
}
/** [west, south, east, north] */
export const OLDFORT_IMG_BOUNDS = imgBounds(OLDFORT[0], OLDFORT[1], 17, 3200, 2000);
