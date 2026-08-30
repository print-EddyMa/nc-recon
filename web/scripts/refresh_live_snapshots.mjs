// Seed / refresh the committed offline snapshots the Live Monitor falls back to
// when the network is unavailable (so the demo works on a plane).
//
//   node scripts/refresh_live_snapshots.mjs
//
// Writes public/data/live/{usgs,gdacs}_snapshot.geojson. FIRMS is not snapshotted
// (needs a key); Sentinel-1 is a stub.
import { writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "public", "data", "live");

const USGS =
  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson";
const GDACS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH";

async function getJSON(url) {
  const r = await fetch(url, { signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

function usgsToSnapshot(raw) {
  return {
    type: "FeatureCollection",
    generated: Date.now(),
    features: (raw.features ?? [])
      .filter((f) => f.geometry?.type === "Point")
      .map((f) => {
        const p = f.properties ?? {};
        const mag = Number(p.mag) || 0;
        return {
          type: "Feature",
          geometry: f.geometry,
          properties: {
            id: String(f.id ?? p.code),
            source: "usgs",
            hazard_type: "earthquake",
            title: String(p.place ?? "Earthquake"),
            magnitude: mag,
            severity: mag >= 6.5 ? 3 : mag >= 5.5 ? 2 : mag >= 5 ? 1 : 0,
            alert: p.alert ?? null,
            time: Number(p.time) || null,
          },
        };
      }),
  };
}

const GDACS_TYPE = { EQ: "earthquake", TC: "cyclone", FL: "flood", VO: "volcano", WF: "wildfire", DR: "other" };

function gdacsToSnapshot(raw) {
  return {
    type: "FeatureCollection",
    generated: Date.now(),
    features: (raw.features ?? [])
      .filter((f) => f.geometry?.type === "Point")
      .map((f) => {
        const p = f.properties ?? {};
        const et = String(p.eventtype ?? "").toUpperCase();
        const lvl = String(p.alertlevel ?? "").toLowerCase();
        return {
          type: "Feature",
          geometry: f.geometry,
          properties: {
            id: String(p.eventid ?? f.id),
            source: "gdacs",
            hazard_type: GDACS_TYPE[et] ?? "other",
            title: String(p.name ?? p.htmldescription ?? p.eventname ?? "Hazard"),
            severity: lvl === "red" ? 3 : lvl === "orange" ? 2 : 1,
            alert: p.alertlevel ?? null,
            time: p.fromdate ? Date.parse(String(p.fromdate)) : null,
          },
        };
      }),
  };
}

await mkdir(OUT, { recursive: true });

for (const [name, url, xform] of [
  ["usgs_snapshot.geojson", USGS, usgsToSnapshot],
  ["gdacs_snapshot.geojson", GDACS, gdacsToSnapshot],
]) {
  try {
    const snap = xform(await getJSON(url));
    await writeFile(join(OUT, name), JSON.stringify(snap));
    console.log(`wrote ${name}: ${snap.features.length} features`);
  } catch (e) {
    console.error(`FAILED ${name}: ${e.message}`);
  }
}
