/* Hallmark · screen: Assess · macrostructure: Workbench (rail · map · inspector)
 * The screen answers one question at a time: where is it worst (rail and
 * overview), what does this area look like (map), what should I do next
 * (inspector tabs, with the next step written out). */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { Marker } from "maplibre-gl";
import { toast } from "sonner";
import OwnerLink from "../components/ops/OwnerLink";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import { useTheme } from "../lib/theme";
import {
  FEMA,
  FEMA_HEX,
  FEMA_LABEL,
  HAZARD_LABEL,
  NOT_ASSESSED_HEX,
  POST_SOURCE_LABEL,
  PRE_SOURCE_LABEL,
  ago,
  cancelJob,
  checkCoverageFull,
  createEvent,
  deleteArea,
  downloadExport,
  downloadIda,
  eventFromFema,
  fmtDuration,
  imageryDate,
  imageryTileUrl,
  isOpsUrl,
  jobActive,
  labelerName,
  loadChip,
  loadEvents,
  loadFemaReference,
  loadReferences,
  loadResponseLayers,
  type ResponseLayers,
  loadImpact,
  loadJobs,
  loadLabels,
  loadOpsArea,
  loadOpsAreas,
  loadResponder,
  occupantsOf,
  openBrief,
  opsRequestHeaders,
  postLabel,
  pSevere,
  reassessArea,
  publicUrl,
  reviewPriority,
  setLabelerName,
  submitAssessment,
  type FemaClass,
  type FemaEventDraft,
  type FemaReference,
  type ImageryRecord,
  type Impact,
  type Job,
  type OpsAreaSummary,
  type OpsCollection,
  type OpsEvent,
  type OpsFeature,
  type OpsProps,
} from "../lib/ops";
import { API_URL } from "../lib/catalog";
import { loadOffline, offlineReason, useOffline } from "../lib/offline";
import { AccuracyNote } from "../components/ops/SystemPanels";
import SwipeCompare from "../components/map/SwipeCompare";
import { heightOf, useBuildings3D } from "../components/map/useBuildings3D";
import References from "../components/ops/References";
import Respond from "../components/ops/Respond";
import {
  Button,
  DamageStrip,
  Disclosure,
  Empty,
  Figure,
  Icon,
  Kbd,
  Popover,
  Segmented,
  Spinner,
  Swatch,
  Tabs,
  Tag,
} from "../components/ui/kit";
import { btnClass } from "../components/ui/classes";

type RGBA = [number, number, number, number];
const hexRgb = (h: string): [number, number, number] => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];
/** the needs-review outline: blue, off the damage ramp, legible on imagery */
const REVIEW: [number, number, number] = [37, 99, 235];
/** the interface accent (bronze), for the extent a new assessment covers */
const ACCENT: [number, number, number] = [142, 91, 39];
const NC_CENTER: [number, number] = [-81.2, 35.5];

/** Which of the assessment's own images sits under the structures. */
type ImageryMode = "post" | "pre" | "swipe" | "off";
type Tab = "overview" | "review" | "respond" | "people" | "checks";
type LevelKey = FemaClass | "none";

/** The square a new assessment would cover: centre + half-width in metres. */
interface Preview {
  lon: number;
  lat: number;
  half_m: number;
}
const previewRing = ({ lon, lat, half_m }: Preview): [number, number][] => {
  const dLat = half_m / 111_320;
  const dLon = half_m / (111_320 * Math.cos((lat * Math.PI) / 180));
  return [
    [lon - dLon, lat - dLat],
    [lon + dLon, lat - dLat],
    [lon + dLon, lat + dLat],
    [lon - dLon, lat + dLat],
  ];
};

/** The name an analyst gave the area; older assessments only have their id. */
const areaTitle = (id: string, name?: string) =>
  name ||
  id
    .replace(/_[0-9a-f]{4}$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

const sevOf = (a: { expected_counts: Partial<Record<FemaClass, number>> }) =>
  (a.expected_counts.major ?? 0) + (a.expected_counts.destroyed ?? 0);
const sevRange = (a: { expected_counts_80pct?: Partial<Record<FemaClass, [number, number]>> }) => {
  const r = a.expected_counts_80pct ?? {};
  return [(r.major?.[0] ?? 0) + (r.destroyed?.[0] ?? 0), (r.major?.[1] ?? 0) + (r.destroyed?.[1] ?? 0)];
};
const n0 = (v: number | undefined | null) => Math.round(v ?? 0).toLocaleString();
const isTyping = (t: EventTarget | null) =>
  !!t && ["INPUT", "TEXTAREA", "SELECT"].includes((t as HTMLElement).tagName);

/** An absolute as-of stamp in the viewer's zone: "26 Sep 2026 01:38 EDT". */
const fmtStamp = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
const hazardsOf = (p: { provenance?: Record<string, unknown> }): string[] =>
  ((p.provenance?.hazards as { event_hazards?: string[] } | undefined)?.event_hazards ?? []).slice(0, 4);

/** In the review queue: flagged, read from imagery, and not yet labelled. The
 * queue, the legend count and the "needs review only" filter all use this. */
const isOpen = (p: OpsProps, labels: Record<string, string>) => p.needs_review && !!p.damage_level && !labels[p.ncr_id];

const ROLE_TITLE: Record<string, string> = {
  TEST: "Held-out evaluation area: never used to tune",
  TUNE: "Tuning area: thresholds may be fitted here",
  OPS: "Operational area",
};

// --------------------------------------------------------------------------- //
export default function Ops({
  areaId,
  onPickArea,
}: {
  areaId: string | null;
  onPickArea: (id: string | null) => void;
}) {
  const [areas, setAreas] = useState<OpsAreaSummary[] | null>(null);
  const [areasErr, setAreasErr] = useState<string | null>(
    API_URL ? null : "no assessment service configured",
  );
  const [fc, setFc] = useState<OpsCollection | null>(null);
  const [areaErr, setAreaErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [hidden, setHidden] = useState<Set<LevelKey>>(() => new Set());
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [addresses, setAddresses] = useState<Record<string, string>>({});
  const [newOpen, setNewOpen] = useState(false);
  const [pick, setPick] = useState<[number, number] | null>(null);
  const [picking, setPicking] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [imagery, setImagery] = useState<ImageryMode>("post");
  // 3D is a toggle, never the default; terrain is a further opt-in inside it
  const [view3d, setView3d] = useState(false);
  const [terrain, setTerrain] = useState(false);
  // offline: no new assessments (they fetch imagery) and no terrain tiles
  const off = useOffline();
  const noNew = off?.offline ? offlineReason(off, /assess/i) : null;
  // hold B: the before-event image, for as long as the key is down
  const [peek, setPeek] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  // the Respond tab draws its own layers and can centre the map on a place
  const [resp, setResp] = useState<ResponseLayers | null>(null);
  const [focus, setFocus] = useState<{ ll: [number, number]; n: number } | null>(null);
  const [eventPick, setEventPick] = useState<string | null>(null);
  const latestEvent = useMemo(() => {
    const evs = (areas ?? []).map((a) => a.event).filter(Boolean);
    evs.sort((a, b) => (b.incident_begin ?? "").localeCompare(a.incident_begin ?? ""));
    return evs[0]?.id ?? null;
  }, [areas]);
  const fitEvent = eventPick ?? latestEvent;
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (tab !== "respond" || !areaId) return;
    let live = true;
    loadResponseLayers(areaId)
      .then((d) => live && setResp(d))
      .catch(() => live && setResp(null));
    return () => {
      live = false;
    };
  }, [tab, areaId, reload]);
  // optional note saved with the next label; cleared when the structure changes
  const [note, setNote] = useState("");
  const select = useCallback((id: string | null) => {
    setSelected(id);
    setNote("");
    if (id) setTab("review");
  }, []);

  const refreshAreas = useCallback(() => {
    if (!API_URL) return;
    loadOpsAreas()
      .then((a) => {
        setAreas(a);
        setAreasErr(null);
      })
      .catch((e: Error) => setAreasErr(e.message));
  }, []);
  useEffect(refreshAreas, [refreshAreas]);

  // Assessment jobs live on the server (and survive its restarts), so the list
  // is polled rather than held here: 4 s while one is going, 30 s otherwise so
  // a job a colleague started still shows up.
  const [jobs, setJobs] = useState<Job[]>([]);
  const lastStatus = useRef(new Map<string, Job["status"]>());
  const watching = useRef<string | null>(null); // the job submitted from this form
  const refreshJobs = useCallback(async () => {
    if (!API_URL) return;
    let list: Job[];
    try {
      list = await loadJobs();
    } catch {
      return; // no responder token yet, or the service is away: keep what we have
    }
    for (const j of list) {
      const was = lastStatus.current.get(j.id);
      lastStatus.current.set(j.id, j.status);
      if (!was || was === j.status || (was !== "queued" && was !== "running")) continue;
      if (j.status === "done") {
        toast.success(
          j.warnings?.length
            ? `${j.name}: assessment complete, with warnings`
            : `${j.name}: assessment complete`,
        );
        refreshAreas();
        if (j.area === areaId) setReload((n) => n + 1); // this area, assessed again
        else if (watching.current === j.id) onPickArea(j.area);
        if (watching.current === j.id) watching.current = null;
      } else if (j.status === "failed") toast.error(`${j.name}: ${j.error ?? "assessment failed"}`);
      else if (j.status === "lost") toast.error(`${j.name}: ${j.error ?? "assessment lost"}`);
    }
    setJobs(list);
  }, [refreshAreas, onPickArea, areaId]);
  const anyActive = jobs.some(jobActive);
  useEffect(() => {
    const tick = () => void refreshJobs();
    const first = window.setTimeout(tick, 0);
    const t = window.setInterval(tick, anyActive ? 4000 : 30000);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(t);
    };
  }, [refreshJobs, anyActive]);

  // the screen is remounted per area (key={areaId} in App), so state starts
  // clean; `reload` bumps when this area has been assessed again
  useEffect(() => {
    if (!areaId) return;
    let live = true;
    loadOpsArea(areaId)
      .then((d) => live && setFc(d))
      .catch((e: Error) => live && setAreaErr(e.message));
    loadLabels(areaId)
      .then((rows) => {
        if (!live) return;
        const m: Record<string, string> = {};
        for (const r of rows) m[r.ncr_id] = r.label;
        setLabels(m);
      })
      .catch(() => {});
    // offline packs leave addresses out (they stay with the EOC), so the
    // responder file is never there to ask for
    loadOffline()
      .then((o) => (o?.offline ? Promise.reject(new Error("offline")) : loadResponder(areaId)))
      .then((d) => {
        if (!live) return;
        const m: Record<string, string> = {};
        for (const [k, v] of Object.entries(d.structures)) m[k] = v.address;
        setAddresses(m);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [areaId, reload]);

  const byId = useMemo(() => {
    const m = new Map<string, OpsFeature>();
    for (const f of fc?.features ?? []) m.set(f.properties.ncr_id, f as OpsFeature);
    return m;
  }, [fc]);

  const queue = useMemo(
    () =>
      (fc?.features ?? [])
        .map((f) => f.properties)
        .filter((p) => isOpen(p, labels))
        .sort((a, b) => reviewPriority(b) - reviewPriority(a)),
    [fc, labels],
  );

  const sel = selected ? (byId.get(selected) ?? null) : null;

  const label = useCallback(
    async (p: OpsProps, lab: string) => {
      if (!areaId) return;
      let who = labelerName();
      if (!who) {
        who = window.prompt("Your name or initials (recorded with each label)") ?? "";
        if (!who.trim()) return;
        setLabelerName(who);
      }
      try {
        const r = await postLabel({
          area: areaId,
          ncr_id: p.ncr_id,
          label: lab,
          labeler: who,
          notes: note.trim() || undefined,
        });
        setLabels((m) => ({ ...m, [p.ncr_id]: lab }));
        toast.success(`Recorded "${lab.replace("_", " ")}" (${r.aoi_role} area)`);
        const next = queue.find((q) => q.ncr_id !== p.ncr_id);
        if (next) select(next.ncr_id);
        else setNote("");
      } catch (e) {
        toast.error((e as Error).message);
      }
    },
    [areaId, queue, note, select],
  );

  // keyboard: 0-4 label, x cannot tell, j/k next/previous, Esc close (with a
  // structure open); N new assessment; hold B to see the before image
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if ((e.key === "b" || e.key === "B") && fc && imagery !== "off") {
        if (!e.repeat) setPeek(true);
        return;
      }
      if (!sel) {
        if (e.key === "n" && API_URL && !noNew) {
          e.preventDefault();
          setNewOpen(true);
        }
        return;
      }
      const i = "01234".indexOf(e.key);
      if (i >= 0) {
        e.preventDefault();
        void label(sel.properties, FEMA[i]);
      } else if (e.key === "x") {
        e.preventDefault();
        void label(sel.properties, "cannot_tell");
      } else if (e.key === "j" || e.key === "k") {
        const idx = queue.findIndex((q) => q.ncr_id === sel.properties.ncr_id);
        const n = queue[e.key === "j" ? idx + 1 : Math.max(0, idx - 1)];
        if (n) select(n.ncr_id);
      } else if (e.key === "Escape") {
        select(null);
      }
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key === "b" || e.key === "B") setPeek(false);
    };
    const onBlur = () => setPeek(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onUp);
      window.removeEventListener("blur", onBlur);
    };
  }, [sel, queue, label, select, fc, imagery, noNew]);

  const onSubmitted = useCallback(
    (j: Job) => {
      watching.current = j.id;
      lastStatus.current.set(j.id, j.status);
      setJobs((cur) => [j, ...cur.filter((x) => x.id !== j.id)]);
      setNewOpen(false);
      setPick(null);
      setPicking(false);
      void refreshJobs();
    },
    [refreshJobs],
  );
  const onCancelJob = useCallback(
    async (j: Job) => {
      try {
        await cancelJob(j.id);
        if (watching.current === j.id) watching.current = null;
        toast(`${j.name}: assessment cancelled`);
      } catch (e) {
        toast.error((e as Error).message);
      }
      void refreshJobs();
    },
    [refreshJobs],
  );
  const onPick = useCallback((ll: [number, number] | null) => {
    setPicking(false);
    if (ll) {
      setPick(ll);
      setNewOpen(true);
    }
  }, []);

  // swipe compares two flat maps: in 3D the after image stays under the buildings
  const shownImagery: ImageryMode = peek && fc ? "pre" : view3d && imagery === "swipe" ? "post" : imagery;
  const records = (fc?.properties.provenance?.imagery ?? []) as ImageryRecord[];

  return (
    // phone: one scrolling column. md: rail on the left, map over the
    // inspector on the right. xl: three columns, each scrolling by itself.
    <div className="grid h-full min-h-0 grid-cols-1 overflow-y-auto md:grid-cols-[288px_1fr] md:grid-rows-[minmax(0,3fr)_minmax(0,2fr)] md:overflow-hidden xl:grid-cols-[288px_1fr_408px] xl:grid-rows-1">
      {/* ---------------------------- rail ---------------------------- */}
      <aside
        className={`flex flex-col border-line bg-surface md:row-span-2 md:min-h-0 md:border-r xl:row-span-1 ${
          areaId ? "order-last border-t md:order-none md:border-t-0" : "border-b md:border-b-0"
        }`}
        aria-label="Assessed areas"
      >
        <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line px-3">
          <h2 className="text-sm font-semibold text-ink">Areas</h2>
          {areas && <span className="tnum font-mono text-xs text-ink-faint">{areas.length}</span>}
          <Button
            variant="primary"
            size="sm"
            className="ml-auto"
            icon={<Icon name="plus" className="h-3.5 w-3.5" />}
            onClick={() => setNewOpen(true)}
            disabled={!API_URL || !!noNew}
            title={noNew ?? "New assessment (N)"}
          >
            New assessment
          </Button>
        </div>
        <div className="md:min-h-0 md:flex-1 md:overflow-y-auto">
          <JobsPanel jobs={jobs} onOpen={onPickArea} onCancel={onCancelJob} />
          <AreaList
            areas={areas}
            err={areasErr}
            areaId={areaId}
            onPick={onPickArea}
            framed={areaId ? null : fitEvent}
            onFrame={(id) => {
              setEventPick(id);
              if (areaId) onPickArea(null);
            }}
          />
        </div>
      </aside>

      {/* ---------------------------- map ----------------------------- */}
      <section className="relative min-h-[60vh] bg-canvas md:min-h-0" aria-label="Map">
        <OpsMap
          fc={fc}
          areaId={areaId}
          imagery={shownImagery}
          areas={areaId ? null : areas}
          onOpenArea={onPickArea}
          selected={selected}
          reviewOnly={reviewOnly}
          hidden={hidden}
          labels={labels}
          onSelect={select}
          picking={picking}
          preview={newOpen ? preview : null}
          onPick={onPick}
          resp={tab === "respond" ? resp : null}
          focus={focus}
          fitEvent={areaId ? null : fitEvent}
          view3d={!!areaId && view3d}
          terrain={terrain && !off?.offline}
          beforeLabel={imageryDate(records.find((r) => r.role === "pre"))}
          afterLabel={imageryDate(records.find((r) => r.role === "post"))}
        />
        {picking && (
          <div className="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-2 rounded bg-ink px-3 py-1.5 text-[13px] font-medium text-canvas">
            <Icon name="target" className="h-3.5 w-3.5" />
            Click the map to set the centre <Kbd className="border-canvas/30 bg-transparent text-canvas/80">Esc</Kbd>
          </div>
        )}
        {fc && (
          <div className="absolute left-3 top-3 z-10">
            <ImageryBar
              mode={imagery}
              onMode={setImagery}
              records={records}
              peek={peek}
              view3d={view3d}
              onView3d={setView3d}
              terrain={terrain}
              onTerrain={setTerrain}
            />
          </div>
        )}
        {fc && peek && (
          <div className="pointer-events-none absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded bg-ink/85 px-3 py-1 text-[13px] font-semibold text-canvas">
            Before · {imageryDate(records.find((r) => r.role === "pre"))}
          </div>
        )}
        {fc && fc.features.length > 0 && (
          <div className="absolute bottom-3 left-3 z-10">
            <LegendFilter
              fc={fc}
              labels={labels}
              hidden={hidden}
              onToggle={(k) =>
                setHidden((h) => {
                  const n = new Set(h);
                  if (n.has(k)) n.delete(k);
                  else n.add(k);
                  return n;
                })
              }
              reviewOnly={reviewOnly}
              onReviewOnly={setReviewOnly}
              view3d={view3d}
            />
          </div>
        )}
        {fc && fc.features.length === 0 && (
          <MapNotice>
            <b>No structures found here.</b> FEMA USA Structures, OpenStreetMap and the USACE inventory
            list no buildings in this area, so nothing was assessed. If buildings are known to be here,
            verify on the ground.
          </MapNotice>
        )}
        {!fc && areaId && (
          <MapNotice>
            {areaErr ? (
              /40[13]/.test(areaErr) ? (
                <>
                  Structure-level results need responder access (<Icon name="key" className="inline h-3.5 w-3.5" />{" "}
                  in the top bar). The public summary needs none.
                </>
              ) : (
                `Could not load this assessment (${areaErr}).`
              )
            ) : (
              <span className="inline-flex items-center gap-2">
                <Spinner /> Loading assessment…
              </span>
            )}
          </MapNotice>
        )}
      </section>

      {/* -------------------------- inspector ------------------------- */}
      <aside
        className="flex flex-col border-t border-line bg-surface md:min-h-0 xl:border-l xl:border-t-0"
        aria-label="Inspector"
      >
        {newOpen ? (
          <NewAssessment
            pick={pick}
            picking={picking}
            onPickToggle={() => setPicking((v) => !v)}
            onPreview={setPreview}
            onSubmitted={onSubmitted}
            onClose={() => {
              setNewOpen(false);
              setPicking(false);
            }}
          />
        ) : !areaId ? (
          <Overview areas={areas} err={areasErr} onOpen={onPickArea} onNew={() => setNewOpen(true)} />
        ) : fc ? (
          <AreaInspector
            fc={fc}
            areaId={areaId}
            reload={reload}
            tab={tab}
            onTab={setTab}
            queue={queue}
            labels={labels}
            sel={sel}
            address={sel ? addresses[sel.properties.ncr_id] : undefined}
            note={note}
            onNote={setNote}
            onLabel={(lab) => sel && void label(sel.properties, lab)}
            onSelect={select}
            onFocus={(ll) => setFocus((f) => ({ ll, n: (f?.n ?? 0) + 1 }))}
            rerunning={jobs.some((j) => j.area === areaId && jobActive(j))}
            onRerun={async () => {
              try {
                onSubmitted(await reassessArea(areaId));
              } catch (e) {
                toast.error((e as Error).message);
              }
            }}
            onDeleted={() => {
              refreshAreas();
              onPickArea(null);
            }}
          />
        ) : (
          <div className="p-4 text-sm text-ink-dim">{areaErr ? "This assessment is not available." : "Loading…"}</div>
        )}
      </aside>
    </div>
  );
}

