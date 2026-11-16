/**
 * Offline packs (pipeline ops/offline, GET /ops/offline): whether this server
 * runs with no internet, and whether a local USGS topo basemap is packed.
 *
 * Detected once at start-up and cached for the session; any failure means
 * "online" (fail open), so a missing route never blanks the map.
 *
 * Offline, the server's Content Security Policy is `connect-src 'self'`: the UI
 * must request nothing external (no CARTO basemap, no terrain tiles, no live
 * feeds), and those features say why they are unavailable instead.
 */
import { useEffect, useState } from "react";
import type { StyleSpecification } from "maplibre-gl";
import { API_URL } from "./catalog";

export interface OfflineStatus {
  offline: boolean;
  basemap: {
    available: boolean;
    style_url: string | null;
    minzoom?: number;
    maxzoom?: number;
    bounds?: [number, number, number, number];
    attribution?: string;
    license?: string;
    tiles?: number;
    areas?: string[];
  };
  packs: { area: string; event_id: string; pack_created_utc: string; imported_utc: string }[];
  /** what does not work offline, in the server's words ([] when online) */
  unavailable_offline: string[];
  /** labels made offline stay on this laptop: no sync */
  labels: string;
}

let cached: OfflineStatus | null | undefined;
let pending: Promise<OfflineStatus | null> | null = null;

/** The server's offline status, fetched once; null = online or unknown. */
export function loadOffline(): Promise<OfflineStatus | null> {
  if (cached !== undefined) return Promise.resolve(cached);
  if (!API_URL) return Promise.resolve((cached = null));
  pending ??= fetch(`${API_URL}/ops/offline`, { signal: AbortSignal.timeout(4000) })
    .then((r) => (r.ok ? (r.json() as Promise<OfflineStatus>) : null))
    .catch(() => null)
    .then((s) => (cached = s && typeof s.offline === "boolean" ? s : null));
  return pending;
}

/** The cached status as React state: undefined until known, null when online. */
export function useOffline(): OfflineStatus | null | undefined {
  const [s, setS] = useState<OfflineStatus | null | undefined>(cached);
  useEffect(() => {
    let live = true;
    void loadOffline().then((v) => live && setS(v));
    return () => {
      live = false;
    };
  }, []);
  return s;
}

export const isOffline = (s: OfflineStatus | null | undefined) => !!s?.offline;

/** The basemap style to use instead of CARTO, or null to use CARTO. Offline
 * with no packed basemap: a plain background, so nothing external is asked
 * for and the area's own imagery still draws on top. */
export function localStyle(
  s: OfflineStatus | null | undefined,
  theme: "light" | "dark",
): string | StyleSpecification | null {
  if (!s || !(s.offline || s.basemap?.available)) return null;
  if (s.basemap?.available && s.basemap.style_url) {
    const u = s.basemap.style_url;
    return /^https?:/.test(u) ? u : `${API_URL}${u}`;
  }
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": theme === "dark" ? "#0d1012" : "#e5e8e3" },
      },
    ],
  };
}

/** A failed request that the server refused because it is offline (503). */
export const isOfflineRefusal = (e: unknown) => /\b503\b/.test(e instanceof Error ? e.message : String(e));

/** Why something is off, in the server's words: the line that matches, or
 * all of them. */
export const offlineReason = (s: OfflineStatus | null | undefined, match?: RegExp) =>
  (match && s?.unavailable_offline?.find((x) => match.test(x))) ||
  (s?.unavailable_offline?.length ? s.unavailable_offline.join(" ") : "Not available offline.");
