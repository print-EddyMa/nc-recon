/**
 * Phase H - the storyboard as data. Nine beats, one continuous ~17.8s
 * sequence. Camera keyframes are interpolated per-segment with a per-segment
 * easing curve (sharp for the attention snaps, smooth for the reveals).
 *
 * Geography constants MUST stay in lockstep with scripts/demo_fetch.mjs.
 */
import { easing, lerp, clamp01, type Ease } from "./timeline";

export const NC_CENTER: [number, number] = [-79.2, 35.55];
/** Old Fort, McDowell County - the B3/B4/B5 camera (matches demo_fetch.mjs). */
export const OLDFORT: [number, number] = [-82.1804, 35.6293];

/**
 * Phase J - god's-eye geography annotations layered on the existing beats
 * (no new beats, no new runtime; §CAC_VIDEO_SCRIPT.md "do not extend it").
 * All flat/annotation-style per DESIGN.md - this is a briefing overlay, not a
 * photoreal render.
 */
// B6 network - response staging cities converging on Old Fort, McDowell
// County. Real NC cities, plausible staging distance.
export const CONVERGE_FROM: { name: string; pos: [number, number] }[] = [
  { name: "Asheville", pos: [-82.5515, 35.5951] },
  { name: "Hickory", pos: [-81.3412, 35.7344] },
  { name: "Charlotte", pos: [-80.8431, 35.2271] },
];

/**
 * Geographic bounds of the stitched oldfort_pre/post.jpg. MUST match the
 * grid math in scripts/demo_fetch.mjs (z17, SHOT_W×SHOT_H around OLDFORT).
 * Used as the deck.gl BitmapLayer `bounds` so the imagery stays registered to
 * the camera through the B5 push-in.
 */
function imgBounds(lon: number, lat: number, z: number, w: number, h: number) {
  const world = 256 * 2 ** z;
  const cx = ((lon + 180) / 360) * world;
  const latR = (lat * Math.PI) / 180;
  const cy = ((1 - Math.asinh(Math.tan(latR)) / Math.PI) / 2) * world;
  const lonOf = (px: number) => (px / world) * 360 - 180;
  const latOf = (py: number) =>
    (Math.atan(Math.sinh(Math.PI * (1 - (2 * py) / world))) * 180) / Math.PI;
  return {
    west: lonOf(cx - w / 2),
    east: lonOf(cx + w / 2),
    north: latOf(cy - h / 2),
    south: latOf(cy + h / 2),
  };
}
const _b = imgBounds(OLDFORT[0], OLDFORT[1], 17, 3200, 2000);
/** [west, south, east, north] for deck.gl BitmapLayer */
export const OLDFORT_IMG_BOUNDS: [number, number, number, number] = [
  _b.west,
  _b.south,
  _b.east,
  _b.north,
];

