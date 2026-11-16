import { useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer, GeoJsonLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import { prefersReducedMotion } from "../lib/motion";
import { useSettings } from "../lib/settings";
import { liveRadarFrames, RADAR_ATTRIBUTION } from "../lib/radar";
import { useOffline, isOffline, offlineReason } from "../lib/offline";
import {
  GIBS_LAYERS,
  gibsLayer,
  gibsTiles,
  goesFrames,
  latestTime,
  shiftTime,
  timeLabel,
  type GibsKey,
  type GibsLayer,
  type GoesFrame,
} from "../lib/gibs";
import type { Map as MLMap, RasterTileSource } from "maplibre-gl";
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
  ncFiman,
  ncPower,
  ncShelters,
  ncStreamflow,
  ncFires,
  ncFemaHistory,
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
  | "fiman"
  | "flow"
  | "alert"
  | "storm"
  | "fire"
  | "camera"
  | "closure"
  | "power"
  | "shelter";

const LAYER_META: Record<LayerId, { label: string; note: string }> = {
  climate: { label: "Current conditions", note: "ECONet + RAWS (CLOUDS API)" },
  gauge: {
    label: "River flood forecast",
    note: "NOAA NWPS / National Water Model",
  },
  fiman: {
    label: "NC flood gauges",
    note: "NC Emergency Management FIMAN",
  },
  flow: { label: "Streamflow", note: "USGS NWIS instantaneous values" },
  alert: { label: "Official alerts", note: "NWS watches & warnings" },
  storm: { label: "Active storm", note: "NHC cone & track" },
  fire: { label: "Active fire", note: "NASA FIRMS VIIRS" },
  camera: { label: "DOT cameras", note: "NCDOT DriveNC" },
  closure: { label: "Road closures", note: "NCDOT DriveNC" },
  power: { label: "Power outages", note: "Duke Energy, by county" },
  shelter: { label: "Open shelters", note: "FEMA ESF6 / American Red Cross" },
};
const LAYER_ORDER: LayerId[] = [
  "gauge",
  "fiman",
  "flow",
  "alert",
  "power",
  "shelter",
  "climate",
  "fire",
  "storm",
  "closure",
  "camera",
];

const DEFAULT_ON: Record<LayerId, boolean> = {
  climate: true,
  gauge: true,
  fiman: true,
  power: true,
  shelter: true,
  flow: false,
  alert: true,
  storm: true,
  fire: true,
  // off by default: statewide DOT closures are mostly routine and, at 100+
  // marks, they read as an emergency on an otherwise-calm map
  closure: false,
  camera: false,
};

// cameras + closures sit off the flood-severity ramp, so the
// legend names them individually
const CAMERA_RGB: [number, number, number] = [139, 148, 163];
const CLOSURE_RGB: [number, number, number] = [232, 137, 74];
const SHELTER_RGB: [number, number, number] = [62, 168, 140];

const sevRGB = (s: number): [number, number, number] =>
  NC_SEV_COLOR[Math.max(-1, Math.min(3, s))];
const sevCSS = (s: number) => `rgb(${sevRGB(s).join(",")})`;

// --- NASA GIBS imagery ----------------------------------------------------- //
// bottom to top: imagery that covers the basemap first, data overlays above,
// all under the radar loop and the basemap labels
const GIBS_STACK: GibsKey[] = ["viirs", "rtc_s1", "goes", "smap", "imerg", "dswx_hls", "dswx_s1"];
const GIBS_OFF: Record<GibsKey, boolean> = {
  goes: false,
  viirs: false,
  imerg: false,
  smap: false,
  dswx_hls: false,
  dswx_s1: false,
  rtc_s1: false,
};
const gibsSourceId = (k: GibsKey) => `nc-gibs-${k}`;
const goesId = (i: number) => `nc-gibs-goes-${i}`;
// a hidden loop frame keeps a sliver of opacity: a fully transparent raster
// layer lets MapLibre drop its tiles, and the loop would refetch every pass
const GOES_HIDDEN = 0.003;

/** where a GIBS layer goes in the layer stack: under the next GIBS layer up,
 * else under the radar loop, else under the first basemap label */
function gibsBeforeId(map: MLMap, key: GibsKey): string | undefined {
  const layers = map.getStyle()?.layers ?? [];
  for (const k of GIBS_STACK.slice(GIBS_STACK.indexOf(key) + 1)) {
    const hit = layers.find((l) => l.id === gibsSourceId(k) || l.id.startsWith(`${gibsSourceId(k)}-`));
    if (hit) return hit.id;
  }
  if (map.getLayer("nc-radar-0")) return "nc-radar-0";
  return layers.find((l) => l.type === "symbol")?.id;
}

const utcHHMM = (ms: number) => new Date(ms).toISOString().slice(11, 16);
const agoLabel = (ms: number) => {
  const m = Math.max(0, Math.round((Date.now() - ms) / 60_000));
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min ago`;
};

export default function NCDashboard({ onOpenAssess, onOpenAbout }: Props) {
  // start already framed on NC (shifted east to clear the left panel); the
  // fitBounds effect refines it once the container is measured
  const { containerRef, mapRef, ready, styleEpoch } = useMapLibre({
    center: [-78.7, 35.4],
    zoom: 6.7,
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
  const [fiman, setFiman] = useState<NCResult<NCPointFC> | null>(null);
  const [power, setPower] = useState<NCResult<NCGeomFC> | null>(null);
  const [shelter, setShelter] = useState<NCResult<NCPointFC> | null>(null);
  const [fire, setFire] = useState<NCResult<NCPointFC> | null>(null);
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

  // --- NASA GIBS imagery ------------------------------------------------- //
  // remote tiles only once the server says it is online (undefined = not
  // known yet, so nothing is requested until then)
  const off = useOffline();
  const gibsOnline = off !== undefined && !isOffline(off);
  const [gibsOn, setGibsOn] = useState<Record<GibsKey, boolean>>(() => {
    try {
      const s = JSON.parse(localStorage.getItem("terratriage:nc-gibs") || "");
      return { ...GIBS_OFF, ...s };
    } catch {
      return GIBS_OFF;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("terratriage:nc-gibs", JSON.stringify(gibsOn));
    } catch {
      /* private window */
    }
  }, [gibsOn]);
  // newest time per layer from GIBS (null = could not ask; tiles then use
  // GIBS's own default), and the time the user stepped to, if any
  const [gibsLatest, setGibsLatest] = useState<Partial<Record<GibsKey, string | null>>>({});
  const [gibsPick, setGibsPick] = useState<Partial<Record<GibsKey, string>>>({});
  const gibsWhen = (k: GibsKey) => gibsPick[k] ?? gibsLatest[k] ?? null;
  useEffect(() => {
    if (!gibsOnline) return;
    let live = true;
    for (const l of GIBS_LAYERS) {
      if (l.key === "goes" || !gibsOn[l.key] || l.key in gibsLatest) continue;
      void latestTime(l).then((t) => live && setGibsLatest((s) => ({ ...s, [l.key]: t })));
    }
    return () => {
      live = false;
    };
  }, [gibsOn, gibsOnline, gibsLatest]);

  // the still layers: one raster source each, retargeted when the date changes
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    try {
      if (!map.getStyle()) return;
      for (const l of GIBS_LAYERS) {
        if (l.key === "goes") continue;
        const id = gibsSourceId(l.key);
        const want = gibsOnline && gibsOn[l.key] && l.key in gibsLatest;
        if (!want) {
          if (map.getLayer(id)) map.removeLayer(id);
          if (map.getSource(id)) map.removeSource(id);
          continue;
        }
        const tiles = gibsTiles(l, gibsPick[l.key] ?? gibsLatest[l.key] ?? null);
        const src = map.getSource(id) as RasterTileSource | undefined;
        if (src) {
          if (src.tiles?.[0] !== tiles) src.setTiles([tiles]);
          continue;
        }
        map.addSource(id, {
          type: "raster",
          tiles: [tiles],
          tileSize: 256,
          maxzoom: l.maxzoom,
          attribution: l.credit,
        });
        map.addLayer(
          {
            id,
            type: "raster",
            source: id,
            ...(l.minzoom ? { minzoom: l.minzoom } : {}),
            paint: { "raster-opacity": l.opacity, "raster-fade-duration": 150 },
          },
          gibsBeforeId(map, l.key),
        );
      }
    } catch {
      /* style mid-swap / torn down */
    }
  }, [ready, mapRef, styleEpoch, gibsOn, gibsOnline, gibsLatest, gibsPick]);

  // GOES-East GeoColor loop: frames from GIBS's own time list, newest last
  const goesOn = gibsOn.goes && gibsOnline;
  const [goes, setGoes] = useState<{ frames: GoesFrame[]; error?: string } | null>(null);
  const [goesIdx, setGoesIdx] = useState(0);
  const [goesReady, setGoesReady] = useState<number[]>([]); // frame indexes with tiles in
  const [goesShown, setGoesShown] = useState(-1);
  const [goesPlaying, setGoesPlaying] = useState(!reduced);
  useEffect(() => {
    if (!goesOn) {
      setGoes(null);
      return;
    }
    const ctl = new AbortController();
    goesFrames(Date.now(), ctl.signal)
      .then((frames) => {
        setGoes(frames.length ? { frames } : { frames, error: "GIBS lists no recent GOES-East images." });
        setGoesIdx(Math.max(0, frames.length - 1));
      })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted)
          setGoes({ frames: [], error: `GOES-East images are unavailable: ${e instanceof Error ? e.message : e}` });
      });
    return () => ctl.abort();
  }, [goesOn]);
  // add one layer per frame, then load them newest first so the loop is usable
  // while it fills (the Canary approach)
  useEffect(() => {
    const map = mapRef.current;
    const frames = goes?.frames ?? [];
    if (!ready || !map || !goesOn || !frames.length) return;
    let live = true;
    const ids = frames.map((_, i) => goesId(i));
    const safe = (fn: () => void) => {
      try {
        if (mapRef.current && map.getStyle()) fn();
      } catch {
        /* style mid-swap / torn down */
      }
    };
    const l = gibsLayer("goes");
    safe(() => {
      const before = gibsBeforeId(map, "goes");
      frames.forEach((f, i) => {
        if (map.getSource(ids[i])) return;
        map.addSource(ids[i], {
          type: "raster",
          tiles: [gibsTiles(l, f.time)],
          tileSize: 256,
          maxzoom: l.maxzoom,
          // identical on every frame so MapLibre shows the credit once
          attribution: l.credit,
        });
        map.addLayer(
          {
            id: ids[i],
            type: "raster",
            source: ids[i],
            layout: { visibility: "none" },
            paint: {
              "raster-opacity": GOES_HIDDEN,
              "raster-opacity-transition": { duration: 0 },
              "raster-fade-duration": 0,
            },
          },
          before,
        );
      });
    });
    setGoesReady([]);
    setGoesShown(-1);
    void (async () => {
      for (let i = frames.length - 1; i >= 0; i--) {
        if (!live) return;
        safe(() => map.setLayoutProperty(ids[i], "visibility", "visible"));
        const started = performance.now();
        const loaded = () => {
          try {
            return !map.getSource(ids[i]) || map.isSourceLoaded(ids[i]);
          } catch {
            return true; // torn down: stop waiting
          }
        };
        while (live && performance.now() - started < 20_000 && !loaded()) {
          await new Promise((r) => setTimeout(r, 250));
        }
        if (!live) return;
        setGoesReady((s) => [...s, i]);
      }
    })();
    return () => {
      live = false;
      safe(() => {
        for (const id of ids) {
          if (map.getLayer(id)) map.removeLayer(id);
          if (map.getSource(id)) map.removeSource(id);
        }
      });
    };
  }, [ready, mapRef, styleEpoch, goesOn, goes]);
  // show the loaded frame nearest the one asked for
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !goesReady.length) return;
    const pick = goesReady.reduce((a, b) => (Math.abs(b - goesIdx) < Math.abs(a - goesIdx) ? b : a));
    try {
      if (!map.getStyle()) return;
      for (const i of goesReady) {
        if (map.getLayer(goesId(i)))
          map.setPaintProperty(goesId(i), "raster-opacity", i === pick ? gibsLayer("goes").opacity : GOES_HIDDEN);
      }
    } catch {
      /* style mid-swap */
    }
    setGoesShown(pick);
  }, [ready, mapRef, goesIdx, goesReady]);
  // play: step through the loaded frames; never starts by itself under
  // reduced motion, and pauses when the tab is hidden
  useEffect(() => {
    if (!goesOn || !goesPlaying || goesReady.length < 2) return;
    const order = [...goesReady].sort((a, b) => a - b);
    const t = window.setInterval(() => {
      setGoesIdx((i) => order.find((k) => k > i) ?? order[0]);
    }, 700);
    return () => window.clearInterval(t);
  }, [goesOn, goesPlaying, goesReady]);
  useEffect(() => {
    const onVis = () => {
      if (document.hidden) setGoesPlaying(false);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

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
      ncFiman().then(setFiman);
      ncPower().then(setPower);
      ncShelters().then(setShelter);
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

  const results: Record<LayerId, NCResult<NCPointFC | NCGeomFC> | null> = {
    climate,
    gauge,
    fiman,
    flow,
    power,
    shelter,
    alert,
    storm,
    fire,
    camera,
    closure,
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
    for (const id of ["power", "alert", "storm"] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      const isStorm = id === "storm";
      const isPower = id === "power";
      out.push(
        new GeoJsonLayer({
          id: `nc-${id}`,
          data: (res.data as NCGeomFC).features as GF[],
          pickable: true,
          stroked: true,
          filled: true,
          getFillColor: (f) => {
            const [r, g, b] = sevRGB((f as GF).properties.severity);
            return [r, g, b, isStorm ? 55 : isPower ? 80 : 34];
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

    // point layers. cameras + closures aren't on the hazard-severity // ramp, they get their own fixed marks so the ramp still means "flood risk".
    const FLOW_RGB: [number, number, number] = [90, 150, 200];
    for (const id of [
      "gauge",
      "fiman",
      "flow",
      "climate",
      "fire",
      "shelter",
      "closure",
      "camera",
    ] as const) {
      const res = results[id];
      if (!on[id] || !res || res.disabled) continue;
      const isCam = id === "camera";
      const isClosure = id === "closure";
      const isFlow = id === "flow";
      const isShelter = id === "shelter";
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
            if (isShelter) return 5;
            const s = (f as PF).properties.severity;
            return s <= 0 ? 2.6 : 4 + s * 3;
          },
          getFillColor: (f) => {
            if (isCam) return [...CAMERA_RGB, 0];
            if (isClosure) return [...CLOSURE_RGB, 150];
            if (isFlow) return [...FLOW_RGB, 70];
            if (isShelter) return [...SHELTER_RGB, 190];
            const s = (f as PF).properties.severity;
            const [r, g, b] = sevRGB(s);
            return [r, g, b, s <= 0 ? 45 : 70 + s * 55];
          },
          getLineColor: (f) => {
            if (isCam) return [...CAMERA_RGB, 210];
            if (isClosure) return [...CLOSURE_RGB, 230];
            if (isFlow) return [...FLOW_RGB, 190];
            if (isShelter) return [255, 255, 255, 230];
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
            flyTo(c, id === "camera" || id === "closure" || id === "shelter" ? 11 : 10);
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
  }, [climate, gauge, fiman, flow, alert, storm, fire, camera, closure, power, shelter, on]);

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
  const anyStale = (["gauge", "fiman", "flow", "alert", "climate"] as const).some(
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
      if (!res.disabled && count === 0 && id === "power") metaLine = "none out · live";
      else if (!res.disabled && count === 0 && id === "shelter")
        metaLine = "none open · live";
      else if (!res.disabled)
        metaLine = `${count.toLocaleString()} · ${res.source.replace(/^[^·]+·\s*/, "").replace(/^[\d,]+\s+/, "")}`;
      else if (id === "climate" || id === "fire")
        metaLine = "optional, add a free key";
      else if (id === "storm") metaLine = "none active";
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

  const gibsOffline = isOffline(off);
  const gibsRows: LayerRow[] = GIBS_LAYERS.map((l) => {
    let meta = l.source;
    if (gibsOffline) meta = "not available offline";
    else if (gibsOn[l.key] && l.key === "goes") {
      const f = goes?.frames[goesShown];
      meta = f ? `${timeLabel(l, f.time)} · ${l.source}` : goes?.error ? "unavailable" : "loading…";
    } else if (gibsOn[l.key])
      meta = l.key in gibsLatest ? `${timeLabel(l, gibsWhen(l.key))} · ${l.source}` : "loading…";
    return {
      id: `gibs-${l.key}`,
      label: l.label,
      meta,
      checked: gibsOn[l.key],
      disabled: gibsOffline,
      reason: gibsOffline
        ? offlineReason(off, /imagery|NASA|satellite|tile/i)
        : `${l.product}. ${l.rule[0].toUpperCase()}${l.rule.slice(1)}.`,
      onToggle: () => setGibsOn((s) => ({ ...s, [l.key]: !s[l.key] })),
    };
  });
  // the still layers that are on and can take a date
  const gibsDated = gibsOffline
    ? []
    : GIBS_LAYERS.filter((l) => l.key !== "goes" && gibsOn[l.key] && l.key in gibsLatest);

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
      {climate && !climate.disabled && (
        <section className="px-3.5 py-3">
          <h2 className="section-title mb-2">Current conditions</h2>
          <StatTile
            label="Stations reporting"
            value={climate.headline ?? "-"}
            sub="ECONet research + RAWS fire-weather stations, via the NC State Climate Office CLOUDS API."
          />
          {(() => {
            const fire = (climate.data.features ?? []).filter((f) => f.properties.severity >= 2);
            return fire.length ? (
              <p className="mt-2 rounded-sm bg-dmg1/15 px-1.5 py-1 text-2xs text-dmg1">
                {fire.length} RAWS station{fire.length > 1 ? "s" : ""} at fire-weather risk (low fuel moisture +
                wind)
              </p>
            ) : null;
          })()}
        </section>
      )}

      <section className="px-3.5 py-3">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="section-title">Flood forecast</h2>
          <span className="cap">{gauge?.headline ?? "…"}</span>
        </div>
        {gauge ? (
          <RankedList
            items={floodItems}
            empty="No river forecasts above action stage."
          />
        ) : (
          <p className="flex items-center gap-2 text-xs text-ink-faint">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-line-strong border-t-transparent" />
            Loading river forecasts…
          </p>
        )}
      </section>

      <section className="px-3.5 py-3">
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
        <section className="px-3.5 py-3">
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

      <section className="px-3.5 py-3">
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
        <section className="px-3.5 py-3">
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
          <section className="px-3.5 py-3">
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
            <h1 className="title-display whitespace-nowrap text-[17px] leading-tight text-ink">Conditions · North Carolina</h1>
            <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
              <span
                className={`h-1.5 w-1.5 rounded-full ${anyStale ? "bg-st-warn" : "bg-st-ok"}`}
              />
              {anyStale ? "cached" : "live"}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-ink-dim">
            Rivers, warnings, power, shelters, storms and roads, before and during a
            disaster. Live feeds cover North Carolina today.
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

            <div className="mt-3 border-t border-line pt-2.5">
              <p className="mb-2 text-2xs font-medium text-ink-dim">NASA satellite imagery</p>
              <LayerToggles rows={gibsRows} />
              {gibsDated.map((l) => (
                <GibsDateControl
                  key={l.key}
                  layer={l}
                  time={gibsWhen(l.key)}
                  latest={gibsLatest[l.key] ?? null}
                  onChange={(t) => setGibsPick((s) => ({ ...s, [l.key]: t }))}
                  onStep={(n) =>
                    setGibsPick((s) => {
                      const from = s[l.key] ?? gibsLatest[l.key];
                      if (!from) return s;
                      const to = shiftTime(l, from, n);
                      const latest = gibsLatest[l.key];
                      if ((latest && to > latest) || (l.since && to < l.since)) return s;
                      return { ...s, [l.key]: to };
                    })
                  }
                />
              ))}
            </div>

            <details className="mt-2 text-2xs text-ink-faint">
              <summary className="cursor-pointer hover:text-ink">Optional data keys</summary>
              <p className="mt-1.5 leading-relaxed">
                A free NC State Climate Office CLOUDS key adds current conditions: temperature, wind, rain
                and fire-weather stations.
              </p>
              <KeyForm
                hasKey={!!settings.cloudsKey}
                placeholder="CLOUDS API hash"
                removeLabel="remove CLOUDS key"
                onAdd={(v) => set("cloudsKey", v)}
                onRemove={() => set("cloudsKey", undefined)}
              />
            </details>

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
                  style={{ background: `rgb(${SHELTER_RGB.join(",")})` }}
                />
                open shelter
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
      <aside className="absolute right-3 top-3 z-20 hidden max-h-[calc(100%-1.5rem)] w-[20rem] flex-col overflow-y-auto md:flex lg:right-4 lg:top-4">
        <div className="panel divide-y divide-line overflow-hidden">
          <div className="flex items-center justify-between px-3.5 py-2.5">
            <span className="text-sm font-semibold text-ink">Now</span>
            <span className="text-xs text-ink-faint">{anyStale ? "some feeds cached" : "all feeds live"}</span>
          </div>
          {riskPanels}
        </div>
      </aside>

      {/* mobile: a compact state strip that opens the full sheet. Right edge
          clears the map's own bottom-right zoom/compass control (~52px) so
          the sheet's rounded corner doesn't sit on top of the compass button. */}
      <div className="absolute bottom-3 left-3 right-14 z-20 md:hidden">
        {riskOpen ? (
          <div className="panel flex max-h-[70vh] flex-col divide-y divide-line overflow-y-auto">
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

      {/* GOES-East loop strip, stacked above the radar strip when both are on */}
      {gibsOn.goes && !gibsOffline && (
        <div
          className={`absolute left-1/2 z-20 w-[min(420px,calc(100%-1.5rem))] -translate-x-1/2 ${
            radarOn ? "bottom-[8.5rem] md:bottom-[4.5rem]" : "bottom-20 md:bottom-4"
          }`}
        >
          <div className="panel flex items-center gap-3 px-3 py-2">
            <button
              onClick={() => setGoesPlaying((p) => !p)}
              disabled={goesReady.length < 2}
              className="pressable grid h-7 w-7 shrink-0 place-items-center rounded-md bg-accent text-accent-ink disabled:opacity-45"
              aria-label={goesPlaying ? "Pause GOES-East loop" : "Play GOES-East loop"}
            >
              {goesPlaying ? (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
                  <rect x="2" y="1.5" width="3" height="9" rx="0.6" />
                  <rect x="7" y="1.5" width="3" height="9" rx="0.6" />
                </svg>
              ) : (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
                  <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.6-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
                </svg>
              )}
            </button>
            <input
              type="range"
              min={0}
              max={Math.max(0, (goes?.frames.length ?? 1) - 1)}
              value={goesIdx}
              disabled={!goes?.frames.length}
              onChange={(e) => {
                setGoesPlaying(false);
                setGoesIdx(Number(e.target.value));
              }}
              aria-label="GOES-East image"
              className="ba-range h-1 flex-1 cursor-pointer accent-accent"
            />
            <div className="tnum shrink-0 text-right text-2xs leading-tight text-ink-dim">
              <div className="text-ink">GOES-East GeoColor</div>
              {goes?.error ? (
                <div className="text-ink-faint">{goes.error}</div>
              ) : goes && goes.frames[goesShown] ? (
                <div className="text-ink-faint">
                  {utcHHMM(goes.frames[goesShown].at)} UTC · {agoLabel(goes.frames[goesShown].at)}
                </div>
              ) : (
                <div className="text-ink-faint">Finding the newest images…</div>
              )}
              {goes && !goes.error && goesReady.length < goes.frames.length && (
                <div className="text-ink-faint">
                  Loading images {goesReady.length} of {goes.frames.length}
                </div>
              )}
            </div>
          </div>
        </div>
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

/** Date (or half-hour) control for one NASA layer: its GIBS product name, the
 * time shown, earlier / later steps, the date rule and the GIBS legend. */
function GibsDateControl({
  layer,
  time,
  latest,
  onChange,
  onStep,
}: {
  layer: GibsLayer;
  time: string | null;
  latest: string | null;
  onChange: (t: string) => void;
  onStep: (n: number) => void;
}) {
  const daily = layer.step === "P1D";
  const unit = daily ? "day" : "half hour";
  const atLatest = !time || !latest || time >= latest;
  const atFirst = !time || (!!layer.since && time <= layer.since);
  const step = "pressable grid h-5 w-5 shrink-0 place-items-center rounded-sm border border-line text-ink-dim hover:text-ink disabled:opacity-40";
  return (
    <div className="mt-2 rounded-md border border-line px-2 py-1.5">
      <p className="text-2xs leading-snug text-ink">{layer.product}</p>
      <div className="mt-1 flex items-center gap-1.5">
        <button
          className={step}
          disabled={atFirst}
          onClick={() => onStep(-1)}
          aria-label={`${layer.label}: one ${unit} earlier`}
        >
          ‹
        </button>
        {daily ? (
          <input
            type="date"
            value={time ?? ""}
            min={layer.since}
            max={latest ?? undefined}
            disabled={!time}
            onChange={(e) => e.target.value && onChange(e.target.value)}
            aria-label={`${layer.label} date, UTC`}
            className="tnum min-w-0 flex-1 rounded-sm border border-line bg-transparent px-1 text-2xs text-ink"
          />
        ) : (
          <span className="tnum flex-1 text-center text-2xs text-ink">{timeLabel(layer, time)}</span>
        )}
        <button
          className={step}
          disabled={atLatest}
          onClick={() => onStep(1)}
          aria-label={`${layer.label}: one ${unit} later`}
        >
          ›
        </button>
        {daily && <span className="text-2xs text-ink-faint">UTC</span>}
      </div>
      <p className="mt-1 text-2xs leading-snug text-ink-faint">
        {layer.rule[0].toUpperCase()}
        {layer.rule.slice(1)}. {layer.source}.
      </p>
      {layer.legend && (
        <img
          src={layer.legend}
          alt={`${layer.product} legend`}
          className="mt-1.5 w-3/4 rounded-sm bg-white p-0.5"
        />
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
