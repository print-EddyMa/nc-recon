import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { toast } from "sonner";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import {
  FEMA,
  FEMA_HEX,
  FEMA_LABEL,
  NOT_ASSESSED_HEX,
  POST_SOURCE_LABEL,
  ago,
  checkCoverage,
  createEvent,
  deleteArea,
  downloadExport,
  fmtAge,
  jobStatus,
  labelerName,
  loadChip,
  loadEvents,
  loadHealth,
  loadImpact,
  loadLabels,
  loadOpsArea,
  loadOpsAreas,
  loadReport,
  loadResponder,
  occupantsOf,
  openBrief,
  postLabel,
  pSevere,
  publicUrl,
  responderToken,
  reviewPriority,
  setLabelerName,
  setResponderToken,
  submitAssessment,
  type FemaClass,
  type HealthRow,
  type Impact,
  type Job,
  type OpsAreaSummary,
  type OpsCollection,
  type OpsEvent,
  type OpsFeature,
  type OpsProps,
} from "../lib/ops";
import { API_URL } from "../lib/catalog";

type RGBA = [number, number, number, number];
const hexRgb = (h: string): [number, number, number] => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];
const ACCENT: [number, number, number] = [37, 99, 235];
const NC_CENTER: [number, number] = [-81.2, 35.5];

const btn =
  "inline-flex items-center rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-2 disabled:opacity-50";
const btnPrimary =
  "rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50";
const h2 = "text-sm font-semibold uppercase tracking-wide text-ink-dim";
const field =
  "mt-1 w-full rounded-md border border-line-strong bg-canvas px-2.5 py-1.5 text-sm text-ink";

const areaTitle = (id: string) =>
  id
    .replace(/_[0-9a-f]{4}$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

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
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [addresses, setAddresses] = useState<Record<string, string>>({});
  const [newOpen, setNewOpen] = useState(false);
  const [pick, setPick] = useState<[number, number] | null>(null);
  const [picking, setPicking] = useState(false);

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

  // the screen is remounted per area (key={areaId} in App), so state starts clean
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
    loadResponder(areaId)
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
  }, [areaId]);

  const byId = useMemo(() => {
    const m = new Map<string, OpsFeature>();
    for (const f of fc?.features ?? []) m.set(f.properties.ncr_id, f as OpsFeature);
    return m;
  }, [fc]);

  const queue = useMemo(
    () =>
      (fc?.features ?? [])
        .map((f) => f.properties)
        .filter((p) => p.needs_review && p.damage_level && !labels[p.ncr_id])
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
        const r = await postLabel({ area: areaId, ncr_id: p.ncr_id, label: lab, labeler: who });
        setLabels((m) => ({ ...m, [p.ncr_id]: lab }));
        toast.success(`Recorded "${lab.replace("_", " ")}" (${r.aoi_role} area)`);
        const next = queue.find((q) => q.ncr_id !== p.ncr_id);
        if (next) setSelected(next.ncr_id);
      } catch (e) {
        toast.error((e as Error).message);
      }
    },
    [areaId, queue],
  );

  // keyboard labeling: 0-4 = class, x = cannot tell, j/k = next/prev, Esc = close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!sel || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
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
        if (n) setSelected(n.ncr_id);
      } else if (e.key === "Escape") {
        setSelected(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sel, queue, label]);

  const onDone = useCallback(
    (area: string) => {
      refreshAreas();
      setNewOpen(false);
      setPick(null);
      onPickArea(area);
    },
    [refreshAreas, onPickArea],
  );
  const onPick = useCallback((ll: [number, number] | null) => {
    setPicking(false);
    if (ll) {
      setPick(ll);
      setNewOpen(true);
    }
  }, []);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 overflow-y-auto md:grid-cols-[300px_1fr] md:overflow-hidden xl:grid-cols-[320px_1fr_400px]">
      {/* ---------------------------- left ---------------------------- */}
      <aside className="min-h-0 border-b border-line bg-surface p-4 md:overflow-y-auto md:border-b-0 md:border-r">
        <div className="flex items-center justify-between">
          <h2 className={h2}>Assessments</h2>
          <button
            className={btnPrimary}
            onClick={() => setNewOpen((v) => !v)}
            aria-expanded={newOpen}
            disabled={!API_URL}
          >
            {newOpen ? "Close" : "New assessment"}
          </button>
        </div>
        {newOpen && (
          <NewAssessment
            pick={pick}
            picking={picking}
            onPickToggle={() => setPicking((v) => !v)}
            onDone={onDone}
            onQueued={refreshAreas}
          />
        )}
        <AreaList areas={areas} err={areasErr} areaId={areaId} onPick={onPickArea} />
        <AccuracyPanel />
        <CollectionBoard />
        <ResponderAccess />
      </aside>

      {/* ---------------------------- map ----------------------------- */}
      <section className="relative min-h-[55vh] md:min-h-0" aria-label="Map">
        <OpsMap
          fc={fc}
          selected={selected}
          reviewOnly={reviewOnly}
          labels={labels}
          onSelect={setSelected}
          picking={picking}
          pick={pick}
          onPick={onPick}
        />
        {picking && (
          <div className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-canvas">
            Click the map to set the assessment centre · Esc to cancel
          </div>
        )}
        {fc && (
          <div className="absolute left-3 top-3 flex flex-col gap-2">
            <Legend />
            <label className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={reviewOnly}
                onChange={(e) => setReviewOnly(e.target.checked)}
              />
              Only structures needing review
            </label>
          </div>
        )}
        {!fc && areaId && (
          <div className="absolute inset-x-0 top-16 mx-auto w-fit max-w-md rounded-md border border-line bg-surface px-4 py-3 text-sm">
            {areaErr
              ? /40[13]/.test(areaErr)
                ? "Structure-level results need the responder token (left panel, Responder access). The public summary needs none."
                : `Could not load this assessment (${areaErr}).`
              : "Loading assessment…"}
          </div>
        )}
      </section>

      {/* ---------------------------- right --------------------------- */}
      <aside className="min-h-0 border-t border-line bg-surface p-4 md:col-span-2 xl:col-span-1 xl:overflow-y-auto xl:border-l xl:border-t-0">
        {!areaId && <Welcome />}
        {fc && areaId && (
          <RunSummary
            fc={fc}
            areaId={areaId}
            onDeleted={() => {
              refreshAreas();
              onPickArea(null);
            }}
          />
        )}
        {fc && areaId && <ImpactPanel areaId={areaId} />}
        {fc &&
          areaId &&
          (sel ? (
            <StructureCard
              areaId={areaId}
              f={sel}
              address={addresses[sel.properties.ncr_id]}
              labeled={labels[sel.properties.ncr_id]}
              onLabel={(lab) => void label(sel.properties, lab)}
              onClose={() => setSelected(null)}
            />
          ) : (
            <ReviewList
              queue={queue}
              labeledCount={Object.keys(labels).length}
              onPick={setSelected}
            />
          ))}
      </aside>
    </div>
  );
}

