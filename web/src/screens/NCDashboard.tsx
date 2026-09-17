import { useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer, GeoJsonLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import { prefersReducedMotion } from "../lib/motion";
import { resolved as resolvedTheme } from "../lib/theme";
import { useSettings } from "../lib/settings";
import { liveRadarFrames, RADAR_ATTRIBUTION } from "../lib/radar";
import LayerToggles, { type LayerRow } from "../components/map/LayerToggles";
import RadarControl from "../components/map/RadarControl";
import RankedList, { type RankedItem } from "../components/map/RankedList";
import FeatureCallout from "../components/map/FeatureCallout";
import KeyForm from "../components/ui/KeyForm";
import StatTile from "../components/ui/StatTile";
import {
  ncClimate,
  ncFloodForecasts,
  ncAlerts,
  ncStormTracks,
  ncCameras,
  ncClosures,
  ncStreamflow,
  ncFires,
  ncFemaHistory,
  ncAircraft,
  NC_CENTER,
  NC_BBOX,
  NC_SEV_COLOR,
  NC_SEV_LABEL,
  type NCResult,
  type NCPointFC,
  type NCGeomFC,
  type NCHistory,
} from "../lib/nc";

interface Props {
  onOpenAssess: () => void;
  onOpenAbout: () => void;
}

type LayerId =
  | "climate"
  | "gauge"
  | "flow"
  | "alert"
  | "storm"
  | "fire"
  | "camera"
  | "closure"
  | "aircraft";

const LAYER_META: Record<LayerId, { label: string; note: string }> = {
  climate: { label: "Current conditions", note: "ECONet + RAWS (CLOUDS API)" },
  gauge: {
    label: "River flood forecast",
    note: "NOAA NWPS / National Water Model",
  },
  flow: { label: "Streamflow", note: "USGS NWIS instantaneous values" },
  alert: { label: "Official alerts", note: "NWS watches & warnings" },
  storm: { label: "Active storm", note: "NHC cone & track" },
  fire: { label: "Active fire", note: "NASA FIRMS VIIRS" },
  camera: { label: "DOT cameras", note: "NCDOT DriveNC" },
  closure: { label: "Road closures", note: "NCDOT DriveNC" },
  aircraft: { label: "Live aircraft", note: "ADS-B via adsb.lol" },
};
const LAYER_ORDER: LayerId[] = [
  "gauge",
  "flow",
  "alert",
  "climate",
  "fire",
  "storm",
  "closure",
  "camera",
  "aircraft",
];

const DEFAULT_ON: Record<LayerId, boolean> = {
  climate: true,
  gauge: true,
  flow: false,
  alert: true,
  storm: true,
  fire: true,
  // off by default: statewide DOT closures are mostly routine and, at 100+
  // marks, they read as an emergency on an otherwise-calm map
  closure: false,
  camera: false,
  // off by default: hundreds of routine flights read as clutter on a calm day
  aircraft: false,
};

// cameras + closures + aircraft sit off the flood-severity ramp, so the
// legend names them individually
const CAMERA_RGB: [number, number, number] = [139, 148, 163];
const CLOSURE_RGB: [number, number, number] = [232, 137, 74];
const AIRCRAFT_RGB: [number, number, number] = [90, 150, 200];
const AIRCRAFT_MIL_RGB: [number, number, number] = [163, 116, 217];

const sevRGB = (s: number): [number, number, number] =>
  NC_SEV_COLOR[Math.max(-1, Math.min(3, s))];
const sevCSS = (s: number) => `rgb(${sevRGB(s).join(",")})`;

export default function NCDashboard({ onOpenAssess, onOpenAbout }: Props) {
  // start already framed on NC (shifted east to clear the left panel); the
  // fitBounds effect refines it once the container is measured
  const { containerRef, mapRef, ready, styleEpoch } = useMapLibre({
    center: [-78.7, 35.4],
    zoom: 6.7,
    autoTilt: true,
  });
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const reduced = prefersReducedMotion();
  const { settings, set } = useSettings();

  const [climate, setClimate] = useState<NCResult<NCPointFC> | null>(null);
  const [gauge, setGauge] = useState<NCResult<NCPointFC> | null>(null);
  const [alert, setAlert] = useState<NCResult<NCGeomFC> | null>(null);
  const [storm, setStorm] = useState<NCResult<NCGeomFC> | null>(null);
  const [camera, setCamera] = useState<NCResult<NCPointFC> | null>(null);
  const [closure, setClosure] = useState<NCResult<NCPointFC> | null>(null);
  const [flow, setFlow] = useState<NCResult<NCPointFC> | null>(null);
  const [fire, setFire] = useState<NCResult<NCPointFC> | null>(null);
  const [aircraft, setAircraft] = useState<NCResult<NCPointFC> | null>(null);
  const [history, setHistory] = useState<NCHistory | null>(null);
  const [selected, setSelected] = useState<{
    title: string;
    detail?: string;
    source: string;
    coord: [number, number];
    url?: string;
    linkLabel?: string;
  } | null>(null);
  const [riskOpen, setRiskOpen] = useState(false); // mobile bottom sheet
  // the layer switchboard is tall; on a phone it covers the map, so start it
  // collapsed there and let the user expand it
  const [layersOpen, setLayersOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth >= 768,
  );

  const [on, setOn] = useState<Record<LayerId, boolean>>(() => {
    try {
      const s = JSON.parse(localStorage.getItem("terratriage:nc-layers") || "");
      return { ...DEFAULT_ON, ...s };
    } catch {
      return DEFAULT_ON;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("terratriage:nc-layers", JSON.stringify(on));
    } catch {
      /* private window */
    }
  }, [on]);

  // --- live NEXRAD radar loop (F1a) --------------------------------------- //
  // 12 five-minute frames covering the last hour; computed once per mount so
  // the frame timestamps stay stable while you watch the loop.
  const radarFrames = useMemo(() => liveRadarFrames(), []);
  const [radarOn, setRadarOn] = useState<boolean>(() => {
    try {
      return localStorage.getItem("terratriage:nc-radar") === "1";
    } catch {
      return false;
    }
  });
  const [radarIdx, setRadarIdx] = useState(radarFrames.length - 1); // start on "now"
  const [radarPlaying, setRadarPlaying] = useState(!reduced);
  useEffect(() => {
    try {
      localStorage.setItem("terratriage:nc-radar", radarOn ? "1" : "0");
    } catch {
      /* private window */
    }
  }, [radarOn]);
  // advance the loop while playing and the tab is visible
  useEffect(() => {
    if (!radarOn || !radarPlaying || reduced) return;
    const t = window.setInterval(
      () => setRadarIdx((i) => (i + 1) % radarFrames.length),
      600,
    );
    return () => window.clearInterval(t);
  }, [radarOn, radarPlaying, reduced, radarFrames.length]);
  useEffect(() => {
    const onVis = () => {
      if (document.hidden) setRadarPlaying(false);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);
  // add / remove the raster layers (one per frame, so a warm loop never refetches).
  // every map touch is wrapped: the style can be mid-swap or the map torn down
  // between a nav and this effect's cleanup.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const ids = radarFrames.map((_, i) => `nc-radar-${i}`);
    const safe = (fn: () => void) => {
      try {
        if (mapRef.current && map.getStyle()) fn();
      } catch {
        /* map style not ready / torn down */
      }
    };
    const teardown = () =>
      safe(() => {
        for (const id of ids) {
          if (map.getLayer(id)) map.removeLayer(id);
          if (map.getSource(id)) map.removeSource(id);
        }
      });
    if (!radarOn) {
      teardown();
      return;
    }
    safe(() => {
      // sit the radar under the basemap's labels so names stay legible
      const firstSymbol = map
        .getStyle()
        ?.layers?.find((l) => l.type === "symbol")?.id;
      radarFrames.forEach((fr, i) => {
        const id = `nc-radar-${i}`;
        if (map.getSource(id)) return;
        map.addSource(id, {
          type: "raster",
          tiles: [fr.tileUrl],
          tileSize: 256,
          attribution: RADAR_ATTRIBUTION,
        });
        map.addLayer(
          {
            id,
            type: "raster",
            source: id,
            paint: {
              "raster-opacity": i === radarIdx ? 0.5 : 0,
              "raster-fade-duration": 120,
            },
          },
          firstSymbol,
        );
      });
    });
    return teardown;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, mapRef, radarOn, radarFrames, styleEpoch]);
  // cross-fade to the active frame
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !radarOn) return;
    try {
      if (!map.getStyle()) return;
      radarFrames.forEach((_, i) => {
        const id = `nc-radar-${i}`;
        if (map.getLayer(id))
          map.setPaintProperty(id, "raster-opacity", i === radarIdx ? 0.5 : 0);
      });
    } catch {
      /* style mid-swap */
    }
  }, [radarIdx, radarOn, ready, mapRef, radarFrames]);

  // --- real traffic congestion (TomTom flow tiles) ------------------------ //
  // Road colour = live speed vs free-flow speed, per road segment. This is
  // genuinely real per-segment data (not the synthetic "moving car" dots some
  // open-source globe demos animate from aggregate flow when no traffic
  // provider is configured) - deliberately declined here for that reason.
  const [trafficOn, setTrafficOn] = useState<boolean>(() => {
    try {
      return localStorage.getItem("terratriage:nc-traffic") === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("terratriage:nc-traffic", trafficOn ? "1" : "0");
    } catch {
      /* private window */
    }
  }, [trafficOn]);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const id = "nc-traffic";
    const safe = (fn: () => void) => {
      try {
        if (mapRef.current && map.getStyle()) fn();
      } catch {
        /* map style not ready / torn down */
      }
    };
    const teardown = () =>
      safe(() => {
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(id)) map.removeSource(id);
      });
    const key = settings.tomtomKey;
    if (!trafficOn || !key) {
      teardown();
      return;
    }
    safe(() => {
      const style = resolvedTheme() === "dark" ? "relative0-dark" : "relative0";
      const firstSymbol = map
        .getStyle()
        ?.layers?.find((l) => l.type === "symbol")?.id;
      map.addSource(id, {
        type: "raster",
        tiles: [
          `https://api.tomtom.com/traffic/map/4/tile/flow/${style}/{z}/{x}/{y}.png?key=${key}&thickness=10`,
        ],
        tileSize: 256,
        attribution: "© TomTom",
      });
      map.addLayer(
        { id, type: "raster", source: id, paint: { "raster-opacity": 0.85 } },
        firstSymbol,
      );
    });
    return teardown;
  }, [ready, mapRef, trafficOn, settings.tomtomKey, styleEpoch]);

  // frame the map on North Carolina once it's ready, leaving room for the side
  // panels, so the state fills the view rather than the whole Southeast
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const map = mapRef.current;
    const frame = () => {
      map.resize();
      const w = map.getContainer().clientWidth || 1200;
      const side = Math.min(340, w * 0.24);
      map.fitBounds(
        [NC_BBOX[0], NC_BBOX[1], NC_BBOX[2], NC_BBOX[3]] as [
          number,
          number,
          number,
          number,
        ],
        {
          padding: { top: 48, bottom: 48, left: side, right: side },
          duration: 0,
        },
      );
    };
    frame();
    const t = window.setTimeout(frame, 400);
    return () => window.clearTimeout(t);
  }, [ready, mapRef]);

  // committed-snapshot feeds (NHC / DriveNC are CORS-blocked live), fetch once
  useEffect(() => {
    ncStormTracks().then(setStorm);
    ncCameras().then(setCamera);
    ncClosures().then(setClosure);
  }, []);
  // genuinely-live feeds, fetch on mount, then refresh every 5 min
  useEffect(() => {
    const pull = () => {
      ncFloodForecasts().then(setGauge);
      ncAlerts().then(setAlert);
      ncStreamflow().then(setFlow);
    };
    pull();
    const t = window.setInterval(pull, 5 * 60_000);
    return () => window.clearInterval(t);
  }, []);
  // OpenFEMA history, fetch once
  useEffect(() => {
    ncFemaHistory().then(setHistory);
  }, []);
  // CLOUDS + FIRMS re-fetch whenever their keys change
  useEffect(() => {
    setClimate(null);
    ncClimate().then(setClimate);
  }, [settings.cloudsKey]);
  useEffect(() => {
    setFire(null);
    ncFires().then(setFire);
  }, [settings.firmsKey]);
  // fetch once on mount so the layer row shows a real count before it's ever
  // switched on; positions move fast, so re-poll on a much shorter cadence
  // than the other feeds, but only while the layer is actually visible
  useEffect(() => {
    ncAircraft().then(setAircraft);
  }, []);
  useEffect(() => {
    if (!on.aircraft) return;
    const t = window.setInterval(() => ncAircraft().then(setAircraft), 20_000);
    return () => window.clearInterval(t);
  }, [on.aircraft]);

  const results: Record<LayerId, NCResult<NCPointFC | NCGeomFC> | null> = {
    climate,
    gauge,
    flow,
    alert,
    storm,
    fire,
    camera,
    closure,
    aircraft,
  };

  const flyTo = (coord: [number, number], zoom = 9) =>
    mapRef.current?.flyTo({
      center: coord,
      zoom,
      duration: reduced ? 0 : 1100,
      essential: true,
    });

  const pointLayers = useMemo(() => {
    const out: (ScatterplotLayer | GeoJsonLayer)[] = [];
    type GF = NCGeomFC["features"][number];
    type PF = NCPointFC["features"][number];

    // polygon-ish layers first (alerts, storm cone) so points sit on top
    for (const id of ["alert", "storm"] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      const isStorm = id === "storm";
      out.push(
        new GeoJsonLayer({
          id: `nc-${id}`,
          data: (res.data as NCGeomFC).features as GF[],
          pickable: true,
          stroked: true,
          filled: true,
          getFillColor: (f) => {
            const [r, g, b] = sevRGB((f as GF).properties.severity);
            return [r, g, b, isStorm ? 55 : 34];
          },
          getLineColor: (f) => {
            const [r, g, b] = sevRGB((f as GF).properties.severity);
            return [r, g, b, 210];
          },
          lineWidthUnits: "pixels",
          getLineWidth: isStorm ? 2 : 1.25,
          pointRadiusUnits: "pixels",
          getPointRadius: isStorm ? 7 : 5,
          onClick: (info: PickingInfo) => {
            const f = info.object as GF | undefined;
            if (!f) return;
            const c = centroidOf(f.geometry);
            if (c) flyTo(c, 8);
            setSelected({
              title: f.properties.title,
              detail: f.properties.detail,
              source: LAYER_META[id].note,
              coord: c ?? NC_CENTER,
              url: f.properties.url,
            });
          },
        }),
      );
    }

    // point layers. cameras + closures + aircraft aren't on the hazard-severity // ramp, they get their own fixed marks so the ramp still means "flood risk".
    const FLOW_RGB: [number, number, number] = [90, 150, 200];
    for (const id of [
      "gauge",
      "flow",
      "climate",
      "fire",
      "closure",
      "camera",
      "aircraft",
    ] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      const isCam = id === "camera";
      const isClosure = id === "closure";
      const isFlow = id === "flow";
      const isAircraft = id === "aircraft";
      out.push(
        new ScatterplotLayer({
          id: `nc-${id}`,
          data: (res.data as NCPointFC).features as PF[],
          pickable: true,
          stroked: true,
          filled: !isCam,
          radiusUnits: "pixels",
          getPosition: (f) =>
            (f as PF).geometry.coordinates as [number, number],
          getRadius: (f) => {
            if (isCam) return 2.5;
            if (isClosure) return 3.5;
            if (isFlow) return 2.8;
            if (isAircraft) return 3;
            const s = (f as PF).properties.severity;
            return s <= 0 ? 2.6 : 4 + s * 3;
          },
          getFillColor: (f) => {
            if (isCam) return [...CAMERA_RGB, 0];
            if (isClosure) return [...CLOSURE_RGB, 150];
            if (isFlow) return [...FLOW_RGB, 70];
            if (isAircraft) {
              const mil = (f as PF).properties.category === "Military";
              return [...(mil ? AIRCRAFT_MIL_RGB : AIRCRAFT_RGB), 190];
            }
            const s = (f as PF).properties.severity;
            const [r, g, b] = sevRGB(s);
            return [r, g, b, s <= 0 ? 45 : 70 + s * 55];
          },
          getLineColor: (f) => {
            if (isCam) return [...CAMERA_RGB, 210];
            if (isClosure) return [...CLOSURE_RGB, 230];
            if (isFlow) return [...FLOW_RGB, 190];
            if (isAircraft) {
              const mil = (f as PF).properties.category === "Military";
              return [...(mil ? AIRCRAFT_MIL_RGB : AIRCRAFT_RGB), 230];
            }
            const s = (f as PF).properties.severity;
            const [r, g, b] = sevRGB(s);
            return [r, g, b, s <= 0 ? 120 : 230];
          },
          lineWidthUnits: "pixels",
          getLineWidth: 1,
          onClick: (info: PickingInfo) => {
            const f = info.object as PF | undefined;
            if (!f) return;
            const c = f.geometry.coordinates as [number, number];
            flyTo(c, id === "camera" || id === "closure" ? 11 : 10);
            setSelected({
              title: f.properties.title,
              detail:
                f.properties.detail ??
                [f.properties.value, f.properties.category]
                  .filter(Boolean)
                  .join(" · "),
              source: LAYER_META[id].note,
              coord: c,
              url: f.properties.url,
              linkLabel:
                id === "camera" ? "View live camera image ↗" : undefined,
            });
          },
        }),
      );
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [climate, gauge, flow, alert, storm, fire, camera, closure, aircraft, on]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({
        interleaved: false,
        layers: [],
        getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
        getTooltip: (info) => {
          const f = info.object as
            | NCPointFC["features"][number]
            | NCGeomFC["features"][number]
            | undefined;
          if (!f) return null;
          const p = f.properties;
          const cs = getComputedStyle(document.documentElement);
          return {
            text: p.value ? `${p.title} · ${p.value}` : p.title,
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
    overlayRef.current.setProps({ layers: pointLayers });
  }, [ready, mapRef, pointLayers, styleEpoch]);

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

  // ---- right-panel derived lists ----------------------------------------- //
  const floodRanked = useMemo(
    () =>
      (gauge?.data.features ?? [])
        .filter((x) => x.properties.severity >= 1)
        .sort((a, b) => b.properties.severity - a.properties.severity)
        .slice(0, 12),
    [gauge],
  );

  const alertList = useMemo(() => {
    const seen = new Set<string>();
    return (alert?.data.features ?? [])
      .filter((f) => {
        const k = `${f.properties.title}|${f.properties.detail ?? ""}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      })
      .sort((a, b) => b.properties.severity - a.properties.severity)
      .slice(0, 10);
  }, [alert]);

  // worst current risk point, top flood gauge, else a fire-weather RAWS
  // station, else the centroid of the most severe official alert
  const focusPoint = useMemo<[number, number] | null>(() => {
    const worstGauge = floodRanked[0];
    if (worstGauge) return worstGauge.geometry.coordinates as [number, number];
    const fireStation = (climate?.data.features ?? []).find(
      (f) => f.properties.severity >= 2,
    );
    if (fireStation)
      return fireStation.geometry.coordinates as [number, number];
    const topAlert = alertList.find((f) => f.properties.severity >= 3);
    if (topAlert) return centroidOf(topAlert.geometry);
    return null;
  }, [floodRanked, climate, alertList]);

  // only surface the DOT ground-truth panel when there is a genuinely elevated
  // situation to attach it to (a gauge at moderate flood, a fire-weather RAWS
  // station, or a severe NWS alert), not just one gauge at action stage
  const elevatedRisk = useMemo(
    () =>
      (floodRanked[0]?.properties.severity ?? 0) >= 2 ||
      (climate?.data.features ?? []).some((f) => f.properties.severity >= 2) ||
      alertList.some((f) => f.properties.severity >= 3),
    [floodRanked, climate, alertList],
  );

  const nearest = (feats: NCPointFC["features"], n: number, maxKm: number) => {
    if (!focusPoint || !feats.length)
      return [] as { c: NCPointFC["features"][number]; km: number }[];
    const [flon, flat] = focusPoint;
    return feats
      .map((c) => {
        const [lon, lat] = c.geometry.coordinates;
        const dx = (lon - flon) * 111 * Math.cos((flat * Math.PI) / 180);
        const dy = (lat - flat) * 111;
        return { c, km: Math.hypot(dx, dy) };
      })
      .filter((x) => x.km <= maxKm)
      .sort((a, b) => a.km - b.km)
      .slice(0, n);
  };
  const nearbyCameras = useMemo(
    () => nearest(camera?.data.features ?? [], 5, 80),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [camera, focusPoint],
  );
  const nearbyClosures = useMemo(
    () => nearest(closure?.data.features ?? [], 4, 120),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [closure, focusPoint],
  );

  // cameras / closures / storm are snapshot-by-design; only a live-capable feed
  // falling back to a snapshot means we're actually offline
  const anyStale = (["gauge", "flow", "alert", "climate"] as const).some(
    (id) => {
      const r = results[id];
      return r && !r.disabled && r.stale;
    },
  );

  const layerRows: LayerRow[] = LAYER_ORDER.map((id) => {
    const res = results[id];
    const meta = LAYER_META[id];
    const disabled = !res || !!res.disabled;
    const count = res && !res.disabled ? res.data.features.length : 0;
    // a disabled layer isn't an error, say why in plain words
    let metaLine = "loading…";
    if (res) {
      // `res.source` names the feed and sometimes tacks on its own count
      // ("USGS NWIS · 291 gages"); drop both the source-name prefix and a
      // leading count so the row doesn't read "291 · 291 gages"
      if (!res.disabled)
        metaLine = `${count.toLocaleString()} · ${res.source.replace(/^[^·]+·\s*/, "").replace(/^[\d,]+\s+/, "")}`;
      else if (id === "climate" || id === "fire")
        metaLine = "optional, add a free key";
      else if (id === "storm") metaLine = "none active";
      else if (id === "aircraft")
        metaLine = res.reason?.includes("unavailable")
          ? "unavailable"
          : "none in view";
      else metaLine = "unavailable";
    }
    return {
      id,
      label: meta.label,
      meta: metaLine,
      checked: on[id],
      disabled,
      reason: res?.reason,
      onToggle: () => setOn((s) => ({ ...s, [id]: !s[id] })),
    };
  });
  layerRows.push({
    id: "radar",
    label: "Rain & storms",
    meta: "NWS NEXRAD · live 1-hour loop",
    checked: radarOn,
    disabled: false,
    onToggle: () => setRadarOn((v) => !v),
  });
  layerRows.push({
    id: "traffic",
    label: "Traffic congestion",
    meta: settings.tomtomKey
      ? "TomTom · live road-segment speeds"
      : "optional, add a free key",
    checked: trafficOn,
    disabled: !settings.tomtomKey,
    reason: !settings.tomtomKey
      ? "Add a free TomTom traffic key to colour every road by its real live speed vs free-flow. Real per-segment data, not a simulation."
      : undefined,
    onToggle: () => setTrafficOn((v) => !v),
  });

  const floodItems: RankedItem[] = floodRanked.map((f) => ({
    id: f.properties.id,
    primary: f.properties.title,
    secondary: `${f.properties.category} · ${f.properties.value}`,
    dot: sevCSS(f.properties.severity),
    onSelect: () => flyTo(f.geometry.coordinates as [number, number], 10),
  }));

  const alertItems: RankedItem[] = alertList.map((f) => ({
    id: f.properties.id,
    primary: f.properties.title,
    secondary: f.properties.detail,
    dot: sevCSS(f.properties.severity),
    onSelect: () => {
      const c = centroidOf(f.geometry);
      if (c) flyTo(c, 8);
    },
  }));

  const riskPanels = (
    <>
      <section className="panel px-3.5 py-3.5">
        <h2 className="section-title mb-2">Current conditions</h2>
        {climate?.disabled ? (
          <p className="text-2xs leading-relaxed text-ink-faint">
            {climate.reason}
          </p>
        ) : climate ? (
          <>
            <StatTile
              label="Stations reporting"
              value={climate.headline ?? "-"}
              sub="ECONet research + RAWS fire-weather stations, via the NC State Climate Office CLOUDS API."
            />
            {(() => {
              const fire = (climate.data.features ?? []).filter(
                (f) => f.properties.severity >= 2,
              );
              return fire.length ? (
                <p className="mt-2 rounded-sm bg-dmg1/15 px-1.5 py-1 text-2xs text-dmg1">
                  {fire.length} RAWS station{fire.length > 1 ? "s" : ""} at
                  fire-weather risk (low fuel moisture + wind)
                </p>
              ) : null;
            })()}
          </>
        ) : (
          <div className="skel h-10" />
        )}
      </section>

      <section className="panel px-3.5 py-3.5">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="section-title">Flood forecast</h2>
          <span className="cap">{gauge?.headline ?? "…"}</span>
        </div>
        {gauge ? (
          <RankedList
            items={floodItems}
            empty="Every forecast gauge in NC is below flood stage. NWM forecasts extend to ungauged creeks too, a rise shows here before a gauge is under water."
          />
        ) : (
          <div className="skel h-16" />
        )}
      </section>

      <section className="panel px-3.5 py-3.5">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="section-title">Official alerts</h2>
          <span className="cap">{alert?.headline ?? "…"}</span>
        </div>
        {alert ? (
          <RankedList
            as="ul"
            items={alertItems}
            empty="No active NWS alerts for North Carolina."
          />
        ) : (
          <div className="skel h-12" />
        )}
      </section>

      {fire && !fire.disabled && fire.data.features.length > 0 && (
        <section className="panel px-3.5 py-3.5">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="section-title">Active fire</h2>
            <span className="cap">{fire.headline ?? "…"}</span>
          </div>
          <p className="text-2xs leading-relaxed text-ink-faint">
            {fire.data.features.length} VIIRS hotspot
            {fire.data.features.length > 1 ? "s" : ""} in North Carolina in the
            past 24 h (NASA FIRMS). Thermal anomalies, not all are wildfires.
          </p>
        </section>
      )}

      <section className="panel px-3.5 py-3.5">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="section-title">NC disaster history</h2>
          <span className="cap">{history ? "OpenFEMA" : "…"}</span>
        </div>
        {history ? (
          history.total > 0 ? (
            <>
              <StatTile
                label="Federally-declared disasters"
                value={`${history.total} since ${history.sinceYear}`}
                sub={history.byType
                  .slice(0, 4)
                  .map((t) => `${t.count} ${t.type.toLowerCase()}`)
                  .join(" · ")}
              />
              <ul className="mt-2 space-y-1">
                {history.recent.map((d) => (
                  <li key={d.disasterNumber} className="text-2xs text-ink-dim">
                    <span className="tnum text-ink-faint">
                      {d.declarationDate.slice(0, 4)}
                    </span>{" "}
                    {d.declarationTitle}
                  </li>
                ))}
              </ul>
              {history.stale && (
                <p className="mt-1.5 text-2xs text-ink-faint">
                  {history.source}
                </p>
              )}
            </>
          ) : (
            <p className="text-2xs text-ink-faint">{history.source}</p>
          )
        ) : (
          <div className="skel h-16" />
        )}
      </section>

      {storm && !storm.disabled && (
        <section className="panel px-3.5 py-3.5">
          <h2 className="section-title mb-1.5">Active storm</h2>
          <ul className="space-y-1">
            {(storm.data.features ?? []).map((f) => (
              <li key={f.properties.id} className="text-xs text-ink">
                {f.properties.title}
                {f.properties.detail && (
                  <span className="block text-2xs text-ink-faint">
                    {f.properties.detail}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-2xs text-ink-faint">
            NHC forecast cone, track line and watch/warning zones (committed
            snapshot).
          </p>
        </section>
      )}

      {elevatedRisk &&
        (nearbyCameras.length > 0 || nearbyClosures.length > 0) && (
          <section className="panel px-3.5 py-3.5">
            <h2 className="section-title mb-1.5">Ground truth near the risk</h2>
            {nearbyClosures.length > 0 && (
              <div className="mb-2">
                <p className="mb-1 text-2xs font-medium text-ink-dim">
                  Road closures
                </p>
                <RankedList
                  items={nearbyClosures.map(({ c, km }) => ({
                    id: c.properties.id,
                    primary: c.properties.title,
                    dotClassName: "bg-dmg1",
                    trailing: `${km.toFixed(0)} km`,
                    onSelect: () =>
                      flyTo(c.geometry.coordinates as [number, number], 12),
                  }))}
                />
              </div>
            )}
            {nearbyCameras.length > 0 && (
              <>
                <p className="mb-1 text-2xs font-medium text-ink-dim">
                  Traffic cameras
                </p>
                <RankedList
                  items={nearbyCameras.map(({ c, km }) => ({
                    id: c.properties.id,
                    primary: c.properties.title,
                    trailing: `${km.toFixed(0)} km`,
                    onSelect: () =>
                      flyTo(c.geometry.coordinates as [number, number], 12),
                  }))}
                />
              </>
            )}
          </section>
        )}
    </>
  );

  return (
    <div className="relative h-full">
      <div
        ref={containerRef}
        className="h-full w-full"
        aria-label="North Carolina risk dashboard"
      />

      {/* left column: title, layers, legend */}
      <aside className="absolute left-3 top-3 z-20 flex max-h-[calc(100%-1.5rem)] w-[18rem] max-w-[calc(100vw-1.5rem)] flex-col gap-3 overflow-y-auto sm:left-4 sm:top-4">
        <section className="panel px-4 py-3.5">
          <div className="flex items-baseline justify-between">
            <h1 className="font-display text-lg font-semibold leading-tight text-ink">
              North Carolina
            </h1>
            <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
              <span
                className={`h-1.5 w-1.5 rounded-full ${anyStale ? "bg-dmg1" : "bg-accent"}`}
              />
              {anyStale ? "cached" : "live"}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-ink-dim">
            Flood forecasts, warnings, storm tracking and road conditions, the
            hours before and during a disaster.
          </p>
          <button
            onClick={onOpenAssess}
            className="pressable mt-2.5 text-xs font-medium text-accent hover:underline"
          >
            Assess damage from imagery →
          </button>
        </section>

        <section className="panel px-4 py-3.5">
          <button
            onClick={() => setLayersOpen((v) => !v)}
            aria-expanded={layersOpen}
            className="pressable -mx-1 flex w-[calc(100%+0.5rem)] items-center justify-between px-1 md:pointer-events-none"
          >
            <span className="section-title">Map layers</span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              aria-hidden
              className={`text-ink-faint transition-transform duration-200 md:hidden ${layersOpen ? "rotate-180" : ""}`}
            >
              <path
                d="M3 4.5L6 7.5L9 4.5"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
              />
            </svg>
          </button>
          <div className={layersOpen ? "mt-2.5" : "hidden"}>
            <LayerToggles rows={layerRows} />

            {(settings.cloudsKey || climate?.disabled) && (
              <KeyForm
                hasKey={!!settings.cloudsKey}
                placeholder="CLOUDS API hash"
                removeLabel="remove CLOUDS key"
                onAdd={(v) => set("cloudsKey", v)}
                onRemove={() => set("cloudsKey", undefined)}
              />
            )}
            <KeyForm
              hasKey={!!settings.tomtomKey}
              placeholder="TomTom traffic key"
              removeLabel="remove TomTom key"
              onAdd={(v) => set("tomtomKey", v)}
              onRemove={() => set("tomtomKey", undefined)}
            />

            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1.5 border-t border-line pt-2.5">
              {[-1, 0, 1, 2, 3].map((s) => (
                <span
                  key={s}
                  className="flex items-center gap-1.5 text-2xs text-ink-faint"
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ background: sevCSS(s) }}
                  />
                  {NC_SEV_LABEL[s + 1]}
                </span>
              ))}
              <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: `rgb(${CLOSURE_RGB.join(",")})` }}
                />
                road closure
              </span>
              <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{
                    boxShadow: `inset 0 0 0 1.5px rgb(${CAMERA_RGB.join(",")})`,
                  }}
                />
                camera
              </span>
              <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: `rgb(${AIRCRAFT_RGB.join(",")})` }}
                />
                aircraft
              </span>
            </div>

            <button
              onClick={onOpenAbout}
              className="pressable mt-3 border-t border-line pt-2.5 text-2xs text-ink-faint hover:text-ink"
            >
              About NC Recon
            </button>
          </div>
        </section>
      </aside>

      {/* right: NC risk now, full panel on md+ */}
      <aside className="absolute right-3 top-3 z-20 hidden max-h-[calc(100%-1.5rem)] w-[20rem] flex-col gap-3 overflow-y-auto md:flex lg:right-4 lg:top-4">
        {riskPanels}
      </aside>

      {/* mobile: a compact state strip that opens the full sheet. Right edge
          clears the map's own bottom-right zoom/compass control (~52px) so
          the sheet's rounded corner doesn't sit on top of the compass button. */}
      <div className="absolute bottom-3 left-3 right-14 z-20 md:hidden">
        {riskOpen ? (
          <div className="panel flex max-h-[70vh] flex-col gap-3 overflow-y-auto p-3">
            <button
              onClick={() => setRiskOpen(false)}
              className="pressable cap self-end text-ink-faint hover:text-ink"
            >
              Close ✕
            </button>
            {riskPanels}
          </div>
        ) : (
          <button
            onClick={() => setRiskOpen(true)}
            className="pressable panel flex w-full items-center justify-between px-3.5 py-2.5 text-xs text-ink"
          >
            <span className="flex flex-col text-left">
              <span className="cap">NC risk now</span>
              <span className="tnum text-2xs text-ink-dim">
                {gauge?.headline ?? "flood …"} · {alert?.headline ?? "alerts …"}
              </span>
            </span>
            <span className="text-ink-faint">details ↑</span>
          </button>
        )}
      </div>

      {/* radar playback strip */}
      {radarOn && (
        <RadarControl
          playing={radarPlaying}
          index={radarIdx}
          frames={radarFrames}
          onToggle={() => setRadarPlaying((p) => !p)}
          onScrub={(i) => {
            setRadarPlaying(false);
            setRadarIdx(i);
          }}
        />
      )}

      {/* selected feature */}
      {selected && (
        <FeatureCallout
          title={selected.title}
          subtitle={`${selected.source} · ${selected.coord[1].toFixed(2)}, ${selected.coord[0].toFixed(2)}`}
          onDismiss={() => setSelected(null)}
        >
          {selected.detail && (
            <p className="mt-2 border-t border-line pt-2 text-2xs leading-relaxed text-ink-dim">
              {selected.detail}
            </p>
          )}
          {selected.url && /^https?:/.test(selected.url) && (
            <a
              href={selected.url}
              target="_blank"
              rel="noreferrer"
              className="pressable mt-2 inline-block rounded-md border border-accent/60 px-2 py-0.5 text-2xs text-ink hover:bg-accent hover:text-accent-ink"
            >
              {selected.linkLabel ?? "Open source ↗"}
            </a>
          )}
        </FeatureCallout>
      )}
    </div>
  );
}

// centroid of any GeoJSON geometry, good enough for a fly-to
function centroidOf(geom: GeoJSON.Geometry): [number, number] | null {
  const acc: [number, number] = [0, 0];
  let n = 0;
  const walk = (coords: unknown): void => {
    if (
      Array.isArray(coords) &&
      typeof coords[0] === "number" &&
      typeof coords[1] === "number"
    ) {
      acc[0] += coords[0];
      acc[1] += coords[1];
      n++;
      return;
    }
    if (Array.isArray(coords)) coords.forEach(walk);
  };
  if ("coordinates" in geom)
    walk((geom as { coordinates: unknown }).coordinates);
  return n ? [acc[0] / n, acc[1] / n] : null;
}
