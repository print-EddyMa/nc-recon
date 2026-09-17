/**
 * NEXRAD base-reflectivity radar from the Iowa Environmental Mesonet.
 *
 * Two products, both keyless, both standard raster tiles:
 *
 *  - LIVE loop: the current CONUS mosaic plus 11 five-minute-old snapshots
 *    (`nexrad-n0q-900913`, `-m05m` … `-m55m`) - a rolling one-hour animation.
 *  - ARCHIVED still: IEM's WMS-T time machine (`nexrad-n0r-wmst`), any 5-minute
 *    step from 1995-01-01 to today, consumed by MapLibre via `{bbox-epsg-3857}`.
 *    Used by the disaster-history timeline to show weather for events that
 *    predate any building-damage imagery.
 */

const IEM_TILE = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0";
const IEM_WMST = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi";

export interface RadarFrame {
  /** minutes before now: 0 = current mosaic */
  minutesAgo: number;
  /** wall-clock time this frame represents */
  at: number;
  /** short label, e.g. "12:35" */
  label: string;
  /** `{z}/{x}/{y}` template for a MapLibre raster source */
  tileUrl: string;
}

const hhmm = (d: Date) =>
  `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

/**
 * The live one-hour loop, oldest frame first. Recomputed each call so the
 * timestamps stay honest; the tile layers themselves are fixed IEM products.
 */
export function liveRadarFrames(now = Date.now()): RadarFrame[] {
  const frames: RadarFrame[] = [];
  for (let m = 55; m >= 0; m -= 5) {
    const layer = m === 0 ? "nexrad-n0q-900913" : `nexrad-n0q-900913-m${String(m).padStart(2, "0")}m`;
    const at = now - m * 60_000;
    frames.push({
      minutesAgo: m,
      at,
      label: hhmm(new Date(at)),
      tileUrl: `${IEM_TILE}/${layer}/{z}/{x}/{y}.png`,
    });
  }
  return frames;
}

/**
 * A single archived radar frame for `date`, as a MapLibre raster tile template.
 * IEM's WMS-T serves any 5-minute step back to 1995; MapLibre fills in the
 * bbox per tile. Returns null for dates outside the archive window.
 */
export function archivedRadarTiles(date: Date): string | null {
  const t = date.getTime();
  if (Number.isNaN(t) || t < Date.parse("1995-01-01") || t > Date.now()) return null;
  const iso = new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
  const q = new URLSearchParams({
    SERVICE: "WMS",
    VERSION: "1.1.1",
    REQUEST: "GetMap",
    LAYERS: "nexrad-n0r-wmst",
    STYLES: "",
    FORMAT: "image/png",
    TRANSPARENT: "TRUE",
    SRS: "EPSG:3857",
    WIDTH: "256",
    HEIGHT: "256",
    TIME: iso,
  });
  // MapLibre substitutes {bbox-epsg-3857}; keep it unencoded
  return `${IEM_WMST}?${q.toString()}&BBOX={bbox-epsg-3857}`;
}

export const RADAR_ATTRIBUTION =
  'Radar <a href="https://mesonet.agron.iastate.edu/" target="_blank" rel="noreferrer">Iowa Environmental Mesonet</a> / NWS NEXRAD';

// --- archived still, as one plain <img> over North Carolina ----------------- //
const R = 6378137;
const merc = (lon: number, lat: number): [number, number] => [
  (lon * Math.PI * R) / 180,
  R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)),
];
// NC bounding box in EPSG:3857, matches NC_BBOX in nc.ts
const [ncX0, ncY0] = merc(-84.55, 33.75);
const [ncX1, ncY1] = merc(-75.4, 36.7);

/**
 * A single archived NEXRAD image over North Carolina for `date` - a complete
 * WMS GetMap URL (real bbox, not a tile template), safe to drop straight into
 * an `<img src>`. Returns null outside the 1995→now archive window.
 */
export function archivedRadarImage(date: Date, w = 720, h = 460): string | null {
  const t = date.getTime();
  if (Number.isNaN(t) || t < Date.parse("1995-01-01") || t > Date.now()) return null;
  const iso = new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
  const q = new URLSearchParams({
    SERVICE: "WMS",
    VERSION: "1.1.1",
    REQUEST: "GetMap",
    LAYERS: "nexrad-n0r-wmst",
    STYLES: "",
    FORMAT: "image/png",
    TRANSPARENT: "TRUE",
    SRS: "EPSG:3857",
    WIDTH: String(w),
    HEIGHT: String(h),
    TIME: iso,
    BBOX: `${ncX0},${ncY0},${ncX1},${ncY1}`,
  });
  return `${IEM_WMST}?${q.toString()}`;
}

/** four evenly-spaced daytime timestamps for a given calendar day (UTC) */
export function dayFrames(dateStr: string): { iso: string; label: string }[] {
  const base = dateStr.slice(0, 10);
  return [0, 6, 12, 18].map((hr) => ({
    iso: `${base}T${String(hr).padStart(2, "0")}:00:00Z`,
    label: `${String(hr).padStart(2, "0")}:00Z`,
  }));
}