function Welcome() {
  return (
    <div className="text-sm leading-relaxed text-ink-dim">
      <h2 className={h2}>Start here</h2>
      <p className="mt-2">
        Open an assessed area on the left, or choose{" "}
        <b className="text-ink">New assessment</b> to assess a town from
        post-event imagery. Help explains every number on this screen.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// new assessment
// --------------------------------------------------------------------------- //
const SIZES = [
  { half_m: 400, label: "Small: 0.8 km across (about 2 min)" },
  { half_m: 800, label: "Medium: 1.6 km across (about 4 min)" },
  { half_m: 1200, label: "Large: 2.4 km across (10+ min)" },
];

function NewAssessment({
  pick,
  picking,
  onPickToggle,
  onDone,
  onQueued,
}: {
  pick: [number, number] | null;
  picking: boolean;
  onPickToggle: () => void;
  onDone: (area: string) => void;
  onQueued: () => void;
}) {
  const [events, setEvents] = useState<OpsEvent[] | null>(null);
  const [event, setEvent] = useState("");
  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [half, setHalf] = useState(400);
  const [cov, setCov] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [newEvent, setNewEvent] = useState(false);
  const [lastPick, setLastPick] = useState<[number, number] | null>(null);

  const reloadEvents = useCallback(() => {
    loadEvents()
      .then((e) => {
        setEvents(e);
        setEvent((cur) => cur || (e[0]?.id ?? ""));
      })
      .catch(() => setEvents([]));
  }, []);
  useEffect(reloadEvents, [reloadEvents]);

  // a map click fills the coordinates (adjusting state during render, the
  // React-recommended way to react to a changed prop)
  if (pick && pick !== lastPick) {
    setLastPick(pick);
    setLon(pick[0].toFixed(5));
    setLat(pick[1].toFixed(5));
    setCov(null);
  }

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed" || job.status === "lost") return;
    const t = window.setInterval(() => {
      jobStatus(job.id)
        .then((j) => {
          setJob(j);
          if (j.status === "done") {
            toast.success(
              j.warnings?.length
                ? `${j.name}: assessment complete, with warnings`
                : `${j.name}: assessment complete`,
            );
            onDone(j.area);
          } else if (j.status === "failed") toast.error(`${j.name}: ${j.error}`);
        })
        .catch((e: Error) => {
          // job state lives in the server process: a restart loses it
          if (/: 404$/.test(e.message)) {
            setJob((cur) =>
              cur
                ? { ...cur, status: "lost", error: "The server restarted while this assessment was running. Run it again." }
                : cur,
            );
          }
        });
    }, 4000);
    return () => window.clearInterval(t);
  }, [job, onDone]);

  const la = Number(lat);
  const lo = Number(lon);
  const coordsOk =
    lat !== "" && lon !== "" && la > 33.5 && la < 37 && lo > -85 && lo < -75;

  const check = async () => {
    setCov("Checking…");
    try {
      const c = await checkCoverage(event, lo, la);
      setCov(
        c.covered
          ? `Covered. After-event imagery: ${POST_SOURCE_LABEL[c.post_source ?? ""] ?? c.post_source}.`
          : `Not covered: ${c.reason}`,
      );
    } catch (e) {
      setCov(`Check failed: ${(e as Error).message}`);
    }
  };

  const submit = async () => {
    setBusy(true);
    try {
      const j = await submitAssessment({ event, name: name.trim(), lon: lo, lat: la, half_m: half });
      setJob(j);
      onQueued();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 rounded-md border border-line p-3 text-sm">
      {job ? (
        <JobCard job={job} onNew={() => setJob(null)} />
      ) : (
        <>
          <label className="block">
            <span className="text-ink-dim">Event</span>
            <select className={field} value={event} onChange={(e) => setEvent(e.target.value)}>
              {(events ?? []).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} {e.declarations.length ? `(${e.declarations.join(", ")})` : "(provisional)"}
                </option>
              ))}
            </select>
          </label>
          <button
            className="mt-1 text-sm text-accent underline"
            onClick={() => setNewEvent((v) => !v)}
          >
            {newEvent ? "Cancel new event" : "Event not listed? Register one"}
          </button>
          {newEvent && (
            <NewEvent
              onCreated={(id) => {
                setNewEvent(false);
                reloadEvents();
                setEvent(id);
              }}
            />
          )}
          <label className="mt-2 block">
            <span className="text-ink-dim">Place name</span>
            <input
              className={field}
              value={name}
              maxLength={60}
              placeholder="e.g. Marion downtown"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <label>
              <span className="text-ink-dim">Latitude</span>
              <input
                className={field}
                value={lat}
                inputMode="decimal"
                placeholder="35.684"
                onChange={(e) => {
                  setLat(e.target.value);
                  setCov(null);
                }}
              />
            </label>
            <label>
              <span className="text-ink-dim">Longitude</span>
              <input
                className={field}
                value={lon}
                inputMode="decimal"
                placeholder="-82.009"
                onChange={(e) => {
                  setLon(e.target.value);
                  setCov(null);
                }}
              />
            </label>
          </div>
          <button className={`${btn} mt-2 w-full justify-center`} onClick={onPickToggle} aria-pressed={picking}>
            {picking ? "Click the map… (cancel)" : "Pick on map"}
          </button>
          <label className="mt-2 block">
            <span className="text-ink-dim">Area size</span>
            <select className={field} value={half} onChange={(e) => setHalf(Number(e.target.value))}>
              {SIZES.map((s) => (
                <option key={s.half_m} value={s.half_m}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <div className="mt-3 flex gap-2">
            <button className={btn} onClick={check} disabled={!coordsOk || !event}>
              Check imagery
            </button>
            <button
              className={btnPrimary}
              onClick={submit}
              disabled={busy || !coordsOk || !event || name.trim().length < 2}
            >
              {busy ? "Submitting…" : "Run assessment"}
            </button>
          </div>
          {!coordsOk && (lat || lon) && (
            <p className="mt-2 text-sm text-dmg3">Coordinates must be in North Carolina.</p>
          )}
          {cov && <p className="mt-2 text-sm text-ink">{cov}</p>}
        </>
      )}
    </div>
  );
}

const STEPS = [
  "choosing imagery",
  "fetching imagery",
  "assessing structures",
  "estimating people",
  "writing brief",
];

function JobCard({ job, onNew }: { job: Job; onNew: () => void }) {
  const cur = STEPS.indexOf(job.step);
  const done = job.status === "done";
  return (
    <div>
      <div className="font-semibold text-ink">{job.name}</div>
      <div className="text-sm text-ink-dim">
        {job.status === "queued"
          ? "Waiting for the previous assessment to finish"
          : job.status === "running"
            ? "Running"
            : job.status === "done"
              ? "Complete"
              : job.status === "lost"
                ? "Lost"
                : "Failed"}
        {job.post_source && ` · ${POST_SOURCE_LABEL[job.post_source] ?? job.post_source}`}
      </div>
      <ol className="mt-2 space-y-0.5 text-sm">
        {STEPS.map((s, i) => {
          const past = done || i < cur;
          const now = i === cur && job.status === "running";
          return (
            <li key={s} className={past ? "text-ink" : now ? "font-semibold text-accent" : "text-ink-faint"}>
              {past ? "✓" : now ? "▸" : "·"} {s}
            </li>
          );
        })}
      </ol>
      {(job.status === "failed" || job.status === "lost") && (
        <p className="mt-2 text-sm text-dmg3">{job.error}</p>
      )}
      {job.warnings && job.warnings.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm text-ink">
          {job.warnings.map((w) => (
            <li key={w}>Warning: {w}</li>
          ))}
        </ul>
      )}
      {(done || job.status === "failed" || job.status === "lost") && (
        <button className={`${btn} mt-2`} onClick={onNew}>
          New assessment
        </button>
      )}
    </div>
  );
}