export interface Cam {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface Beat {
  id: string;
  name: string;
  /** ms, absolute */
  t0: number;
  t1: number;
}

// --- beat boundaries ------------------------------------------------------- //
// Phase I retime (§I7 - deliberate pacing contrast, same ~17.8s total):
// the two HELD beats breathe longer (reveal +300, title +400); the time is
// taken back from the faster analysis/transition beats (radar -300, network
// -200, history -200). The two URGENT beats (descent, snap) are untouched.
//
// Post-Phase-I: snap widened 1800 → 2400ms (taken from reveal, which holds
// under the full-frame before/after wipe and can spare it). A z6→z16 plunge in
// ~1s outruns MapLibre's per-frame vector-tile upload even with every tile
// already cache-resident - the frame flew over bare ground. 2400ms gives the
// upload pipeline enough headroom that the swoop stays painted.
export const BEATS: Beat[] = [
  { id: "descent", name: "Descent", t0: 0, t1: 2000 },
  { id: "radar", name: "Helene radar timelapse", t0: 2000, t1: 4900 },
  { id: "snap", name: "Snap to western NC", t0: 4900, t1: 7300 },
  { id: "reveal", name: "Before / after", t0: 7300, t1: 9200 },
  { id: "extrude", name: "Damage model rises", t0: 9200, t1: 11200 },
  { id: "network", name: "Statewide sensor network", t0: 11200, t1: 13200 },
  { id: "flood", name: "Flood risk flash", t0: 13200, t1: 14400 },
  { id: "history", name: "Disaster history scrub", t0: 14400, t1: 16200 },
  { id: "title", name: "Title card", t0: 16200, t1: 17800 },
];
export const TOTAL = BEATS[BEATS.length - 1].t1;

export const beatAt = (ms: number) =>
  BEATS.find((b) => ms >= b.t0 && ms < b.t1) ?? BEATS[BEATS.length - 1];

/** local 0..1 progress within a beat */
export const within = (ms: number, b: Beat) =>
  clamp01((ms - b.t0) / (b.t1 - b.t0));

// --- camera path -------------------------------------------------------- //
interface Seg {
  until: number;
  from: Cam;
  to: Cam;
  ease: Ease;
}

const STATEWIDE: Cam = { center: NC_CENTER, zoom: 6.32, pitch: 0, bearing: 0 };
// B2 eases back and drifts SW toward the storm's approach so the wide NEXRAD
// plate reads in and out over GA / TN / SC / VA / the Atlantic, NC still central.
const STORM_WIDE: Cam = {
  center: [-80.5, 35.25],
  zoom: 6.02,
  pitch: 0,
  bearing: 0,
};
const START: Cam = { center: [-80.6, 37.7], zoom: 4.7, pitch: 0, bearing: 0 };
const OF_FLAT: Cam = { center: OLDFORT, zoom: 16, pitch: 0, bearing: 0 };
// Phase J - steeper pitch + wider bearing swing than the original 52°/-17°:
// sells the 3-D extrusion more clearly at the cost of nothing else in the
// shot - the dark band at the very top of frame near peak pitch (the camera
// looking past the finite stitched Maxar image into the bare basemap) is
// already present at 52°/-17°, confirmed by testing both side by side; this
// widens it slightly, not a new artifact.
const OF_3D: Cam = { center: OLDFORT, zoom: 16.4, pitch: 58, bearing: -26 };
const STATEWIDE_OUT: Cam = {
  center: NC_CENTER,
  zoom: 6.28,
  pitch: 0,
  bearing: 0,
};

// `until` MUST equal the matching BEATS[].t1 or the camera desyncs from the beats.
const SEGS: Seg[] = [
  // B1 descent - fast off the line, eases to rest
  { until: 2000, from: START, to: STATEWIDE, ease: easing.outExpo },
  // B2 radar - gentle ease-back + SW drift so the storm fills in from the edges
  { until: 4900, from: STATEWIDE, to: STORM_WIDE, ease: easing.out },
  // B3 snap - fast swoop that decelerates hard into Old Fort (arrives ~45%
  // through the now-wider beat, leaving room for the tiles to paint and the
  // imagery to resolve before the wipe)
  { until: 7300, from: STORM_WIDE, to: OF_FLAT, ease: easing.out },
  // B4 before/after - hold
  { until: 9200, from: OF_FLAT, to: OF_FLAT, ease: easing.linear },
  // B5 extrude - smooth push into 3-D so the eye tracks the rise
  { until: 11200, from: OF_FLAT, to: OF_3D, ease: easing.inOut },
  // B6 pull back - fast out, settle
  { until: 13200, from: OF_3D, to: STATEWIDE_OUT, ease: easing.outQuint },
  // B7 flood flash - hold
  { until: 14400, from: STATEWIDE_OUT, to: STATEWIDE_OUT, ease: easing.linear },
  // B8 history - hold (the scrub is a DOM strip)
  { until: 16200, from: STATEWIDE_OUT, to: STATEWIDE_OUT, ease: easing.linear },
  // B9 title - hold (map is hidden)
  { until: 17800, from: STATEWIDE_OUT, to: STATEWIDE_OUT, ease: easing.linear },
];

const mixCam = (a: Cam, b: Cam, t: number): Cam => ({
  center: [
    lerp(a.center[0], b.center[0], t),
    lerp(a.center[1], b.center[1], t),
  ],
  zoom: lerp(a.zoom, b.zoom, t),
  pitch: lerp(a.pitch, b.pitch, t),
  bearing: lerp(a.bearing, b.bearing, t),
});

export function cameraAt(ms: number): Cam {
  let t0 = 0;
  for (const s of SEGS) {
    if (ms <= s.until || s === SEGS[SEGS.length - 1]) {
      const p = s.ease(clamp01((ms - t0) / (s.until - t0)));
      return mixCam(s.from, s.to, p);
    }
    t0 = s.until;
  }
  return SEGS[SEGS.length - 1].to;
}