function MapNotice({ children }: { children: ReactNode }) {
  return (
    <div className="panel absolute inset-x-3 top-16 z-10 mx-auto w-fit max-w-md px-4 py-3 text-[13px] leading-relaxed text-ink">
      {children}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// rail: jobs and areas
// --------------------------------------------------------------------------- //
const STEPS = ["choosing imagery", "fetching imagery", "assessing structures", "estimating people", "writing brief"];

const JOB_STATUS: Record<Job["status"], string> = {
  queued: "Waiting for the previous assessment",
  running: "Running",
  done: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
  lost: "Interrupted",
};
const JOB_SHOWN_FOR_S = 24 * 3600;
const CANCELLED_SHOWN_FOR_S = 10 * 60;
const DISMISSED_KEY = "terratriage:dismissedJobs";

/** Assessments in progress, and what happened to the recent ones. The list is
 * the server's, so it is the same for every analyst and after a restart. */
function JobsPanel({
  jobs,
  onOpen,
  onCancel,
}: {
  jobs: Job[];
  onOpen: (area: string) => void;
  onCancel: (job: Job) => void;
}) {
  // re-render once a second while something runs, for the elapsed time
  const [now, setNow] = useState(() => Date.now() / 1000);
  const anyActive = jobs.some(jobActive);
  useEffect(() => {
    if (!anyActive) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, [anyActive]);
  // dismissed cards stay dismissed in this browser (the screen remounts per area)
  const [dismissed, setDismissed] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? "[]") as string[]);
    } catch {
      return new Set();
    }
  });
  const dismiss = (id: string) =>
    setDismissed((d) => {
      const next = new Set(d).add(id);
      try {
        localStorage.setItem(DISMISSED_KEY, JSON.stringify([...next].slice(-100)));
      } catch {
        /* private window: dismissed until the next reload */
      }
      return next;
    });
  // what is running first, then the queue in the order it will run, then
  // what stopped, most recent first
  const rank = (j: Job) => (j.status === "running" ? 0 : j.status === "queued" ? 1 : 2);
  const shown = jobs
    .filter(
      (j) =>
        jobActive(j) ||
        (!dismissed.has(j.id) &&
          j.status !== "done" &&
          // a failure stays until dismissed (for a day); a cancellation was
          // someone's own choice and only needs to be seen briefly
          now - (j.finished ?? j.created) <
            (j.status === "cancelled" ? CANCELLED_SHOWN_FOR_S : JOB_SHOWN_FOR_S)),
    )
    .sort(
      (a, b) =>
        rank(a) - rank(b) ||
        (jobActive(a) ? a.created - b.created : (b.finished ?? 0) - (a.finished ?? 0)),
    );
  if (shown.length === 0) return null;
  return (
    <section className="border-b border-line p-3" aria-label="Assessments in progress">
      <div className="label mb-2">In progress</div>
      <ul className="space-y-2">
        {shown.map((j) => (
          <li key={j.id}>
            <JobCard job={j} now={now} onOpen={onOpen} onCancel={onCancel} onDismiss={() => dismiss(j.id)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function JobCard({
  job,
  now,
  onOpen,
  onCancel,
  onDismiss,
}: {
  job: Job;
  now: number;
  onOpen: (area: string) => void;
  onCancel: (job: Job) => void;
  onDismiss: () => void;
}) {
  // a re-run reuses the imagery already on disk
  const steps = job.kind === "reassess" ? STEPS.slice(2) : STEPS;
  const cur = steps.indexOf(job.step);
  const done = job.status === "done";
  const active = jobActive(job);
  const stopped = !active && !done;
  const frac = done ? 1 : cur < 0 ? 0 : (cur + (job.status === "running" ? 0.5 : 0)) / steps.length;
  return (
    <div className="rounded border border-line bg-canvas p-2.5 text-[13px]">
      <div className="flex items-center gap-2">
        {active ? <Spinner className="text-accent" /> : <Icon name={stopped ? "alert" : "check"} className={`h-3.5 w-3.5 ${stopped ? "text-st-bad" : "text-st-ok"}`} />}
        <span className="flex-1 truncate font-semibold text-ink">{job.name}</span>
        {job.status === "running" && job.started != null && (
          <span className="tnum font-mono text-xs text-ink-faint">{fmtDuration(now - job.started)}</span>
        )}
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-2">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${stopped ? "bg-st-bad" : "bg-accent"}`}
          style={{ width: `${Math.max(4, frac * 100)}%` }}
        />
      </div>
      <div className="mt-1.5 text-xs text-ink-dim" role="status">
        {job.kind === "reassess" && "Run again · "}
        {job.status === "running" && cur >= 0 ? `${cur + 1} of ${steps.length}: ${steps[cur]}` : JOB_STATUS[job.status]}
        {job.post_source && ` · ${POST_SOURCE_LABEL[job.post_source]?.split(" (")[0] ?? job.post_source}`}
        {stopped && job.finished != null && ` · ${ago(job.finished)}`}
      </div>
      {(job.status === "failed" || job.status === "lost") && job.error && (
        <p className="mt-1.5 text-xs text-st-bad">{job.error}</p>
      )}
      {job.warnings && job.warnings.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-ink-dim">
          {job.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex gap-1.5">
        {active && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              if (
                job.status === "queued" ||
                window.confirm(`Stop the assessment "${job.name}"? What it has fetched so far is discarded.`)
              )
                onCancel(job);
            }}
          >
            Cancel
          </Button>
        )}
        {done && (
          <Button size="sm" onClick={() => onOpen(job.area)}>
            Open
          </Button>
        )}
        {stopped && (
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        )}
      </div>
    </div>
  );
}

function AreaList({
  areas,
  err,
  areaId,
  onPick,
  framed,
  onFrame,
}: {
  areas: OpsAreaSummary[] | null;
  err: string | null;
  areaId: string | null;
  onPick: (id: string) => void;
  /** the event the overview map is framed on */
  framed: string | null;
  onFrame: (eventId: string) => void;
}) {
  const [q, setQ] = useState("");
  const off = useOffline();
  const noNew = off?.offline ? offlineReason(off, /assess/i) : null;
  const groups = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const m = new Map<string, { id: string; name: string; decl: string[]; rows: OpsAreaSummary[] }>();
    for (const a of areas ?? []) {
      const hay = `${areaTitle(a.id, a.aoi.name)} ${a.aoi.county ?? ""}`.toLowerCase();
      if (ql && !hay.includes(ql)) continue;
      const k = a.event?.id ?? "event";
      if (!m.has(k)) m.set(k, { id: k, name: a.event?.name ?? "Event", decl: a.event?.declarations ?? [], rows: [] });
      m.get(k)!.rows.push(a);
    }
    for (const g of m.values()) g.rows.sort((a, b) => sevOf(b) - sevOf(a));
    return [...m.values()];
  }, [areas, q]);
  if (err && !areas)
    return (
      <div className="p-3">
        <Empty icon="alert" title="Assessment service unreachable">
          {err}
        </Empty>
      </div>
    );
  if (!areas)
    return (
      <div className="space-y-2 p-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skel h-16" />
        ))}
      </div>
    );
  if (areas.length === 0)
    return (
      <div className="p-3">
        <Empty icon="map" title="No assessments yet">
          {noNew ?? (
            <>
              Start one with <b className="text-ink">New assessment</b>, or press <Kbd>N</Kbd>.
            </>
          )}
        </Empty>
      </div>
    );
  return (
    <div className="pb-3">
      {areas.length > 5 && (
        <div className="relative px-3 pt-3">
          <Icon name="search" className="pointer-events-none absolute left-5 top-[19px] h-3.5 w-3.5 text-ink-faint" />
          <input
            className="field pl-7"
            placeholder="Find an area or county"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Find an area"
          />
        </div>
      )}
      {groups.map((g) => (
        <section key={g.name} className="mt-3">
          <button
            className="flex w-full items-baseline justify-between gap-2 px-3 pb-1 text-left hover:text-ink"
            onClick={() => onFrame(g.id)}
            title={`Show ${g.name} on the map`}
            aria-pressed={framed === g.id}
          >
            <span className={`truncate text-xs font-semibold ${framed === g.id ? "text-accent" : "text-ink-dim"}`}>
              {g.name}
            </span>
            <span className="tnum shrink-0 font-mono text-xs text-ink-faint">{g.decl.join(", ")}</span>
          </button>
          <ul>
            {g.rows.map((a) => {
              const [lo, hi] = sevRange(a);
              const on = a.id === areaId;
              return (
                <li key={a.id}>
                  <button
                    onClick={() => onPick(a.id)}
                    aria-current={on ? "true" : undefined}
                    className={`w-full px-3 py-2 text-left ${
                      on ? "bg-accent-soft shadow-[inset_0_0_0_1px_rgb(var(--accent)/0.35)]" : "hover:bg-surface-2"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="flex-1 truncate text-[13px] font-semibold text-ink">
                        {areaTitle(a.id, a.aoi.name)}
                      </span>
                      {a.aoi.role !== "OPS" && (
                        <Tag tone={a.aoi.role === "TEST" ? "neutral" : "neutral"} title={ROLE_TITLE[a.aoi.role] ?? ""}>
                          {a.aoi.role}
                        </Tag>
                      )}
                    </div>
                    <DamageStrip counts={a.expected_counts} className="mt-1.5" height={5} />
                    <div className="tnum mt-1 flex items-baseline justify-between gap-2 font-mono text-xs">
                      <span className="shrink-0 whitespace-nowrap text-ink" title={`Expected at Major or Destroyed, 80% range ${lo}-${hi}`}>
                        ~{Math.round(sevOf(a)).toLocaleString()} ≥ Major
                      </span>
                      <span className="min-w-0 truncate text-ink-faint">
                        {a.n_needs_review.toLocaleString()} to review
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {groups.length === 0 && <p className="px-3 pt-3 text-[13px] text-ink-dim">No area matches “{q}”.</p>}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// inspector: overview (no area open)
// --------------------------------------------------------------------------- //
function Overview({
  areas,
  err,
  onOpen,
  onNew,
}: {
  areas: OpsAreaSummary[] | null;
  err: string | null;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const rows = useMemo(() => [...(areas ?? [])].sort((a, b) => sevOf(b) - sevOf(a)), [areas]);
  const off = useOffline();
  const noNew = off?.offline ? offlineReason(off, /assess/i) : null;
  const total = useMemo(() => {
    const t: Record<FemaClass, number> = { no_damage: 0, affected: 0, minor: 0, major: 0, destroyed: 0 };
    let structures = 0;
    let review = 0;
    for (const a of rows) {
      for (const c of FEMA) t[c] += a.expected_counts[c] ?? 0;
      structures += a.n_structures;
      review += a.n_needs_review;
    }
    return { t, structures, review };
  }, [rows]);
  const events = new Set(rows.map((a) => a.event?.id)).size;
  return (
    <div className="p-4 md:min-h-0 md:flex-1 md:overflow-y-auto">
      <h1 className="title-display text-[24px]">Overview</h1>
      {rows.length > 0 ? (
        <p className="mt-1 text-[13px] text-ink-dim">
          {rows.length} assessed area{rows.length > 1 ? "s" : ""} across {events} event{events > 1 ? "s" : ""}.
          Open the worst one first.
        </p>
      ) : (
        !err && (
          <p className="mt-1 text-[13px] text-ink-dim">Nothing assessed yet. Three steps to a first count:</p>
        )
      )}

      {rows.length === 0 && !err && areas && (
        <ol className="mt-4 space-y-3 text-[13px]">
          {[
            ["Pick the event", "Choose a registered event, or start one from its FEMA disaster number."],
            ["Pick the place", "Click the map at the town's centre and choose an area size."],
            ["Run it", "Imagery is found and every structure is read, in a few minutes."],
          ].map(([t, d], i) => (
            <li key={t} className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line-strong font-mono text-xs text-ink-dim">
                {i + 1}
              </span>
              <span>
                <b className="text-ink">{t}.</b> <span className="text-ink-dim">{d}</span>
              </span>
            </li>
          ))}
          <li>
            <Button variant="primary" onClick={onNew} kbd="N" disabled={!!noNew} title={noNew ?? undefined}>
              New assessment
            </Button>
            {noNew && <p className="mt-2 text-xs text-ink-dim">{noNew}</p>}
          </li>
        </ol>
      )}

      {rows.length > 0 && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-4 rounded border border-line p-3">
            <Figure big label="Expected at Major or Destroyed" value={`~${n0(total.t.major + total.t.destroyed)}`} />
            <Figure big label="Calls waiting for people" value={n0(total.review)} />
            <div className="col-span-2">
              <DamageStrip counts={total.t} height={8} />
              <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-dim">
                {FEMA.map((c) => (
                  <span key={c} className="inline-flex items-center gap-1">
                    <Swatch c={c} />
                    {FEMA_LABEL[c]} <span className="tnum font-mono text-ink">{n0(total.t[c])}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <table className="tnum mt-5 w-full text-[13px]">
            <caption className="label pb-2 text-left">Areas, worst first</caption>
            <thead>
              <tr className="text-xs text-ink-faint">
                <th className="pb-1 text-left font-medium">Area</th>
                <th className="pb-1 text-right font-medium" title="Expected at Major or Destroyed, with the 80% range">
                  ≥ Major
                </th>
                <th className="pb-1 text-right font-medium">To review</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const [lo, hi] = sevRange(a);
                return (
                  <tr key={a.id} className="border-t border-line align-top">
                    <td className="py-1.5 pr-2">
                      <button className="text-left font-semibold text-ink hover:text-accent" onClick={() => onOpen(a.id)}>
                        {areaTitle(a.id, a.aoi.name)}
                      </button>
                      <DamageStrip counts={a.expected_counts} height={4} className="mt-1 max-w-[180px]" />
                    </td>
                    <td className="py-1.5 text-right font-mono">
                      <span className="font-semibold text-ink">~{Math.round(sevOf(a))}</span>
                      <div className="text-xs text-ink-faint">
                        {lo}–{hi}
                      </div>
                    </td>
                    <td className="py-1.5 text-right font-mono text-ink">{a.n_needs_review.toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs leading-relaxed text-ink-faint">
            Expected counts from uncalibrated probabilities, for the ground assessed only: not a county or event
            total. Ranges are per area and do not add.
          </p>
        </>
      )}
      <div className="mt-5">
        <AccuracyNote />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// inspector: one area
// --------------------------------------------------------------------------- //
function AreaInspector({
  fc,
  areaId,
  reload,
  tab,
  onTab,
  queue,
  labels,
  sel,
  address,
  note,
  onNote,
  onLabel,
  onSelect,
  onFocus,
  rerunning,
  onRerun,
  onDeleted,
}: {
  fc: OpsCollection;
  areaId: string;
  reload: number;
  onFocus: (ll: [number, number]) => void;
  tab: Tab;
  onTab: (t: Tab) => void;
  queue: OpsProps[];
  labels: Record<string, string>;
  sel: OpsFeature | null;
  address?: string;
  note: string;
  onNote: (v: string) => void;
  onLabel: (lab: string) => void;
  onSelect: (id: string | null) => void;
  rerunning: boolean;
  onRerun: () => void;
  onDeleted: () => void;
}) {
  const p = fc.properties;
  const [exporting, setExporting] = useState(false);
  const [hasChecks, setHasChecks] = useState<boolean | null>(null);
  useEffect(() => {
    loadReferences(areaId)
      .then((d) => setHasChecks(d.references.length > 0))
      .catch(() => setHasChecks(false));
  }, [areaId, reload]);
  const brief = () => openBrief(areaId).catch((e: Error) => toast.error(e.message));
  const off = useOffline();
  const noRerun = off?.offline ? offlineReason(off, /assess/i) : null;
  const exportGis = async () => {
    setExporting(true);
    try {
      await downloadExport(areaId);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(false);
    }
  };
  return (
    <div className="flex flex-col md:min-h-0 md:flex-1">
      <header className="shrink-0 px-4 pt-3">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <h1 className="title-display truncate text-[24px]">{areaTitle(areaId, p.aoi.name)}</h1>
            <div className="truncate text-xs text-ink-dim" title={p.event.name}>
              {p.event.name} · {p.event.declarations.join(", ") || "provisional event"}
              {p.aoi.county ? ` · ${p.aoi.county} County` : ""}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-faint">
              <span className="tnum font-mono" title={`assessed ${ago(p.generated_utc)}`}>
                as of {fmtStamp(p.generated_utc)}
              </span>
              {p.aoi.role !== "OPS" && <Tag title={ROLE_TITLE[p.aoi.role]}>{p.aoi.role}</Tag>}
              {hazardsOf(p).map((h) => (
                <Tag key={h}>{HAZARD_LABEL[h] ?? h}</Tag>
              ))}
            </div>
          </div>
          <Popover
            label="More actions"
            trigger={({ open, toggle, id }) => (
              <button
                onClick={toggle}
                aria-expanded={open}
                aria-controls={id}
                aria-label="More actions"
                className={btnClass("ghost", "sm", "w-7 px-0")}
              >
                <Icon name="more" />
              </button>
            )}
          >
            {(close) => (
              <div className="-m-1.5 flex flex-col text-[13px]">
                <a className="rounded px-2.5 py-1.5 text-ink hover:bg-surface-2" href={publicUrl(areaId)} download onClick={close}>
                  Download public summary
                  <div className="text-xs text-ink-faint">Counts only, no addresses: safe to share</div>
                </a>
                <button
                  className="rounded px-2.5 py-1.5 text-left text-ink hover:bg-surface-2"
                  onClick={() => {
                    close();
                    const t = toast.loading("Building the damage assessment packet…");
                    downloadIda(areaId)
                      .then(() => toast.success("Packet downloaded", { id: t }))
                      .catch((e: Error) => toast.error(e.message, { id: t }));
                  }}
                >
                  FEMA damage assessment packet
                  <div className="text-xs text-ink-faint">Excel, GeoPackage and PDA narrative for the state. Has addresses</div>
                </button>
                {p.aoi.role === "OPS" && (
                  <button
                    className="rounded px-2.5 py-1.5 text-left text-ink hover:bg-surface-2 disabled:opacity-45"
                    disabled={rerunning || !!noRerun}
                    onClick={() => {
                      close();
                      onRerun();
                    }}
                  >
                    {rerunning ? "Running again…" : "Run again"}
                    <div className="text-xs text-ink-faint">
                      {noRerun ?? "Same imagery, after a calibration or update. Labels kept."}
                    </div>
                  </button>
                )}
                {p.aoi.role === "OPS" && (
                  <button
                    className="rounded px-2.5 py-1.5 text-left text-st-bad hover:bg-st-bad/10 disabled:opacity-45"
                    disabled={rerunning}
                    onClick={async () => {
                      close();
                      if (!window.confirm(`Delete the assessment "${areaTitle(areaId, p.aoi.name)}"? Labels are kept.`)) return;
                      try {
                        await deleteArea(areaId);
                        toast.success("Assessment deleted");
                        onDeleted();
                      } catch (e) {
                        toast.error((e as Error).message);
                      }
                    }}
                  >
                    Delete assessment
                  </button>
                )}
              </div>
            )}
          </Popover>
        </div>
        <div className="mt-3 flex gap-2">
          <Button variant="primary" size="sm" icon={<Icon name="file" className="h-3.5 w-3.5" />} onClick={brief}>
            Situation brief
          </Button>
          <Button
            size="sm"
            icon={<Icon name="download" className="h-3.5 w-3.5" />}
            busy={exporting}
            disabled={exporting}
            onClick={exportGis}
            title="GeoJSON, CSV with USNG, KML, GeoPackage, File Geodatabase, Survey123 sheet"
          >
            GIS export
          </Button>
        </div>
        <Tabs
          className="mt-3 -mx-4 px-2"
          label="Area details"
          value={tab}
          onChange={onTab}
          items={[
            { id: "overview", label: "Overview" },
            { id: "review", label: "Review", count: queue.length },
            { id: "respond", label: "Respond" },
            { id: "people", label: "People" },
            { id: "checks", label: "Checks", hidden: hasChecks === false },
          ]}
        />
      </header>
      <div className="px-4 pb-6 md:min-h-0 md:flex-1 md:overflow-y-auto" role="tabpanel">
        {tab === "overview" && (
          <AreaOverview fc={fc} queue={queue} onReview={() => onTab("review")} onBrief={brief} onExport={exportGis} />
        )}
        {tab === "review" &&
          (sel ? (
            <StructureCard
              areaId={areaId}
              f={sel}
              address={address}
              labeled={labels[sel.properties.ncr_id]}
              note={note}
              onNote={onNote}
              onLabel={onLabel}
              onClose={() => onSelect(null)}
              position={queue.findIndex((q) => q.ncr_id === sel.properties.ncr_id)}
              total={queue.length}
            />
          ) : (
            <ReviewList queue={queue} labeledCount={Object.keys(labels).length} onPick={onSelect} />
          ))}
        {tab === "respond" && <Respond key={`respond-${reload}`} areaId={areaId} onFocus={onFocus} />}
        {tab === "people" && <ImpactPanel key={`people-${reload}`} areaId={areaId} />}
        {tab === "checks" && (
          <>
            <References key={`refs-${reload}`} areaId={areaId} />
            <div className="mt-2">
              <FemaPanel key={`fema-${reload}`} areaId={areaId} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function AreaOverview({
  fc,
  queue,
  onReview,
  onBrief,
  onExport,
}: {
  fc: OpsCollection;
  queue: OpsProps[];
  onReview: () => void;
  onBrief: () => void;
  onExport: () => void;
}) {
  const p = fc.properties;
  const reasons = p.pair_context.reasons ?? [];
  const sev = sevOf(p);
  const [lo, hi] = sevRange(p);
  const max = Math.max(1, ...FEMA.map((c) => p.expected_counts[c] ?? 0));
  return (
    <div className="pt-4">
      <div className="grid grid-cols-2 gap-4">
        <Figure big label="Expected at Major or Destroyed" value={`~${n0(sev)}`} range={`${lo}–${hi}`} />
        <Figure big label="Structures read" value={n0(p.n_structures)} />
      </div>

      <table className="tnum mt-4 w-full text-[13px]">
        <caption className="sr-only">Expected structures by damage level</caption>
        <thead>
          <tr className="text-xs text-ink-faint">
            <th className="pb-1 text-left font-medium">Level</th>
            <th className="pb-1 text-right font-medium" title="Sum of each structure's probability for the level">
              Expected (sum of probabilities)
            </th>
            <th className="pb-1 text-right font-medium">80% range*</th>
          </tr>
        </thead>
        <tbody>
          {FEMA.map((c) => (
            <tr key={c} className="border-t border-line">
              <td className="py-1.5 pr-3">
                <div className="flex items-center gap-2 text-ink">
                  <Swatch c={c} />
                  {FEMA_LABEL[c]}
                </div>
                <div className="bar-track mt-1 h-1">
                  <div className="bar-fill" style={{ width: `${((p.expected_counts[c] ?? 0) / max) * 100}%`, background: FEMA_HEX[c] }} />
                </div>
              </td>
              <td className="py-1.5 text-right font-mono font-semibold text-ink">{Math.round(p.expected_counts[c])}</td>
              <td className="py-1.5 text-right font-mono text-ink-faint">{p.expected_counts_80pct?.[c]?.join("–") ?? "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs leading-relaxed text-ink-faint">
        * From uncalibrated probabilities; real uncertainty is wider. {n0(p.not_assessed.total)} inventory structures
        had no outline and were not read ({n0(p.not_assessed.residential)} residential).
      </p>

      <div className="label mt-5">Next steps</div>
      <ol className="mt-2 divide-y divide-line rounded border border-line">
        <NextStep
          n={1}
          done={queue.length === 0}
          title={queue.length ? `Check ${queue.length.toLocaleString()} uncertain calls` : "Every uncertain call is checked"}
          detail="Severe and low-confidence calls, the most occupied first"
          onClick={onReview}
          action="Review"
        />
        <NextStep n={2} title="Send the situation brief" detail="One page for the EOC and partners" onClick={onBrief} action="Open" />
        <NextStep n={3} title="Load it into GIS" detail="GeoPackage, File Geodatabase, KML, CSV with USNG" onClick={onExport} action="Export" />
      </ol>

      {(p.warnings.length > 0 || reasons.length > 0) && (
        <div className="mt-4">
          <Disclosure title="Data caveats" meta={p.warnings.length + reasons.length}>
            <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-dim">
              {p.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
              {reasons.map((r) => (
                <li key={r} className="tnum">
                  {r.replace(/_/g, " ").toLowerCase()}
                </li>
              ))}
            </ul>
          </Disclosure>
        </div>
      )}
    </div>
  );
}

function NextStep({
  n,
  title,
  detail,
  onClick,
  action,
  done,
}: {
  n: number;
  title: string;
  detail: string;
  onClick: () => void;
  action: string;
  done?: boolean;
}) {
  return (
    <li className="flex items-center gap-3 p-2.5">
      <span
        className={`grid h-6 w-6 shrink-0 place-items-center rounded-full font-mono text-xs ${
          done ? "bg-st-ok/15 text-st-ok" : "border border-line-strong text-ink-dim"
        }`}
      >
        {done ? <Icon name="check" className="h-3.5 w-3.5" /> : n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-semibold text-ink">{title}</div>
        <div className="text-xs text-ink-faint">{detail}</div>
      </div>
      {!done && (
        <Button size="sm" onClick={onClick}>
          {action}
        </Button>
      )}
    </li>
  );
}

function ImpactPanel({ areaId }: { areaId: string }) {
  const [imp, setImp] = useState<Impact | null | "none">(null);
  useEffect(() => {
    loadImpact(areaId)
      .then(setImp)
      .catch(() => setImp("none"));
  }, [areaId]);
  if (imp === null)
    return (
      <div className="space-y-2 pt-4">
        <div className="skel h-12" />
        <div className="skel h-24" />
      </div>
    );
  if (imp === "none")
    return (
      <div className="pt-4">
        <Empty icon="users" title="No people estimate for this area">
          It is written after the assessment; it may still be running, or a source was unavailable.
        </Empty>
      </div>
    );
  const unadjusted = imp.occupancy_adjustment.startsWith("UNADJUSTED");
  const maxNeed = Math.max(1, ...imp.tracts.map((t) => t.need_index ?? 0));
  return (
    <div className="pt-4">
      <div className="grid grid-cols-2 gap-4">
        <Figure
          big
          label="Likely displaced"
          value={`~${Math.round(imp.expected_displaced.median)}`}
          range={`${Math.round(imp.expected_displaced.p10)}–${Math.round(imp.expected_displaced.p90)}`}
        />
        <Figure
          big
          label="Homes not read"
          value={n0(imp.unassessed_residential?.structures ?? 0)}
          unit={`~${n0(imp.unassessed_residential?.occupants_nsi ?? 0)} residents`}
        />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-ink-dim">
        {unadjusted
          ? "Seasonal and vacant homes counted as occupied (pushes this up); homes not read are excluded (pushes it down). "
          : `${imp.occupancy_adjustment}. `}
        Ranks where to look; not an eligibility determination.
      </p>
      <table className="tnum mt-4 w-full text-[13px]">
        <caption className="label pb-2 text-left">By census tract, highest need first</caption>
        <thead>
          <tr className="text-xs text-ink-faint">
            <th className="pb-1 text-left font-medium">Tract</th>
            <th className="pb-1 text-right font-medium">Displaced</th>
            <th className="pb-1 text-right font-medium" title="CDC social vulnerability percentile">
              SVI
            </th>
            <th className="w-24 pb-1 text-right font-medium">Need</th>
          </tr>
        </thead>
        <tbody>
          {[...imp.tracts]
            .sort((a, b) => (b.need_index ?? -1) - (a.need_index ?? -1))
            .slice(0, 8)
            .map((t) => (
              <tr key={t.tract} className="border-t border-line">
                <td className="py-1.5 text-ink" title={t.location ?? ""}>
                  {(t.location ?? t.tract).split(";")[0].replace("Census Tract ", "")}
                </td>
                <td className="py-1.5 text-right font-mono text-ink">{t.expected_displaced ?? "<5 bldgs"}</td>
                <td className="py-1.5 text-right font-mono text-ink-dim">{t.svi_percentile?.toFixed(2) ?? "n/a"}</td>
                <td className="py-1.5 pl-2">
                  <div className="flex items-center justify-end gap-1.5">
                    <div className="bar-track h-1.5 w-12">
                      <div className="bar-fill bg-meter" style={{ width: `${((t.need_index ?? 0) / maxNeed) * 100}%` }} />
                    </div>
                    <span className="w-9 text-right font-mono font-semibold text-ink">{t.need_index ?? "n/a"}</span>
                  </div>
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

const REVIEW_PAGE = 150;

/** What FEMA has approved in the ZIP codes this area touches, beside what the
 * assessment expects there. Folded by default: it is context for a later
 * stage of an event, and it is easy to over-read. */
function FemaPanel({ areaId }: { areaId: string }) {
  const [ref, setRef] = useState<FemaReference | null | "none">(null);
  const [open, setOpen] = useState(false);
  // OpenFEMA is a network source: offline it is never asked for
  const off = useOffline();
  const noFema = off?.offline ? offlineReason(off, /FEMA/) : null;
  useEffect(() => {
    if (!open || ref !== null || noFema) return;
    let live = true;
    loadFemaReference(areaId)
      .then((d) => live && setRef(d))
      .catch(() => live && setRef("none"));
    return () => {
      live = false;
    };
  }, [open, ref, areaId, noFema]);
  return (
    <Disclosure title="FEMA assistance by ZIP code" onToggle={setOpen}>
      {noFema && <p className="text-[13px] text-ink-dim">{noFema}</p>}
      {ref === null && !noFema && <div className="skel h-16" />}
      {ref === "none" && (
        <p className="text-[13px] text-ink-dim">Not available (needs responder access, or OpenFEMA is unreachable).</p>
      )}
      {ref && ref !== "none" && (
        <>
          {ref.status === "NO_DECLARATION" ? (
            <p className="text-[13px] text-ink-dim">
              No federal declaration for this event yet, so FEMA has published no assistance data.
            </p>
          ) : ref.zips.length === 0 ? (
            <p className="text-[13px] text-ink-dim">
              No structure in this area has an address, so none could be placed in a ZIP code.
            </p>
          ) : (
            <table className="tnum w-full text-[13px]">
              <caption className="sr-only">
                Homes this assessment expects at Major or Destroyed, and FEMA owner approvals, by ZIP code
              </caption>
              <thead>
                <tr className="text-xs text-ink-faint">
                  <th className="text-left font-medium">ZIP</th>
                  <th className="text-right font-medium" title="Homes assessed in this area with that ZIP, and how many are expected at Major or Destroyed">
                    This area
                  </th>
                  <th className="text-right font-medium" title="Owner households FEMA approved in the whole ZIP code">
                    FEMA approved
                  </th>
                  <th className="text-right font-medium" title="Owner approvals over $25,000, and maximum grants">
                    Over $25k
                  </th>
                </tr>
              </thead>
              <tbody>
                {ref.zips.map((z) => (
                  <tr key={z.zip} className="border-t border-line align-top">
                    <td className="py-1.5 font-mono text-ink">{z.zip}</td>
                    <td className="py-1.5 text-right font-mono text-ink">
                      ~{n0(z.expected_major_plus)} ≥ Major
                      <div className="text-xs text-ink-faint">of {n0(z.homes_assessed)} homes</div>
                    </td>
                    <td className="py-1.5 text-right font-mono text-ink">
                      {z.fema?.owners ? n0(z.fema.owners.approved) : "n/a"}
                      {z.fema?.owners && (
                        <div className="text-xs text-ink-faint">of {n0(z.fema.owners.registrations)} owners</div>
                      )}
                    </td>
                    <td className="py-1.5 text-right font-mono text-ink">
                      {z.fema?.owners ? n0(z.fema.owners.approved_over_25k) : "n/a"}
                      {z.fema?.owners && (
                        <div className="text-xs text-ink-faint">{n0(z.fema.owners.max_grants)} max grants</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-2 text-xs leading-relaxed text-ink-faint">
            {ref.caveat}
            {ref.unplaced_structures > 0 &&
              ` ${ref.unplaced_structures.toLocaleString()} structures here have no address and are not in the ZIP rows.`}{" "}
            Source: {ref.source.name}.
          </p>
          {ref.warnings.map((w) => (
            <p key={w} className="mt-1 text-xs text-st-bad">
              {w}
            </p>
          ))}
        </>
      )}
    </Disclosure>
  );
}

function ReviewList({
  queue,
  labeledCount,
  onPick,
}: {
  queue: OpsProps[];
  labeledCount: number;
  onPick: (id: string) => void;
}) {
  const [limit, setLimit] = useState(REVIEW_PAGE);
  const off = useOffline();
  const note = off?.offline && off.labels ? (
    <p className="mb-3 rounded border border-st-warn/40 bg-st-warn/10 px-2.5 py-2 text-xs leading-relaxed text-ink">{off.labels}</p>
  ) : null;
  if (queue.length === 0)
    return (
      <div className="pt-4">
        {note}
        <Empty icon="check" title="Nothing waiting for review">
          {labeledCount > 0 ? `${labeledCount} calls checked in this area.` : "No call here was flagged for review."}
        </Empty>
      </div>
    );
  return (
    <div className="pt-3">
      {note}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-dim">
        <span>
          <b className="tnum font-mono text-ink">{queue.length.toLocaleString()}</b> open · {labeledCount} checked · most
          severe and most occupied first
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-ink-faint">
        <span className="inline-flex items-center gap-1">
          <Kbd>0</Kbd>–<Kbd>4</Kbd> level
        </span>
        <span className="inline-flex items-center gap-1">
          <Kbd>x</Kbd> can’t tell
        </span>
        <span className="inline-flex items-center gap-1">
          <Kbd>j</Kbd>
          <Kbd>k</Kbd> next, previous
        </span>
        <span className="inline-flex items-center gap-1">
          hold <Kbd>B</Kbd> before image
        </span>
      </div>
      <ul className="mt-2 divide-y divide-line border-y border-line">
        {queue.slice(0, limit).map((p, i) => (
          // index in the key: assessments made before multi-part buildings got
          // their own ids can hold the same ncr_id twice
          <li key={`${p.ncr_id}-${i}`}>
            <button
              onClick={() => onPick(p.ncr_id)}
              className="flex w-full items-center gap-2.5 px-1 py-2 text-left hover:bg-surface-2"
            >
              <Swatch c={p.damage_level ?? "none"} />
              <span className="w-16 shrink-0 truncate text-[12px] text-ink">
                {p.damage_level ? FEMA_LABEL[p.damage_level] : "Not read"}
              </span>
              <span className="tnum flex-1 truncate font-mono text-[12px] text-ink-dim">{p.usng_10m}</span>
              <span className="tnum font-mono text-xs text-ink-dim">
                {(pSevere(p) * 100).toFixed(0)}% ≥Maj
              </span>
              <span className="tnum w-14 text-right font-mono text-xs text-ink-faint">{occupantsOf(p)} ppl</span>
            </button>
          </li>
        ))}
      </ul>
      {queue.length > limit && (
        <Button size="sm" className="mt-2" onClick={() => setLimit((n) => n + REVIEW_PAGE)}>
          Show {Math.min(REVIEW_PAGE, queue.length - limit)} more ({limit} of {queue.length.toLocaleString()})
        </Button>
      )}
    </div>
  );
}

function Chip({ areaId, ncrId, kind }: { areaId: string; ncrId: string; kind: "pre" | "post" }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    let live = true;
    loadChip(areaId, ncrId, kind)
      .then((u) => {
        url = u;
        if (live) setSrc(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [areaId, ncrId, kind]);
  return (
    <figure className="relative">
      {src ? (
        <img
          src={src}
          alt={`${kind === "pre" ? "Before" : "After"}-event image of this structure`}
          className="aspect-square w-full rounded bg-surface-2 object-cover"
        />
      ) : (
        <div className="grid aspect-square w-full place-items-center rounded bg-surface-2 text-xs text-ink-faint">
          {failed ? "needs responder access" : <Spinner />}
        </div>
      )}
      <figcaption className="absolute left-1.5 top-1.5 rounded-sm bg-ink/75 px-1.5 py-0.5 text-xs font-semibold text-canvas">
        {kind === "pre" ? "Before" : "After"}
      </figcaption>
    </figure>
  );
}

function ProbBar({ probs }: { probs: Record<FemaClass, number> }) {
  return (
    <div>
      <div
        className="flex h-3 w-full overflow-hidden rounded-sm bg-surface-2"
        role="img"
        aria-label={FEMA.map((c) => `${FEMA_LABEL[c]} ${(probs[c] * 100).toFixed(0)}%`).join(", ")}
      >
        {FEMA.map((c) => (
          <div key={c} style={{ width: `${probs[c] * 100}%`, background: FEMA_HEX[c], boxShadow: "1px 0 0 rgb(var(--surface))" }} />
        ))}
      </div>
      <div className="tnum mt-1 grid grid-cols-5 text-center font-mono text-xs text-ink-dim">
        {FEMA.map((c) => (
          <span key={c} className={probs[c] >= 0.2 ? "text-ink" : ""}>
            {(probs[c] * 100).toFixed(0)}%
          </span>
        ))}
      </div>
    </div>
  );
}

function StructureCard({
  areaId,
  f,
  address,
  labeled,
  note,
  onNote,
  onLabel,
  onClose,
  position,
  total,
}: {
  areaId: string;
  f: OpsFeature;
  address?: string;
  labeled?: string;
  note: string;
  onNote: (v: string) => void;
  onLabel: (lab: string) => void;
  onClose: () => void;
  position: number;
  total: number;
}) {
  const p = f.properties;
  const assessed = !!p.damage_level;
  const offline = !!useOffline()?.offline;
  return (
    <div className="pt-3">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="ghost" icon={<Icon name="arrowLeft" className="h-3.5 w-3.5" />} onClick={onClose} kbd="Esc">
          Queue
        </Button>
        {position >= 0 && (
          <span className="tnum ml-auto font-mono text-xs text-ink-faint">
            {position + 1} of {total.toLocaleString()}
          </span>
        )}
      </div>

      <div className="mt-2">
        <div className="tnum font-mono text-[15px] font-semibold text-ink" title="US National Grid, 10 m: the precision of an outline centroid">
          {p.usng_10m}
        </div>
        {address ? (
          <div className="text-[13px] text-ink">{address}</div>
        ) : (
          offline && <div className="text-xs text-ink-faint">Addresses are not in this offline pack.</div>
        )}
        <div className="tnum font-mono text-xs text-ink-faint">
          {p.centroid[1].toFixed(5)}, {p.centroid[0].toFixed(5)}
        </div>
      </div>

      {assessed && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {(["pre", "post"] as const).map((k) => (
            <Chip key={`${p.ncr_id}-${k}`} areaId={areaId} ncrId={p.ncr_id} kind={k} />
          ))}
        </div>
      )}

      {assessed && p.damage_probs ? (
        <div className="mt-3">
          <div className="flex items-baseline justify-between">
            <span className="inline-flex items-center gap-2 text-base font-semibold text-ink">
              <Swatch c={p.damage_level!} className="h-3 w-3" />
              {FEMA_LABEL[p.damage_level!]}
            </span>
            <span className="tnum font-mono text-xs text-ink-dim">{(p.confidence! * 100).toFixed(0)}% · uncalibrated</span>
          </div>
          <div className="mt-2">
            <ProbBar probs={p.damage_probs} />
          </div>
          {p.needs_review && (
            <p className="mt-2 flex gap-2 rounded border border-review/40 bg-review/10 px-2.5 py-1.5 text-xs text-ink">
              <Icon name="eye" className="mt-px h-3.5 w-3.5 text-review" />
              <span>
                <b>Why it needs a person:</b> {p.review_reasons.map((r) => r.replace(/_/g, " ").toLowerCase()).join("; ")}
              </span>
            </p>
          )}
        </div>
      ) : (
        <p className="mt-3 text-[13px] text-ink">
          <b>Not assessed.</b> In the structure inventory, but no building outline exists, so imagery was not read.
        </p>
      )}

      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <span className="text-[13px] font-semibold text-ink">What does the imagery show?</span>
          {labeled && <Tag tone="accent">recorded: {labeled.replace("_", " ")}</Tag>}
        </div>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {FEMA.map((c, i) => (
            <button
              key={c}
              onClick={() => onLabel(c)}
              aria-pressed={labeled === c}
              className={`pressable flex h-9 items-center gap-1.5 rounded border px-2 text-[13px] ${
                labeled === c ? "border-ink bg-surface-2 font-semibold text-ink" : "border-line-strong text-ink hover:bg-surface-2"
              }`}
            >
              <Swatch c={c} />
              <span className="flex-1 truncate text-left">{FEMA_LABEL[c]}</span>
              <span className="font-mono text-xs text-ink-faint">{i}</span>
            </button>
          ))}
          <button
            onClick={() => onLabel("cannot_tell")}
            aria-pressed={labeled === "cannot_tell"}
            className={`pressable flex h-9 items-center gap-1.5 rounded border px-2 text-[13px] ${
              labeled === "cannot_tell" ? "border-ink bg-surface-2 font-semibold text-ink" : "border-line-strong text-ink hover:bg-surface-2"
            }`}
          >
            <span className="flex-1 truncate text-left">Can’t tell</span>
            <span className="font-mono text-xs text-ink-faint">x</span>
          </button>
        </div>
        <label className="mt-2 block">
          <span className="text-xs text-ink-dim">Note saved with the label (optional)</span>
          <input
            className="field mt-1"
            value={note}
            maxLength={300}
            placeholder="e.g. roof under trees, tarp on north side"
            onChange={(e) => onNote(e.target.value)}
          />
        </label>
      </div>

      <div className="mt-4">
        <Disclosure title="Evidence" meta={`${p.evidence.filter((e) => e.available).length} of ${p.evidence.length} used`}>
          <ul className="space-y-1.5 text-xs">
            {p.evidence.map((e) => (
              <li key={e.id} className="flex gap-2">
                <b className="tnum w-6 shrink-0 font-mono text-ink">{e.id}</b>
                {e.available ? (
                  <span className="text-ink-dim">
                    weight {e.weight.toFixed(2)} · {e.status}
                    {e.reasons.length > 0 && (
                      <>
                        {" "}
                        · <span className="tnum font-mono">{e.reasons.join(", ")}</span>
                      </>
                    )}
                  </span>
                ) : (
                  <span className="text-ink-faint">unavailable: {e.unavailable_reason?.replace(/_/g, " ").toLowerCase()}</span>
                )}
              </li>
            ))}
          </ul>
        </Disclosure>
        <Disclosure title="Structure and occupants">
          <dl className="tnum grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-ink-dim">Use</dt>
            <dd className="text-ink">{p.primary_occupancy ?? p.occupancy ?? "unknown"}</dd>
            <dt className="text-ink-dim">Manufactured home</dt>
            <dd className="text-ink">{p.flags.manufactured_home ? "yes" : "no"}</dd>
            <dt className="text-ink-dim">Occupants (NSI {p.occupants?.period ?? ""})</dt>
            <dd className="font-mono text-ink">{p.occupants?.nsi_estimate ?? "n/a"}</dd>
            <dt className="text-ink-dim">Occupants (USA Structures)</dt>
            <dd className="font-mono text-ink">
              {p.occupants?.usa_structures_median ?? "n/a"}
              {p.occupants?.usa_structures_ci95?.[0] != null &&
                ` (${p.occupants.usa_structures_ci95[0]}–${p.occupants.usa_structures_ci95[1]})`}
            </dd>
            <dt className="text-ink-dim">Stories</dt>
            <dd className="font-mono text-ink">{p.stories ?? "n/a"}</dd>
            <dt className="text-ink-dim">Foundation height</dt>
            <dd className="font-mono text-ink">{p.foundation_height_ft != null ? `${p.foundation_height_ft} ft` : "n/a"}</dd>
            <dt className="text-ink-dim">Ground (NAVD88)</dt>
            <dd className="font-mono text-ink">
              {p.ground_elev_m_navd88 != null ? `${p.ground_elev_m_navd88.toFixed(1)} m` : "n/a"}
            </dd>
            <dt className="text-ink-dim">Flood zone</dt>
            <dd className="text-ink">{p.flood_zone ?? "n/a"}</dd>
            <dt className="text-ink-dim">Outline source</dt>
            <dd className="text-ink">
              {p.footprint_source ?? "none"}
              {p.footprint_image_date ? ` (${p.footprint_image_date})` : ""}
            </dd>
          </dl>
        </Disclosure>
        {assessed && !offline && (
          <Disclosure title="Owner record" meta="private link">
            <OwnerLink areaId={areaId} ncrId={p.ncr_id} />
          </Disclosure>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// map controls
// --------------------------------------------------------------------------- //
/** Puts the assessment's own before / after image under the structures, with
 * the capture date, so a call is checked against the evidence it was made on. */
function ImageryBar({
  mode,
  onMode,
  records,
  peek,
  view3d,
  onView3d,
  terrain,
  onTerrain,
}: {
  mode: ImageryMode;
  onMode: (m: ImageryMode) => void;
  records: ImageryRecord[];
  peek: boolean;
  view3d: boolean;
  onView3d: (v: boolean) => void;
  terrain: boolean;
  onTerrain: (v: boolean) => void;
}) {
  const rec = records.find((r) => r.role === (peek ? "pre" : mode === "swipe" ? "post" : mode));
  // terrain tiles come from a public host: never asked for offline
  const off = useOffline();
  const noTerrain = off?.offline ? "Terrain needs a network connection; buildings stay on flat ground offline." : null;
  return (
    <div className="panel flex flex-wrap items-center gap-2 p-1.5 pr-2.5">
      <Segmented
        size="sm"
        label="Imagery under the structures"
        value={mode}
        onChange={onMode}
        items={[
          { id: "post", label: "After", title: "After-event image under the structures" },
          { id: "pre", label: "Before", title: "Before-event image under the structures" },
          ...(view3d ? [] : [{ id: "swipe" as const, label: "Swipe", title: "Drag a divider between the before and after images" }]),
          { id: "off", label: "Map", title: "No imagery, base map only" },
        ]}
      />
      {mode !== "off" && (
        <span className="tnum font-mono text-xs text-ink-dim" title={rec?.source?.replace(/_/g, " ")}>
          {imageryDate(rec)}
        </span>
      )}
      {(mode === "post" || mode === "pre") && !view3d && (
        <span className="hidden items-center gap-1 text-xs text-ink-faint lg:inline-flex">
          hold <Kbd>B</Kbd> to compare
        </span>
      )}
      <span className="mx-0.5 h-5 w-px bg-line" aria-hidden />
      <Segmented
        size="sm"
        label="Map view"
        value={view3d ? "3d" : "2d"}
        onChange={(v) => onView3d(v === "3d")}
        items={[
          { id: "2d", label: "2D", title: "Flat map (default)" },
          { id: "3d", label: "3D", title: "Buildings at inventory height; drag with the right button or Ctrl to tilt and turn" },
        ]}
      />
      {view3d && (
        <label
          className={`inline-flex items-center gap-1.5 text-xs text-ink-dim ${noTerrain ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
          title={noTerrain ?? "Lay the buildings on the ground's relief (AWS Terrain Tiles)"}
        >
          <input
            type="checkbox"
            checked={terrain && !noTerrain}
            disabled={!!noTerrain}
            onChange={(e) => onTerrain(e.target.checked)}
            className="accent-[rgb(var(--accent))]"
          />
          Terrain
        </label>
      )}
    </div>
  );
}

/** The legend is also the filter: click a level to hide or show it. */
function LegendFilter({
  fc,
  labels,
  view3d,
  hidden,
  onToggle,
  reviewOnly,
  onReviewOnly,
}: {
  fc: OpsCollection;
  labels: Record<string, string>;
  view3d: boolean;
  hidden: Set<LevelKey>;
  onToggle: (k: LevelKey) => void;
  reviewOnly: boolean;
  onReviewOnly: (v: boolean) => void;
}) {
  const [open, setOpen] = useState(() => window.matchMedia?.("(min-width: 768px)").matches ?? true);
  const counts = useMemo(() => {
    const c: Record<LevelKey, number> = { no_damage: 0, affected: 0, minor: 0, major: 0, destroyed: 0, none: 0 };
    let review = 0;
    let known = 0;
    for (const f of fc.features) {
      c[f.properties.damage_level ?? "none"]++;
      if (isOpen(f.properties, labels)) review++;
      if (heightOf(f as OpsFeature) != null) known++;
    }
    return { c, review, known, unknown: fc.features.length - known };
  }, [fc, labels]);
  if (!open)
    return (
      <button className={btnClass("secondary", "sm", "shadow-1")} onClick={() => setOpen(true)} aria-expanded={false}>
        <Icon name="layers" className="h-3.5 w-3.5" /> Legend
      </button>
    );
  const row = (k: LevelKey, label: string) => (
    <button
      key={k}
      onClick={() => onToggle(k)}
      aria-pressed={!hidden.has(k)}
      title={hidden.has(k) ? `Show ${label}` : `Hide ${label}`}
      className={`flex w-full items-center gap-2 rounded px-1.5 py-1 text-[13px] hover:bg-surface-2 ${hidden.has(k) ? "opacity-40" : ""}`}
    >
      <Swatch c={k} />
      <span className={`flex-1 text-left text-ink ${hidden.has(k) ? "line-through" : ""}`}>{label}</span>
      <span className="tnum font-mono text-[11px] text-ink-faint">{counts.c[k].toLocaleString()}</span>
    </button>
  );
  return (
    <div className="panel w-56 p-1.5">
      <div className="flex items-center justify-between px-1.5 pb-1 pt-0.5">
        <span className="label">Most likely level</span>
        <button className="text-ink-faint hover:text-ink" onClick={() => setOpen(false)} aria-label="Fold the legend">
          <Icon name="x" className="h-3.5 w-3.5" />
        </button>
      </div>
      {FEMA.map((c) => row(c, FEMA_LABEL[c]))}
      {counts.c.none > 0 && row("none", "Not assessed")}
      <div className="my-1 border-t border-line" />
      <button
        onClick={() => onReviewOnly(!reviewOnly)}
        aria-pressed={reviewOnly}
        className={`flex w-full items-center gap-2 rounded px-1.5 py-1 text-[13px] ${reviewOnly ? "bg-review/10" : "hover:bg-surface-2"}`}
      >
        <span className="h-2.5 w-2.5 shrink-0 rounded-[2px] border-2 border-review" />
        <span className="flex-1 text-left text-ink">Needs review only</span>
        <span className="tnum font-mono text-[11px] text-ink-faint">{counts.review.toLocaleString()}</span>
      </button>
      {view3d && (
        <>
          <div className="my-1 border-t border-line" />
          <div className="flex items-center gap-2 px-1.5 py-1 text-[13px] text-ink">
            <span className="h-3 w-2.5 shrink-0 rounded-[1px] bg-ink-dim" aria-hidden />
            <span className="flex-1">Inventory height</span>
            <span className="tnum font-mono text-[11px] text-ink-faint">{counts.known.toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-2 px-1.5 py-1 text-[13px] text-ink">
            <span className="h-2.5 w-2.5 shrink-0 rounded-[1px] border border-dashed border-ink-dim" aria-hidden />
            <span className="flex-1">Height unknown</span>
            <span className="tnum font-mono text-[11px] text-ink-faint">{counts.unknown.toLocaleString()}</span>
          </div>
          <p className="px-1.5 pb-0.5 text-[11px] leading-snug text-ink-faint">
            Height is stories × 3 m from the USACE inventory. Unknown heights are drawn flat and dashed, never guessed.
          </p>
        </>
      )}
      <p className="px-1.5 pt-1 text-[11px] leading-snug text-ink-faint">Faint fill: low confidence. Click a level to hide it.</p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// map
// --------------------------------------------------------------------------- //
function OpsMap({
  fc,
  areaId,
  imagery,
  areas,
  onOpenArea,
  selected,
  reviewOnly,
  hidden,
  labels,
  onSelect,
  picking,
  preview,
  onPick,
  beforeLabel,
  afterLabel,
  resp,
  focus,
  fitEvent,
  view3d,
  terrain,
}: {
  view3d: boolean;
  terrain: boolean;
  /** the event whose areas the overview frames */
  fitEvent: string | null;
  resp: ResponseLayers | null;
  focus: { ll: [number, number]; n: number } | null;
  fc: OpsCollection | null;
  areaId: string | null;
  imagery: ImageryMode;
  beforeLabel: string;
  afterLabel: string;
  /** assessed areas to mark on the overview (null inside an area) */
  areas: OpsAreaSummary[] | null;
  onOpenArea: (id: string) => void;
  selected: string | null;
  reviewOnly: boolean;
  hidden: Set<LevelKey>;
  labels: Record<string, string>;
  onSelect: (id: string | null) => void;
  picking: boolean;
  /** the square a new assessment would cover, while the form is open */
  preview: Preview | null;
  onPick: (ll: [number, number] | null) => void;
}) {
  const { containerRef, mapRef, ready, styleEpoch } = useMapLibre({
    center: NC_CENTER,
    zoom: 6.6,
    pitch: 0,
  });
  const { effective } = useTheme();
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; p: OpsProps } | null>(null);
  const [hoverR, setHoverR] = useState<{ x: number; y: number; title: string; sub: string } | null>(null);

  // the Respond panel asks the map to look at a place
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !focus) return;
    map.easeTo({ center: focus.ll, zoom: Math.max(map.getZoom(), 16), duration: 450 });
  }, [focus, ready, mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !fc) return;
    if (!fc.features.length) {
      const c = fc.properties.aoi.center;
      if (c) map.jumpTo({ center: c, zoom: 15 });
      return;
    }
    let w = Infinity,
      s = Infinity,
      e = -Infinity,
      n = -Infinity;
    for (const f of fc.features) {
      const [lon, lat] = f.properties.centroid;
      w = Math.min(w, lon);
      e = Math.max(e, lon);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
    }
    map.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: { top: 70, bottom: 40, left: 40, right: 40 }, duration: 0 },
    );
  }, [ready, fc, mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !selected || !fc) return;
    const f = fc.features.find((x) => x.properties.ncr_id === selected);
    if (f)
      map.easeTo({
        center: f.properties.centroid as [number, number],
        zoom: Math.max(map.getZoom(), 17),
        duration: 350,
      });
  }, [selected, ready, fc, mapRef]);

  // The assessment's own before / after image as a raster layer under the
  // structures (deck.gl draws above the map) and under the basemap's top labels.
  const shown = fc && areaId && imagery !== "off" ? (imagery === "swipe" ? "post" : imagery) : null;
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !areaId || !shown) return;
    // the tiles are responder-only: send the token as a header, never in the URL
    map.setTransformRequest((url) => (isOpsUrl(url) ? { url, headers: opsRequestHeaders() } : { url }));
    const id = "ops-imagery";
    try {
      map.addSource(id, {
        type: "raster",
        tiles: [imageryTileUrl(areaId, shown)],
        tileSize: 256,
        minzoom: 12,
        maxzoom: 19, // the stored 0.3 m grid; the map upsamples beyond it
      });
      // above every drawn basemap layer (roads and building blocks would
      // otherwise cover the photo), below the labels that close the style
      const layers = map.getStyle().layers;
      let lastDrawn = -1;
      layers.forEach((l, i) => {
        if (l.type !== "symbol") lastDrawn = i;
      });
      map.addLayer({ id, type: "raster", source: id, paint: { "raster-fade-duration": 0 } }, layers[lastDrawn + 1]?.id);
    } catch {
      /* style mid-swap: the styleEpoch bump re-runs this */
    }
    return () => {
      try {
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(id)) map.removeSource(id);
      } catch {
        /* map torn down */
      }
    };
  }, [ready, mapRef, styleEpoch, areaId, shown]);

  // Overview: one marker per assessed area. They are real buttons (keyboard
  // and screen-reader reachable), sized-in-place HTML rather than canvas marks.
  const located = useMemo(
    () =>
      (areas ?? []).flatMap((a) => {
        const c =
          a.aoi.center ??
          (a.bbox ? ([(a.bbox[0] + a.bbox[2]) / 2, (a.bbox[1] + a.bbox[3]) / 2] as [number, number]) : null);
        return c ? [{ a, c }] : [];
      }),
    [areas],
  );
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || located.length === 0) return;
    const maxSev = Math.max(1, ...located.map(({ a }) => sevOf(a)));
    const markers = located.map(({ a, c }) => {
      const sev = Math.round(sevOf(a));
      const el = document.createElement("button");
      el.type = "button";
      el.className =
        "group flex items-center gap-1.5 rounded border border-line-strong bg-surface py-1 pl-1.5 pr-2 text-[12px] font-semibold text-ink shadow-1 hover:border-accent focus-visible:border-accent";
      el.setAttribute(
        "aria-label",
        `Open ${areaTitle(a.id, a.aoi.name)}: about ${sev} structures at Major or Destroyed, ${a.n_needs_review} to review`,
      );
      // the dot grows with the expected count at Major or Destroyed
      const dot = document.createElement("span");
      const r = 6 + 8 * Math.sqrt(sevOf(a) / maxSev);
      dot.className = "shrink-0 rounded-full ring-2 ring-surface";
      dot.style.width = dot.style.height = `${r}px`;
      dot.style.background = FEMA_HEX.major;
      const name = document.createElement("span");
      name.textContent = areaTitle(a.id, a.aoi.name);
      const n = document.createElement("span");
      n.className = "tnum font-mono text-xs font-normal text-ink-dim";
      n.textContent = `~${sev}`;
      n.title = "Expected structures at Major or Destroyed";
      el.append(dot, name, n);
      // while a centre is being picked, a click on a marker must reach the map
      if (picking) el.style.pointerEvents = "none";
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onOpenArea(a.id);
      });
      return new Marker({ element: el, anchor: "left", offset: [-9, 0] }).setLngLat(c).addTo(map);
    });
    return () => markers.forEach((m) => m.remove());
  }, [ready, mapRef, located, onOpenArea, picking]);

  // the overview frames one event's areas (the most recent by default, or the
  // one picked in the rail), not every area on the continent at once
  const fitted = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !fitEvent || fitted.current === fitEvent) return;
    const pts = located.filter(({ a }) => a.event?.id === fitEvent).map((x) => x.c);
    if (!pts.length) return;
    const first = fitted.current === null;
    fitted.current = fitEvent;
    const lons = pts.map((c) => c[0]);
    const lats = pts.map((c) => c[1]);
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: { top: 70, bottom: 70, left: 70, right: 150 }, duration: first ? 0 : 600, maxZoom: 12 },
    );
  }, [ready, mapRef, located, fitEvent]);

  // a typed or picked centre that is off screen (or a dot at state zoom) is
  // brought into view, once per location
  const previewKey = preview ? `${preview.lon},${preview.lat}` : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !preview) return;
    const ring = previewRing(preview);
    const b = map.getBounds();
    const inside = ring.every(([x, y]) => b.contains([x, y]));
    if (!inside || map.getZoom() < 11) map.fitBounds([ring[0], ring[2]], { padding: 120, duration: 300, maxZoom: 15 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey, ready, mapRef]);

  // map-click picking for a new assessment
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const canvas = map.getCanvas();
    canvas.style.cursor = picking ? "crosshair" : "";
    if (!picking) return;
    const onClick = (e: { lngLat: { lng: number; lat: number } }) => onPick([e.lngLat.lng, e.lngLat.lat]);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onPick(null);
    };
    map.on("click", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      map.off("click", onClick);
      window.removeEventListener("keydown", onKey);
      canvas.style.cursor = "";
    };
  }, [picking, ready, mapRef, onPick]);

  const data = useMemo(
    () =>
      fc
        ? fc.features.filter(
            (f) =>
              (!reviewOnly || isOpen(f.properties, labels)) && !hidden.has(f.properties.damage_level ?? "none"),
          )
        : [],
    [fc, reviewOnly, hidden, labels],
  );

  // outlines that must read on both base maps and on imagery
  const dark = effective === "dark";

  // 3D: MapLibre extrusions (they follow the terrain); deck's flat layers step aside
  useBuildings3D({
    map: mapRef.current,
    ready,
    styleEpoch,
    on: view3d,
    terrain,
    features: data as OpsFeature[],
    selected,
    dark,
    onSelect,
    onHover: setHoverR,
  });
  const SELECT: [number, number, number] = dark ? [255, 255, 255] : [12, 14, 16];
  const LABELED: [number, number, number] = dark ? [215, 215, 210] : [40, 40, 40];

  const layers = useMemo(() => {
    const out: (
      | GeoJsonLayer<OpsProps>
      | ScatterplotLayer<Preview>
      | PolygonLayer<OpsAreaSummary>
      | PolygonLayer<Preview>
      | ReturnType<typeof responseLayers>[number]
    )[] = [
      // overview: the extent each assessment covered, so a new one is not
      // placed on top of ground that has already been assessed
      new PolygonLayer<OpsAreaSummary>({
        id: "ops-area-extents",
        data: (areas ?? []).filter((a) => a.bbox),
        getPolygon: (a) => {
          const [w, s, e, n] = a.bbox!;
          return [
            [w, s],
            [e, s],
            [e, n],
            [w, n],
          ];
        },
        stroked: true,
        filled: true,
        getFillColor: [...hexRgb(FEMA_HEX.major), 24],
        getLineColor: [...hexRgb(FEMA_HEX.major), 190],
        lineWidthUnits: "pixels",
        getLineWidth: 1.25,
      }),
      new GeoJsonLayer<OpsProps>({
        id: "ops-structures",
        data: view3d ? [] : (data as OpsFeature[]),
        pickable: !picking,
        stroked: true,
        filled: true,
        pointType: "circle",
        getPointRadius: 5,
        pointRadiusUnits: "pixels",
        lineWidthUnits: "pixels",
        getFillColor: (f): RGBA => {
          const p = f.properties;
          if (!p.damage_level) return [...hexRgb(NOT_ASSESSED_HEX), 220];
          // over imagery the fill is a tint, so the roof stays readable
          const c = p.confidence ?? 0;
          return [...hexRgb(FEMA_HEX[p.damage_level]), Math.round(shown ? 45 + 60 * c : 80 + 170 * c)];
        },
        getLineColor: (f): RGBA => {
          const p = f.properties;
          if (p.ncr_id === selected) return [...SELECT, 255];
          if (labels[p.ncr_id]) return [...LABELED, 255];
          if (p.needs_review && p.damage_level) return [...REVIEW, 255];
          if (shown && p.damage_level) return [...hexRgb(FEMA_HEX[p.damage_level]), 255];
          return [110, 110, 110, 170];
        },
        getLineWidth: (f) =>
          f.properties.ncr_id === selected ? 4 : f.properties.needs_review ? 2 : shown ? 1.5 : 0.8,
        updateTriggers: {
          getFillColor: [shown],
          getLineColor: [selected, labels, shown, dark],
          getLineWidth: [selected, shown],
        },
        onClick: (info: PickingInfo) => {
          const f = info.object as OpsFeature | undefined;
          onSelect(f ? f.properties.ncr_id : null);
        },
        onHover: (info: PickingInfo) => {
          const f = info.object as OpsFeature | undefined;
          setHover(f && info.x != null ? { x: info.x, y: info.y, p: f.properties } : null);
        },
      }),
    ];
    if (preview) {
      out.push(
        new PolygonLayer<Preview>({
          id: "ops-preview-extent",
          data: [preview],
          getPolygon: previewRing,
          stroked: true,
          filled: true,
          getFillColor: [...ACCENT, 28],
          getLineColor: [...ACCENT, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 2,
        }),
        new ScatterplotLayer<Preview>({
          id: "ops-preview-centre",
          data: [preview],
          getPosition: (d) => [d.lon, d.lat],
          getRadius: 5,
          radiusUnits: "pixels",
          stroked: true,
          filled: false,
          getLineColor: [...ACCENT, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 2,
        }),
      );
    }
    if (resp && !view3d) out.push(...responseLayers(resp, setHoverR));
    return out;
    // SELECT and LABELED follow `dark`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, areas, selected, labels, onSelect, picking, preview, shown, dark, resp, view3d]);

  // deck.gl's overlay cannot follow MapLibre terrain (it throws reading the
  // terrain elevation every frame), and in 3D MapLibre draws the buildings
  // itself: so while terrain is on the overlay is detached, then re-attached
  const noDeck = view3d && terrain;
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (noDeck) {
      if (overlayRef.current) {
        try {
          map.removeControl(overlayRef.current as unknown as IControl);
        } catch {
          /* torn down */
        }
        overlayRef.current = null;
      }
      return;
    }
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(overlayRef.current as unknown as IControl);
    }
    overlayRef.current.setProps({ layers });
  }, [ready, mapRef, layers, noDeck]);

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

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" aria-label="Damage map" />
      {imagery === "swipe" && !view3d && ready && areaId && fc && mapRef.current && (
        <SwipeCompare main={mapRef.current} areaId={areaId} beforeLabel={beforeLabel} afterLabel={afterLabel} />
      )}
      {hoverR && !hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-xs rounded border border-line-strong bg-surface px-2.5 py-1.5 shadow-2"
          style={{ left: hoverR.x + 14, top: hoverR.y + 14 }}
        >
          <div className="text-[13px] font-semibold text-ink">{hoverR.title}</div>
          <div className="text-xs text-ink-dim">{hoverR.sub}</div>
        </div>
      )}
      {hover && !picking && (
        <div
          className="pointer-events-none absolute z-10 rounded border border-line-strong bg-surface px-2.5 py-1.5 shadow-2"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
            <Swatch c={hover.p.damage_level ?? "none"} />
            {hover.p.damage_level ? FEMA_LABEL[hover.p.damage_level] : "Not assessed"}
            {hover.p.confidence != null && (
              <span className="tnum font-mono text-xs font-normal text-ink-dim">
                {(hover.p.confidence * 100).toFixed(0)}%
              </span>
            )}
            {hover.p.needs_review && <Tag tone="review">review</Tag>}
          </div>
          <div className="tnum font-mono text-xs text-ink-dim">{hover.p.usng_10m}</div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// response layers (Respond tab)
// --------------------------------------------------------------------------- //
type RF = ResponseLayers["features"][number];
// FEMA lifeline colours (toolkit v2.1): red, yellow, green, grey
const LL_RGB = {
  red: [197, 32, 56],
  yellow: [251, 186, 22],
  green: [94, 156, 66],
  grey: [145, 147, 149],
} as const satisfies Record<string, [number, number, number]>;
const ROAD_RGB: Record<string, readonly [number, number, number]> = {
  blocked: LL_RGB.red,
  debris: LL_RGB.yellow,
  bridge: LL_RGB.grey,
};
const FAC_RGB: Record<string, readonly [number, number, number]> = {
  disrupted: LL_RGB.red,
  at_risk: LL_RGB.yellow,
  no_evidence: LL_RGB.green,
  not_assessed: LL_RGB.grey,
};
const FAC_WORD: Record<string, string> = {
  disrupted: "disrupted",
  at_risk: "at risk",
  no_evidence: "no sign of disruption",
  not_assessed: "not checked",
};
const pt = (f: RF) => f.geometry.coordinates as [number, number];
const str = (v: unknown) => (v == null ? "" : String(v));

function responseLayers(
  resp: ResponseLayers,
  onHover: (h: { x: number; y: number; title: string; sub: string } | null) => void,
) {
  const by = (k: string) => resp.features.filter((f) => f.properties.layer === k);
  const hover = (title: (f: RF) => string, sub: (f: RF) => string) => (info: PickingInfo) => {
    const f = info.object as RF | undefined;
    onHover(f && info.x != null ? { x: info.x, y: info.y, title: title(f), sub: sub(f) } : null);
  };
  return [
    new PathLayer<RF>({
      id: "resp-roads",
      data: by("road"),
      getPath: (f) => f.geometry.coordinates as [number, number][],
      getColor: (f) => [...(ROAD_RGB[str(f.properties.status)] ?? LL_RGB.grey), 235],
      getWidth: (f) => (f.properties.status === "blocked" ? 5 : 3.5),
      widthUnits: "pixels",
      capRounded: true,
      jointRounded: true,
      pickable: true,
      onHover: hover(
        (f) => `${str(f.properties.name) || "Road"}: ${f.properties.status === "bridge" ? "bridge, unverified" : str(f.properties.status)}`,
        (f) => ((f.properties.why as string[] | undefined) ?? []).join("; "),
      ),
    }),
    new ScatterplotLayer<RF>({
      id: "resp-cutoff",
      data: by("cut_off_cluster"),
      getPosition: pt,
      // a hollow ring sized by people: access, not damage, so it must not
      // read as a red fill on top of the damage colours
      getRadius: (f) => 25 + 3 * Math.sqrt(Number(f.properties.people_est ?? 0)),
      radiusUnits: "meters",
      stroked: true,
      filled: false,
      getLineColor: [...LL_RGB.red, 230],
      lineWidthUnits: "pixels",
      getLineWidth: 2,
      pickable: true,
      onHover: hover(
        () => "Cut off if debris blocks nearby roads",
        (f) => `${str(f.properties.people_est)} people · ${str(f.properties.buildings)} buildings · ${str(f.properties.usng)}`,
      ),
    }),
    new ScatterplotLayer<RF>({
      id: "resp-facilities",
      data: by("facility"),
      getPosition: pt,
      getRadius: (f) => (f.properties.critical ? 7 : 5.5),
      radiusUnits: "pixels",
      stroked: true,
      getFillColor: (f) => [...(FAC_RGB[str(f.properties.status)] ?? LL_RGB.grey), 255],
      getLineColor: [255, 255, 255, 255],
      lineWidthUnits: "pixels",
      getLineWidth: 1.5,
      pickable: true,
      onHover: hover(
        (f) => `${str(f.properties.name) || str(f.properties.kind).replace(/_/g, " ")}`,
        (f) => `${str(f.properties.kind).replace(/_/g, " ")} · ${FAC_WORD[str(f.properties.status)] ?? ""}`,
      ),
    }),
    new ScatterplotLayer<RF>({
      id: "resp-lz-ring",
      data: by("landing_zone"),
      getPosition: pt,
      getRadius: 9,
      radiusUnits: "pixels",
      stroked: true,
      filled: true,
      getFillColor: [20, 25, 27, 200],
      getLineColor: [255, 255, 255, 255],
      lineWidthUnits: "pixels",
      getLineWidth: 2,
      pickable: true,
      onHover: hover(
        (f) => `Landing candidate ${str(f.properties.usng)}`,
        (f) =>
          `${str(f.properties.clear_diameter_m)} m clear · ${str(f.properties.slope_deg)}° slope · reconnaissance candidate, not an approved LZ`,
      ),
    }),
    new TextLayer<RF>({
      id: "resp-lz-h",
      data: by("landing_zone"),
      getPosition: pt,
      getText: () => "H",
      getSize: 12,
      getColor: [255, 255, 255, 255],
      fontWeight: 700,
      fontFamily: "IBM Plex Mono, monospace",
    }),
    new ScatterplotLayer<RF>({
      id: "resp-sector-dot",
      data: by("sector"),
      getPosition: pt,
      getRadius: 11,
      radiusUnits: "pixels",
      stroked: true,
      getFillColor: [233, 231, 224, 240],
      getLineColor: [20, 25, 27, 255],
      lineWidthUnits: "pixels",
      getLineWidth: 2,
      pickable: true,
      onHover: hover(
        (f) => `Search priority ${str(f.properties.priority)} · ${str(f.properties.usng_1km)}`,
        (f) =>
          `${Math.round(Number(f.properties.people_in_severe_expected ?? 0))} people in severe damage · ${Math.round(
            Number(f.properties.major_or_destroyed_expected ?? 0),
          )} buildings at Major or Destroyed`,
      ),
    }),
    new TextLayer<RF>({
      id: "resp-sector-n",
      data: by("sector"),
      getPosition: pt,
      getText: (f) => str(f.properties.priority),
      getSize: 12,
      getColor: [20, 25, 27, 255],
      fontWeight: 700,
      fontFamily: "IBM Plex Mono, monospace",
    }),
  ];
}

// --------------------------------------------------------------------------- //
// new assessment: a four-step form beside the map
// --------------------------------------------------------------------------- //
const SIZES = [
  { half_m: 400, label: "Small", detail: "0.8 km across · about 2 min" },
  { half_m: 800, label: "Medium", detail: "1.6 km across · about 4 min" },
  { half_m: 1200, label: "Large", detail: "2.4 km across · 10+ min" },
];
/** US states and territories: the API refuses anything else */
const inUS = (lo: number, la: number) => lo >= -180 && lo <= -64 && la >= 17 && la <= 72;

function NewAssessment({
  pick,
  picking,
  onPickToggle,
  onPreview,
  onSubmitted,
  onClose,
}: {
  pick: [number, number] | null;
  picking: boolean;
  onPickToggle: () => void;
  onPreview: (p: Preview | null) => void;
  onSubmitted: (job: Job) => void;
  onClose: () => void;
}) {
  const [events, setEvents] = useState<OpsEvent[] | null>(null);
  const [event, setEvent] = useState("");
  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [half, setHalf] = useState(400);
  const [cov, setCov] = useState<{ ok: boolean; text: string; pre?: string; post?: string } | "checking" | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastPick, setLastPick] = useState<[number, number] | null>(null);

  const reloadEvents = useCallback((pickId?: string) => {
    loadEvents()
      .then((e) => {
        setEvents(e);
        setEvent((cur) => pickId || cur || (e[0]?.id ?? ""));
      })
      .catch(() => setEvents([]));
  }, []);
  useEffect(() => reloadEvents(), [reloadEvents]);

  // a map click fills the coordinates (adjusting state during render, the
  // React-recommended way to react to a changed prop)
  if (pick && pick !== lastPick) {
    setLastPick(pick);
    setLon(pick[0].toFixed(5));
    setLat(pick[1].toFixed(5));
    setCov(null);
  }

  const la = Number(lat);
  const lo = Number(lon);
  const coordsOk = lat !== "" && lon !== "" && Number.isFinite(la) && Number.isFinite(lo) && inUS(lo, la);

  // show the square this assessment would cover, typed or picked
  useEffect(() => {
    onPreview(coordsOk ? { lon: lo, lat: la, half_m: half } : null);
  }, [coordsOk, lo, la, half, onPreview]);
  useEffect(() => () => onPreview(null), [onPreview]);

  const check = async () => {
    setCov("checking");
    try {
      const c = await checkCoverageFull(event, lo, la);
      setCov(
        c.covered
          ? {
              ok: true,
              text: "Imagery covers this point.",
              post: POST_SOURCE_LABEL[c.post_source ?? ""] ?? c.post_source,
              pre: c.pre_source ? (PRE_SOURCE_LABEL[c.pre_source] ?? c.pre_source) : undefined,
            }
          : { ok: false, text: c.reason ?? "Not covered." },
      );
    } catch (e) {
      const m = (e as Error).message;
      setCov({
        ok: false,
        text: /40[13]/.test(m)
          ? "Responder access is needed to check imagery: set it with the key in the top bar."
          : `Check failed: ${m}`,
      });
    }
  };

  const submit = async () => {
    setBusy(true);
    try {
      onSubmitted(await submitAssessment({ event, name: name.trim(), lon: lo, lat: la, half_m: half }));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ev = events?.find((e) => e.id === event);
  const steps = [!!event, coordsOk && name.trim().length >= 2, true, cov !== null && cov !== "checking" && cov.ok];

  return (
    <div className="flex flex-col md:min-h-0 md:flex-1">
      <header className="flex h-11 shrink-0 items-center gap-2 border-b border-line px-4">
        <h1 className="title-display text-[20px]">New assessment</h1>
        <button className={btnClass("ghost", "sm", "ml-auto w-7 px-0")} onClick={onClose} aria-label="Close">
          <Icon name="x" />
        </button>
      </header>
      <div className="space-y-5 p-4 md:min-h-0 md:flex-1 md:overflow-y-auto">
        <Step n={1} title="Event" done={steps[0]}>
          <select className="field" value={event} onChange={(e) => setEvent(e.target.value)} aria-label="Event">
            {(events ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.name.replace(/\s*\([^)]*DR-\d+[^)]*\)\s*$/, "")}
              </option>
            ))}
          </select>
          {ev && (
            <div className="mt-1.5 text-xs text-ink-faint">
              <span className="font-mono text-ink-dim">{ev.declarations.join(", ") || "provisional"}</span> · incident
              from <span className="font-mono">{ev.incident_begin}</span> · after-event imagery from{" "}
              {ev.post_sources.map((s) => POST_SOURCE_LABEL[s]?.split(" (")[0] ?? s).join(", ")}
            </div>
          )}
          <FromFema onCreated={(id) => reloadEvents(id)} />
        </Step>

        <Step n={2} title="Place" done={steps[1]}>
          <label className="block">
            <span className="text-xs text-ink-dim">Place name</span>
            <input
              className="field mt-1"
              value={name}
              maxLength={60}
              placeholder="e.g. Marion downtown"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <Button
            className="mt-2 w-full"
            variant={coordsOk ? "secondary" : "primary"}
            onClick={onPickToggle}
            aria-pressed={picking}
            icon={<Icon name="target" className="h-3.5 w-3.5" />}
          >
            {picking ? "Click the map… (cancel)" : coordsOk ? "Pick again on the map" : "Pick the centre on the map"}
          </Button>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <label>
              <span className="text-xs text-ink-dim">Latitude</span>
              <input
                className="field mt-1 font-mono"
                value={lat}
                inputMode="decimal"
                placeholder="35.684"
                aria-invalid={!!lat && !coordsOk}
                onChange={(e) => {
                  setLat(e.target.value);
                  setCov(null);
                }}
              />
            </label>
            <label>
              <span className="text-xs text-ink-dim">Longitude</span>
              <input
                className="field mt-1 font-mono"
                value={lon}
                inputMode="decimal"
                placeholder="-82.009"
                aria-invalid={!!lon && !coordsOk}
                onChange={(e) => {
                  setLon(e.target.value);
                  setCov(null);
                }}
              />
            </label>
          </div>
          {!coordsOk && (lat || lon) && (
            <p className="mt-1.5 text-xs text-st-bad">The point must be in the United States (longitude is negative).</p>
          )}
        </Step>

        <Step n={3} title="Size" done={steps[2] && coordsOk}>
          <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Area size">
            {SIZES.map((s) => (
              <button
                key={s.half_m}
                role="radio"
                aria-checked={half === s.half_m}
                onClick={() => setHalf(s.half_m)}
                className={`pressable rounded border px-2 py-2 text-left ${
                  half === s.half_m ? "border-accent bg-accent-soft" : "border-line-strong hover:bg-surface-2"
                }`}
              >
                <div className="text-[13px] font-semibold text-ink">{s.label}</div>
                <div className="text-xs leading-snug text-ink-dim">{s.detail}</div>
              </button>
            ))}
          </div>
        </Step>

        <Step n={4} title="Check and run" done={steps[3]}>
          <div className="flex gap-2">
            <Button onClick={check} disabled={!coordsOk || !event || cov === "checking"} busy={cov === "checking"}>
              Check imagery
            </Button>
            <Button
              variant="primary"
              onClick={submit}
              disabled={busy || !coordsOk || !event || name.trim().length < 2}
              busy={busy}
            >
              Run assessment
            </Button>
          </div>
          {cov && cov !== "checking" && (
            <div
              className={`mt-2 rounded border p-2.5 text-xs leading-relaxed ${
                cov.ok ? "border-st-ok/40 bg-st-ok/10" : "border-st-bad/40 bg-st-bad/10"
              }`}
              role="status"
            >
              <b className="text-ink">{cov.text}</b>
              {cov.pre && <div className="text-ink-dim">Before: {cov.pre}</div>}
              {cov.post && <div className="text-ink-dim">After: {cov.post}</div>}
            </div>
          )}
          {name.trim().length < 2 && coordsOk && (
            <p className="mt-1.5 text-xs text-ink-faint">Give the place a name to run it.</p>
          )}
        </Step>
      </div>
    </div>
  );
}

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: ReactNode }) {
  return (
    <section className="flex gap-3">
      <span
        className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full font-mono text-xs ${
          done ? "bg-accent text-accent-ink" : "border border-line-strong text-ink-dim"
        }`}
        aria-hidden
      >
        {done ? <Icon name="check" className="h-3.5 w-3.5" /> : n}
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="mb-2 text-[13px] text-ink">{title}</h2>
        {children}
      </div>
    </section>
  );
}

/** Start an event from its FEMA disaster number: the server reads the
 * declaration, picks the hazards and the imagery that matches; the analyst
 * sees the draft before anything is registered. */
function FromFema({ onCreated }: { onCreated: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [num, setNum] = useState("");
  const [draft, setDraft] = useState<FemaEventDraft | null>(null);
  const [state, setState] = useState<"idle" | "looking" | "saving">("idle");
  const [err, setErr] = useState<string | null>(null);
  const [manual, setManual] = useState(false);
  const lookup = async () => {
    setState("looking");
    setErr(null);
    setDraft(null);
    try {
      setDraft((await eventFromFema(Number(num), false)).draft);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setState("idle");
    }
  };
  const register = async () => {
    setState("saving");
    try {
      const r = await eventFromFema(Number(num), true);
      toast.success(`Event registered: ${r.event?.name ?? r.draft.name}`);
      onCreated(r.event?.id ?? r.draft.event_id);
      setOpen(false);
      setDraft(null);
      setNum("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setState("idle");
    }
  };
  if (!open)
    return (
      <button className="mt-2 text-xs font-medium text-accent hover:underline" onClick={() => setOpen(true)}>
        Event not listed? Start it from its FEMA disaster number
      </button>
    );
  return (
    <div className="mt-2 rounded border border-line bg-canvas p-2.5">
      <label className="text-xs text-ink-dim" htmlFor="fema-num">
        FEMA disaster number
      </label>
      <div className="mt-1 flex gap-2">
        <input
          id="fema-num"
          className="field font-mono"
          inputMode="numeric"
          placeholder="4856"
          value={num}
          onChange={(e) => setNum(e.target.value.replace(/\D/g, "").slice(0, 4))}
          onKeyDown={(e) => e.key === "Enter" && num && void lookup()}
        />
        <Button onClick={lookup} disabled={!num || state !== "idle"} busy={state === "looking"}>
          Look up
        </Button>
      </div>
      {err && <p className="mt-1.5 text-xs text-st-bad">{err}</p>}
      {draft && (
        <div className="mt-2.5 space-y-1.5 text-xs">
          <div className="text-[13px] font-semibold text-ink">{draft.name}</div>
          <div className="text-ink-dim">
            Incident began <span className="font-mono text-ink">{draft.incident_begin}</span> ·{" "}
            {draft.designated_areas.length} designated area{draft.designated_areas.length === 1 ? "" : "s"}
          </div>
          <div className="flex flex-wrap gap-1">
            {draft.hazards.map((h) => (
              <Tag key={h}>{HAZARD_LABEL[h] ?? h}</Tag>
            ))}
          </div>
          <div className="text-ink-dim">
            After-event imagery:{" "}
            {draft.eri_prefix || draft.maxar_event ? (
              <span className="text-ink">
                {[draft.eri_prefix && `NOAA ${draft.eri_prefix.replace(/_/g, " ")}`, draft.maxar_event && `Maxar ${draft.maxar_event}`]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            ) : (
              <span className="text-st-warn">none matched yet</span>
            )}
          </div>
          {draft.notes.map((n) => (
            <p key={n} className="text-ink-faint">
              {n}
            </p>
          ))}
          <Button variant="primary" size="sm" className="mt-1" onClick={register} busy={state === "saving"} disabled={state !== "idle"}>
            Register this event
          </Button>
        </div>
      )}
      <div className="mt-2 flex gap-3 text-xs">
        <button className="text-ink-dim hover:text-ink" onClick={() => setManual((v) => !v)}>
          {manual ? "Hide manual entry" : "No declaration yet? Enter it by hand"}
        </button>
        <button className="ml-auto text-ink-dim hover:text-ink" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {manual && <NewEvent onCreated={onCreated} />}
    </div>
  );
}

function NewEvent({ onCreated }: { onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [dr, setDr] = useState("");
  const [eri, setEri] = useState("");
  const id =
    name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) + (date ? `-${date.slice(0, 4)}` : "");
  const create = async () => {
    try {
      const ev = await createEvent({
        id,
        name,
        incident_begin: date,
        disaster_numbers: dr
          .split(/[ ,]+/)
          .filter(Boolean)
          .map(Number)
          .filter(Number.isFinite),
        eri_prefix: eri || undefined,
      });
      toast.success(`Event registered: ${ev.name}`);
      onCreated(ev.id);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  return (
    <div className="mt-2 space-y-2 border-t border-line pt-2 text-xs">
      <label className="block">
        <span className="text-ink-dim">Event name</span>
        <input className="field mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Tropical Storm X" />
      </label>
      <label className="block">
        <span className="text-ink-dim">Incident start date</span>
        <input className="field mt-1" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label className="block">
        <span className="text-ink-dim">NOAA emergency imagery folder, if flown</span>
        <input className="field mt-1 font-mono" value={eri} onChange={(e) => setEri(e.target.value)} placeholder="2026_Tropical_Storm_X" />
      </label>
      <label className="block">
        <span className="text-ink-dim">FEMA disaster number(s), if declared later</span>
        <input className="field mt-1 font-mono" value={dr} onChange={(e) => setDr(e.target.value)} placeholder="" />
      </label>
      <Button size="sm" variant="primary" disabled={name.length < 3 || !date} onClick={create}>
        Register provisional event
      </Button>
    </div>
  );
}