function NewEvent({ onCreated }: { onCreated: (id: string) => void }) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [dr, setDr] = useState("");
  const [eri, setEri] = useState("");
  const id =
    name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) +
    (date ? `-${date.slice(0, 4)}` : "");
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
    <div className="mt-2 rounded-md bg-surface-2 p-2.5 text-sm">
      <label className="block">
        <span className="text-ink-dim">Event name</span>
        <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Tropical Storm X" />
      </label>
      <label className="mt-2 block">
        <span className="text-ink-dim">Incident start date</span>
        <input className={field} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label className="mt-2 block">
        <span className="text-ink-dim">FEMA disaster number(s), if declared</span>
        <input className={field} value={dr} onChange={(e) => setDr(e.target.value)} placeholder="4827" />
      </label>
      <label className="mt-2 block">
        <span className="text-ink-dim">NOAA emergency imagery folder, if flown</span>
        <input className={field} value={eri} onChange={(e) => setEri(e.target.value)} placeholder="2026_Tropical_Storm_X" />
      </label>
      <button className={`${btnPrimary} mt-2`} disabled={name.length < 3 || !date} onClick={create}>
        Register event
      </button>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// left panels
// --------------------------------------------------------------------------- //
const ROLE_TITLE: Record<string, string> = {
  TEST: "Held-out evaluation area: never used to tune",
  TUNE: "Tuning area: thresholds may be fitted here",
  OPS: "Operational area",
};

function AreaList({
  areas,
  err,
  areaId,
  onPick,
}: {
  areas: OpsAreaSummary[] | null;
  err: string | null;
  areaId: string | null;
  onPick: (id: string) => void;
}) {
  const sorted = useMemo(
    () =>
      [...(areas ?? [])].sort(
        (a, b) => Date.parse(b.generated_utc) - Date.parse(a.generated_utc),
      ),
    [areas],
  );
  return (
    <section className="mt-4">
      {err && !areas && <p className="text-sm text-dmg3">Assessment service unreachable ({err}).</p>}
      {!areas && !err && <p className="text-sm text-ink-dim">Loading…</p>}
      {areas && areas.length === 0 && <p className="text-sm text-ink-dim">No assessments yet.</p>}
      <ul className="space-y-2">
        {sorted.map((a) => {
          const sev = (a.expected_counts.major ?? 0) + (a.expected_counts.destroyed ?? 0);
          const r = a.expected_counts_80pct ?? {};
          const lo = (r.major?.[0] ?? 0) + (r.destroyed?.[0] ?? 0);
          const hi = (r.major?.[1] ?? 0) + (r.destroyed?.[1] ?? 0);
          return (
            <li key={a.id}>
              <button
                onClick={() => onPick(a.id)}
                aria-current={a.id === areaId ? "true" : undefined}
                className={`w-full rounded-md border px-3 py-2 text-left ${
                  a.id === areaId ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-2"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-ink">{areaTitle(a.id)}</span>
                  <span className="rounded-sm border border-line px-1.5 text-xs text-ink-dim" title={ROLE_TITLE[a.aoi.role] ?? ""}>
                    {a.aoi.role}
                  </span>
                </div>
                <div className="text-xs text-ink-dim">
                  {a.aoi.county
                    ? `${a.aoi.county} Co. · `
                    : a.aoi.center
                      ? `${a.aoi.center[1].toFixed(3)}, ${a.aoi.center[0].toFixed(3)} · `
                      : ""}
                  {a.n_structures.toLocaleString()} structures · {a.n_needs_review.toLocaleString()} to review
                </div>
                <div className="tnum text-sm text-ink">
                  ≥ Major: ~{Math.round(sev)}{" "}
                  <span className="text-xs text-ink-dim">
                    (80% {lo}–{hi})
                  </span>
                </div>
                <div className="text-xs text-ink-faint">assessed {ago(a.generated_utc)}</div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function AccuracyPanel() {
  const [rep, setRep] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    if (!API_URL) return;
    loadReport()
      .then(setRep)
      .catch(() => setRep({ status: "UNAVAILABLE" }));
  }, []);
  const status = rep?.status as string | undefined;
  const roles = (rep?.roles ?? {}) as Record<
    string,
    { all: { n: number; macro_f1: number | null; destroyed_recall: number | null } }
  >;
  return (
    <section className="mt-5 border-t border-line pt-4">
      <h2 className={h2}>Accuracy</h2>
      {rep && status !== "OK" && (
        <p className="mt-1 text-sm leading-relaxed">
          <b className="text-dmg3">Not yet validated.</b>{" "}
          <span className="text-ink-dim">
            No ground-truth labels yet, so no accuracy figure is shown. Treat
            every call as a lead to verify.
          </span>
        </p>
      )}
      {rep &&
        status === "OK" &&
        Object.entries(roles).map(([role, r]) => (
          <div key={role} className="mt-1 text-sm">
            <div className="text-ink-dim">
              {role} areas · {r.all.n} labeled
              {role === "TUNE" && " (fitted here: optimistic)"}
            </div>
            <div className="tnum text-ink">
              macro-F1 {r.all.macro_f1?.toFixed(2) ?? "n/a"} · Destroyed recall{" "}
              {r.all.destroyed_recall?.toFixed(2) ?? "n/a"}
            </div>
          </div>
        ))}
    </section>
  );
}

const STATUS_DOT: Record<HealthRow["status"], string> = {
  ok: "bg-dmg0",
  stale: "bg-dmg1",
  down: "bg-dmg3",
  unconfigured: "bg-ink-faint",
};
const STATUS_WORD: Record<HealthRow["status"], string> = {
  ok: "OK",
  stale: "stale",
  down: "DOWN",
  unconfigured: "not set up",
};

function CollectionBoard() {
  const [h, setH] = useState<{ checked_utc: string; sources: HealthRow[] } | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (!API_URL) return;
    loadHealth()
      .then(setH)
      .catch(() => setErr(true));
  }, []);
  return (
    <section className="mt-5 border-t border-line pt-4">
      <div className="flex items-baseline justify-between">
        <h2 className={h2}>Data sources</h2>
        {h && <span className="text-xs text-ink-faint">checked {ago(h.checked_utc)}</span>}
      </div>
      {err && <p className="mt-1 text-sm text-ink-dim">Status unavailable.</p>}
      <ul className="mt-2 space-y-1">
        {h?.sources
          .filter((s) => s.source !== "usgs_waterservices_legacy")
          .map((s) => (
            <li key={s.source} className="flex items-center gap-2 text-sm" title={s.detail}>
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[s.status]}`} aria-hidden />
              <span className="flex-1 truncate text-ink">{s.source.replace(/_/g, " ")}</span>
              <span className={`text-xs ${s.status === "down" ? "font-semibold text-dmg3" : "text-ink-dim"}`}>
                {STATUS_WORD[s.status]}
                {s.status === "ok" && s.data_age_s != null ? ` · ${fmtAge(s.data_age_s)}` : ""}
              </span>
            </li>
          ))}
      </ul>
    </section>
  );
}

function ResponderAccess() {
  const [tok, setTok] = useState(responderToken());
  const [who, setWho] = useState(labelerName());
  return (
    <section className="mt-5 border-t border-line pt-4">
      <h2 className={h2}>Responder access</h2>
      <p className="mt-1 text-xs leading-relaxed text-ink-dim">
        Structure-level results, addresses, labels, exports and briefs need the
        service token. It is stored only in this browser.
      </p>
      <label className="sr-only" htmlFor="ops-token">Service token</label>
      <input
        id="ops-token"
        type="password"
        value={tok}
        placeholder="Service token"
        className={field}
        onChange={(e) => setTok(e.target.value)}
        onBlur={() => {
          setResponderToken(tok);
          if (tok) toast("Token saved. Reopen the area to load structure-level data.");
        }}
      />
      <label className="sr-only" htmlFor="ops-who">Your name or initials</label>
      <input
        id="ops-who"
        value={who}
        placeholder="Your name / initials (for labels)"
        className={field}
        onChange={(e) => setWho(e.target.value)}
        onBlur={() => setLabelerName(who)}
      />
    </section>
  );
}

function Legend() {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
      <div className="mb-1 text-xs font-semibold text-ink-dim">Most likely FEMA damage level</div>
      {FEMA.map((c) => (
        <div key={c} className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-sm border border-line" style={{ background: FEMA_HEX[c] }} />
          <span className="text-ink">{FEMA_LABEL[c]}</span>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-full" style={{ background: NOT_ASSESSED_HEX }} />
        <span className="text-ink">Not assessed</span>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="h-3 w-3 rounded-sm border-2 border-accent" />
        <span className="text-ink">Needs review</span>
      </div>
      <div className="mt-1 text-xs text-ink-dim">Faint fill = low confidence</div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// map
// --------------------------------------------------------------------------- //
function OpsMap({
  fc,
  selected,
  reviewOnly,
  labels,
  onSelect,
  picking,
  pick,
  onPick,
}: {
  fc: OpsCollection | null;
  selected: string | null;
  reviewOnly: boolean;
  labels: Record<string, string>;
  onSelect: (id: string | null) => void;
  picking: boolean;
  pick: [number, number] | null;
  onPick: (ll: [number, number] | null) => void;
}) {
  const { containerRef, mapRef, ready } = useMapLibre({ center: NC_CENTER, zoom: 6.6, pitch: 0 });
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; p: OpsProps } | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !fc?.features.length) return;
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
      { padding: 40, duration: 0 },
    );
  }, [ready, fc, mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !selected || !fc) return;
    const f = fc.features.find((x) => x.properties.ncr_id === selected);
    if (f)
      map.jumpTo({
        center: f.properties.centroid as [number, number],
        zoom: Math.max(map.getZoom(), 17),
      });
  }, [selected, ready, fc, mapRef]);

  // map-click picking for a new assessment
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const canvas = map.getCanvas();
    canvas.style.cursor = picking ? "crosshair" : "";
    if (!picking) return;
    const onClick = (e: { lngLat: { lng: number; lat: number } }) =>
      onPick([e.lngLat.lng, e.lngLat.lat]);
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
      fc ? (reviewOnly ? fc.features.filter((f) => f.properties.needs_review) : fc.features) : [],
    [fc, reviewOnly],
  );

  const layers = useMemo(() => {
    const out: (GeoJsonLayer<OpsProps> | ScatterplotLayer<[number, number]>)[] = [
      new GeoJsonLayer<OpsProps>({
        id: "ops-structures",
        data: data as OpsFeature[],
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
          return [...hexRgb(FEMA_HEX[p.damage_level]), Math.round(80 + 170 * (p.confidence ?? 0))];
        },
        getLineColor: (f): RGBA => {
          const p = f.properties;
          if (p.ncr_id === selected) return [0, 0, 0, 255];
          if (labels[p.ncr_id]) return [40, 40, 40, 255];
          if (p.needs_review) return [...ACCENT, 255];
          return [90, 90, 90, 170];
        },
        getLineWidth: (f) =>
          f.properties.ncr_id === selected ? 4 : f.properties.needs_review ? 2 : 0.8,
        updateTriggers: { getLineColor: [selected, labels], getLineWidth: [selected] },
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
    if (pick) {
      out.push(
        new ScatterplotLayer<[number, number]>({
          id: "ops-pick",
          data: [pick],
          getPosition: (d) => d,
          getRadius: 9,
          radiusUnits: "pixels",
          stroked: true,
          filled: false,
          getLineColor: [...ACCENT, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 3,
        }),
      );
    }
    return out;
  }, [data, selected, labels, onSelect, picking, pick]);

  useEffect(() => {
    if (!ready || !mapRef.current) return;
    if (!overlayRef.current) {
      overlayRef.current = new MapboxOverlay({ interleaved: false, layers: [] });
      mapRef.current.addControl(overlayRef.current as unknown as IControl);
    }
    overlayRef.current.setProps({ layers });
  }, [ready, mapRef, layers]);

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
      <div ref={containerRef} className="h-full w-full" aria-label="Operational damage map" />
      {hover && !picking && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="font-medium text-ink">
            {hover.p.damage_level ? FEMA_LABEL[hover.p.damage_level] : "Not assessed"}
            {hover.p.confidence != null && ` · ${(hover.p.confidence * 100).toFixed(0)}%`}
            {hover.p.needs_review && " · review"}
          </div>
          <div className="tnum text-xs text-ink-dim">{hover.p.usng_10m}</div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// right panels
// --------------------------------------------------------------------------- //
function RunSummary({
  fc,
  areaId,
  onDeleted,
}: {
  fc: OpsCollection;
  areaId: string;
  onDeleted: () => void;
}) {
  const p = fc.properties;
  const [busy, setBusy] = useState(false);
  const reasons = p.pair_context.reasons ?? [];
  return (
    <section className="border-b border-line pb-4">
      <h2 className="text-base font-semibold text-ink">{areaTitle(areaId)}</h2>
      <div className="text-sm text-ink-dim">
        {p.event.name} · {p.event.declarations.join(", ") || "provisional event"}
        {p.aoi.county ? ` · ${p.aoi.county} Co.` : ""} · {p.aoi.role} area
      </div>
      <div className="text-xs text-ink-faint">
        assessed {ago(p.generated_utc)} ({new Date(p.generated_utc).toLocaleString()})
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className={btn} onClick={() => openBrief(areaId).catch((e: Error) => toast.error(e.message))}>
          Situation brief
        </button>
        <button
          className={btn}
          disabled={busy}
          title="GeoJSON, CSV with USNG, KML, GeoPackage, File Geodatabase, Survey123 sheet"
          onClick={async () => {
            setBusy(true);
            try {
              await downloadExport(areaId);
            } catch (e) {
              toast.error((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Exporting…" : "GIS export"}
        </button>
        <a className={btn} href={publicUrl(areaId)} download>
          Public summary
        </a>
        {p.aoi.role === "OPS" && (
          <button
            className={`${btn} text-dmg3`}
            onClick={async () => {
              if (!window.confirm(`Delete the assessment "${areaTitle(areaId)}"? Labels are kept.`)) return;
              try {
                await deleteArea(areaId);
                toast.success("Assessment deleted");
                onDeleted();
              } catch (e) {
                toast.error((e as Error).message);
              }
            }}
          >
            Delete
          </button>
        )}
      </div>
      <table className="tnum mt-3 w-full text-sm">
        <caption className="sr-only">Expected structures by damage level</caption>
        <thead>
          <tr className="text-xs text-ink-dim">
            <th className="text-left font-medium">Level</th>
            <th className="text-right font-medium">Expected</th>
            <th className="text-right font-medium">80% range*</th>
          </tr>
        </thead>
        <tbody>
          {FEMA.map((c) => (
            <tr key={c} className="border-t border-line">
              <td className="py-1 text-ink">
                <span
                  className="mr-2 inline-block h-3 w-3 rounded-sm border border-line align-middle"
                  style={{ background: FEMA_HEX[c] }}
                />
                {FEMA_LABEL[c]}
              </td>
              <td className="py-1 text-right font-semibold text-ink">{Math.round(p.expected_counts[c])}</td>
              <td className="py-1 text-right text-ink-dim">{p.expected_counts_80pct?.[c]?.join("–") ?? "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs leading-relaxed text-ink-dim">
        * Conditional on uncalibrated probabilities; real uncertainty is wider.{" "}
        {p.not_assessed.total.toLocaleString()} inventory structures had no
        outline and were not assessed ({p.not_assessed.residential} residential).{" "}
        {p.n_needs_review.toLocaleString()} need review.
      </p>
      {(p.warnings.length > 0 || reasons.length > 0) && (
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-ink">
            Data caveats ({p.warnings.length + reasons.length})
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-dim">
            {p.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
            {reasons.map((r) => (
              <li key={r} className="tnum">
                {r.replace(/_/g, " ").toLowerCase()}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function ImpactPanel({ areaId }: { areaId: string }) {
  const [imp, setImp] = useState<Impact | null | "none">(null);
  useEffect(() => {
    loadImpact(areaId)
      .then(setImp)
      .catch(() => setImp("none"));
  }, [areaId]);
  if (imp === null) return null;
  if (imp === "none")
    return <p className="border-b border-line py-3 text-sm text-ink-dim">No people estimate for this area.</p>;
  const unadjusted = imp.occupancy_adjustment.startsWith("UNADJUSTED");
  return (
    <section className="border-b border-line py-4">
      <h2 className={h2}>People</h2>
      <div className="tnum mt-1 text-base font-semibold text-ink">
        ~{Math.round(imp.expected_displaced.median)} likely displaced{" "}
        <span className="text-sm font-normal text-ink-dim">
          (80% {Math.round(imp.expected_displaced.p10)}–{Math.round(imp.expected_displaced.p90)})
        </span>
      </div>
      <div className="tnum text-sm text-ink">
        + {imp.unassessed_residential?.structures ?? 0} homes not assessed (~
        {Math.round(imp.unassessed_residential?.occupants_nsi ?? 0)} residents)
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink-dim">
        {unadjusted
          ? "Seasonal and vacant homes counted as occupied (pushes this up); unassessed homes excluded (pushes it down). "
          : `${imp.occupancy_adjustment}. `}
        Ranks where to look; not an eligibility determination.
      </p>
      <table className="tnum mt-2 w-full text-sm">
        <thead>
          <tr className="text-xs text-ink-dim">
            <th className="text-left font-medium">Census tract</th>
            <th className="text-right font-medium">Displaced</th>
            <th className="text-right font-medium">SVI</th>
            <th className="text-right font-medium">Need</th>
          </tr>
        </thead>
        <tbody>
          {imp.tracts.slice(0, 6).map((t) => (
            <tr key={t.tract} className="border-t border-line">
              <td className="py-0.5 text-ink" title={t.location ?? ""}>
                {(t.location ?? t.tract).split(";")[0].replace("Census Tract ", "")}
              </td>
              <td className="py-0.5 text-right text-ink">{t.expected_displaced ?? "<5 bldgs"}</td>
              <td className="py-0.5 text-right text-ink-dim">{t.svi_percentile?.toFixed(2) ?? "n/a"}</td>
              <td className="py-0.5 text-right font-semibold text-ink">{t.need_index ?? "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
  return (
    <section className="pt-4">
      <h2 className={h2}>Review queue</h2>
      <p className="mt-1 text-xs text-ink-dim">
        {queue.length.toLocaleString()} open · {labeledCount} labeled · most
        severe and most occupied first. Keys: 0–4 label, x can't tell, j/k
        next/previous, Esc close.
      </p>
      <ul className="mt-2 divide-y divide-line">
        {queue.slice(0, 150).map((p) => (
          <li key={p.ncr_id}>
            <button
              onClick={() => onPick(p.ncr_id)}
              className="flex w-full items-center gap-2 py-1.5 text-left text-sm hover:bg-surface-2"
            >
              <span
                className="h-3 w-3 shrink-0 rounded-sm border border-line"
                style={{ background: p.damage_level ? FEMA_HEX[p.damage_level] : NOT_ASSESSED_HEX }}
              />
              <span className="tnum flex-1 truncate text-ink">{p.usng_10m}</span>
              <span className="tnum text-xs text-ink-dim">
                {(pSevere(p) * 100).toFixed(0)}% ≥Major · {occupantsOf(p)} ppl
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
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
    <figure>
      {src ? (
        <img
          src={src}
          alt={`${kind === "pre" ? "Before" : "After"}-event image of this structure`}
          className="aspect-square w-full rounded-sm bg-surface-2 object-cover"
        />
      ) : (
        <div className="grid aspect-square w-full place-items-center rounded-sm bg-surface-2 text-xs text-ink-dim">
          {failed ? "needs responder token" : "loading…"}
        </div>
      )}
      <figcaption className="text-center text-sm font-medium text-ink">
        {kind === "pre" ? "Before" : "After"}
      </figcaption>
    </figure>
  );
}

function ProbBar({ probs }: { probs: Record<FemaClass, number> }) {
  return (
    <div>
      <div
        className="flex h-4 w-full overflow-hidden rounded-sm border border-line"
        role="img"
        aria-label={FEMA.map((c) => `${FEMA_LABEL[c]} ${(probs[c] * 100).toFixed(0)}%`).join(", ")}
      >
        {FEMA.map((c) => (
          <div key={c} style={{ width: `${probs[c] * 100}%`, background: FEMA_HEX[c] }} />
        ))}
      </div>
      <div className="tnum mt-1 grid grid-cols-5 text-center text-xs text-ink-dim">
        {FEMA.map((c) => (
          <span key={c}>
            {FEMA_LABEL[c].split(" ")[0]}
            <br />
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
  onLabel,
  onClose,
}: {
  areaId: string;
  f: OpsFeature;
  address?: string;
  labeled?: string;
  onLabel: (lab: string) => void;
  onClose: () => void;
}) {
  const p = f.properties;
  const assessed = !!p.damage_level;
  const choice = (sel: boolean) =>
    `rounded-md border px-2 py-2 text-sm hover:bg-surface-2 ${sel ? "border-ink bg-surface-2 font-semibold" : "border-line-strong"}`;
  return (
    <section className="pt-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-ink-dim">Structure</div>
          <div className="tnum text-base font-semibold text-ink">{p.usng_1m}</div>
          {address && <div className="text-sm text-ink">{address}</div>}
          <div className="tnum text-xs text-ink-faint">
            {p.centroid[1].toFixed(5)}, {p.centroid[0].toFixed(5)}
          </div>
        </div>
        <button onClick={onClose} className={btn} aria-label="Close structure">
          Close
        </button>
      </div>

      {assessed && p.damage_probs ? (
        <div className="mt-3">
          <div className="flex items-baseline justify-between">
            <span className="text-lg font-semibold text-ink">
              <span
                className="mr-2 inline-block h-3.5 w-3.5 rounded-sm border border-line align-middle"
                style={{ background: FEMA_HEX[p.damage_level!] }}
              />
              {FEMA_LABEL[p.damage_level!]}
            </span>
            <span className="tnum text-sm text-ink-dim">{(p.confidence! * 100).toFixed(0)}% (uncalibrated)</span>
          </div>
          <div className="mt-2">
            <ProbBar probs={p.damage_probs} />
          </div>
          {p.needs_review && (
            <p className="mt-2 rounded-md border border-accent px-2 py-1 text-sm text-ink">
              <b>Needs review:</b>{" "}
              {p.review_reasons.map((r) => r.replace(/_/g, " ").toLowerCase()).join("; ")}
            </p>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-ink">
          <b>Not assessed.</b> In the structure inventory, but no building
          outline exists, so imagery was not read.
        </p>
      )}

      {assessed && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {(["pre", "post"] as const).map((k) => (
            <Chip key={`${p.ncr_id}-${k}`} areaId={areaId} ncrId={p.ncr_id} kind={k} />
          ))}
        </div>
      )}

      <div className="mt-3">
        <div className="text-sm font-semibold text-ink">
          Record what the imagery shows{" "}
          {labeled && <span className="font-normal text-accent">· labeled {labeled.replace("_", " ")}</span>}
        </div>
        <div className="mt-1.5 grid grid-cols-3 gap-1.5">
          {FEMA.map((c, i) => (
            <button key={c} onClick={() => onLabel(c)} className={choice(labeled === c)}>
              <span className="tnum text-ink-dim">{i}</span> {FEMA_LABEL[c]}
            </button>
          ))}
          <button onClick={() => onLabel("cannot_tell")} className={choice(labeled === "cannot_tell")}>
            <span className="text-ink-dim">x</span> Can't tell
          </button>
        </div>
      </div>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-medium text-ink">Evidence</summary>
        <ul className="mt-1 space-y-1 text-xs">
          {p.evidence.map((e) => (
            <li key={e.id}>
              <b className="tnum text-ink">{e.id}</b>{" "}
              {e.available ? (
                <span className="text-ink-dim">
                  weight {e.weight.toFixed(2)} · {e.status}
                  {e.reasons.length > 0 && (
                    <>
                      {" "}
                      · <span className="tnum">{e.reasons.join(", ")}</span>
                    </>
                  )}
                </span>
              ) : (
                <span className="text-ink-dim">
                  unavailable: {e.unavailable_reason?.replace(/_/g, " ").toLowerCase()}
                </span>
              )}
            </li>
          ))}
        </ul>
      </details>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer font-medium text-ink">Structure and occupants</summary>
        <dl className="tnum mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
          <dt className="text-ink-dim">Use</dt>
          <dd className="text-ink">{p.primary_occupancy ?? p.occupancy ?? "unknown"}</dd>
          <dt className="text-ink-dim">Manufactured home</dt>
          <dd className="text-ink">{p.flags.manufactured_home ? "yes" : "no"}</dd>
          <dt className="text-ink-dim">Occupants (NSI {p.occupants?.period ?? ""})</dt>
          <dd className="text-ink">{p.occupants?.nsi_estimate ?? "n/a"}</dd>
          <dt className="text-ink-dim">Occupants (USA Structures)</dt>
          <dd className="text-ink">
            {p.occupants?.usa_structures_median ?? "n/a"}
            {p.occupants?.usa_structures_ci95?.[0] != null &&
              ` (${p.occupants.usa_structures_ci95[0]}–${p.occupants.usa_structures_ci95[1]})`}
          </dd>
          <dt className="text-ink-dim">Stories</dt>
          <dd className="text-ink">{p.stories ?? "n/a"}</dd>
          <dt className="text-ink-dim">Foundation height</dt>
          <dd className="text-ink">{p.foundation_height_ft != null ? `${p.foundation_height_ft} ft` : "n/a"}</dd>
          <dt className="text-ink-dim">Ground (NAVD88)</dt>
          <dd className="text-ink">
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
      </details>
    </section>
  );
}
