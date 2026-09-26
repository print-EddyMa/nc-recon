import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { toast } from "sonner";
import { useMapLibre, type IControl } from "../lib/useMapLibre";
import {
  DISCLAIMER,
  FEMA,
  FEMA_HEX,
  FEMA_LABEL,
  NOT_ASSESSED_HEX,
  chipUrl,
  downloadExport,
  fmtAge,
  labelerName,
  loadHealth,
  loadImpact,
  publicUrl,
  briefUrl,
  loadLabels,
  loadOpsArea,
  loadOpsAreas,
  loadReport,
  loadResponder,
  occupantsOf,
  postLabel,
  pSevere,
  responderToken,
  reviewPriority,
  setLabelerName,
  setResponderToken,
  type FemaClass,
  type HealthRow,
  type Impact,
  type OpsAreaSummary,
  type OpsCollection,
  type OpsFeature,
  type OpsProps,
} from "../lib/ops";

type RGBA = [number, number, number, number];
const hexRgb = (h: string): [number, number, number] => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];
const ACCENT: [number, number, number] = [74, 128, 246];

// --------------------------------------------------------------------------- //
export default function Ops({
  areaId,
  onPickArea,
}: {
  areaId: string | null;
  onPickArea: (id: string | null) => void;
}) {
  const [areas, setAreas] = useState<OpsAreaSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [fc, setFc] = useState<OpsCollection | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [addresses, setAddresses] = useState<Record<string, string>>({});

  useEffect(() => {
    loadOpsAreas()
      .then(setAreas)
      .catch((e: Error) => setErr(e.message));
  }, []);

  // App remounts this screen per area (key={areaId}), so state starts clean
  useEffect(() => {
    if (!areaId) return;
    let live = true;
    loadOpsArea(areaId)
      .then((d) => live && setFc(d))
      .catch((e: Error) => live && setErr(e.message));
    // responder-only extras: fail quietly (public viewers just don't see them)
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

  const sel = selected ? byId.get(selected) ?? null : null;

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
        toast.success(`Labeled ${lab.replace("_", " ")} (${r.aoi_role} area)`);
        // advance to the next building in the queue
        const next = queue.find((q) => q.ncr_id !== p.ncr_id);
        if (next) setSelected(next.ncr_id);
      } catch (e) {
        toast.error((e as Error).message);
      }
    },
    [areaId, queue],
  );

  // keyboard labeling: 0-4 = class, x = cannot tell, j/k = next/prev in queue
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!sel || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
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
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sel, queue, label]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        role="note"
        className="shrink-0 border-b border-line bg-dmg1/10 px-4 py-1.5 text-center text-xs text-ink"
      >
        {DISCLAIMER}
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[300px_1fr_360px]">
        <aside className="min-h-0 overflow-y-auto border-r border-line p-3">
          <AreaList areas={areas} err={err} areaId={areaId} onPick={onPickArea} />
          <AccuracyPanel />
          <CollectionBoard />
          <ResponderAccess />
        </aside>
        <main className="relative min-h-[50vh]">
          {fc ? (
            <OpsMap
              fc={fc}
              selected={selected}
              reviewOnly={reviewOnly}
              labels={labels}
              onSelect={setSelected}
            />
          ) : (
            <div className="grid h-full place-items-center p-6 text-sm text-ink-dim">
              {areaId ? "Loading assessment…" : "Pick an assessed area on the left."}
            </div>
          )}
          {fc && (
            <div className="absolute left-3 top-3 flex flex-col gap-2">
              <Legend />
              <label className="panel flex items-center gap-2 px-2.5 py-1.5 text-xs">
                <input
                  type="checkbox"
                  checked={reviewOnly}
                  onChange={(e) => setReviewOnly(e.target.checked)}
                />
                Needs review only
              </label>
            </div>
          )}
        </main>
        <aside className="min-h-0 overflow-y-auto border-l border-line p-3">
          {fc && <RunSummary fc={fc} areaId={areaId!} />}
          {fc && <ImpactPanel areaId={areaId!} />}
          {sel ? (
            <StructureCard
              areaId={areaId!}
              f={sel}
              address={addresses[sel.properties.ncr_id]}
              labeled={labels[sel.properties.ncr_id]}
              onLabel={(lab) => void label(sel.properties, lab)}
              onClose={() => setSelected(null)}
            />
          ) : (
            fc && (
              <ReviewList
                queue={queue}
                labeledCount={Object.keys(labels).length}
                onPick={setSelected}
              />
            )
          )}
        </aside>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
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
  return (
    <section className="mb-4">
      <h2 className="section-title">Assessed areas</h2>
      {err && !areas && (
        <p className="mt-2 text-xs text-dmg3">
          Ops service unreachable ({err}). Start <code>server.py</code>.
        </p>
      )}
      {!areas && !err && <div className="skel mt-2 h-16" />}
      <ul className="mt-2 space-y-1.5">
        {areas?.map((a) => {
          const sev =
            (a.expected_counts.major ?? 0) + (a.expected_counts.destroyed ?? 0);
          const lo =
            (a.expected_counts_80pct?.major?.[0] ?? 0) +
            (a.expected_counts_80pct?.destroyed?.[0] ?? 0);
          const hi =
            (a.expected_counts_80pct?.major?.[1] ?? 0) +
            (a.expected_counts_80pct?.destroyed?.[1] ?? 0);
          return (
            <li key={a.id}>
              <button
                onClick={() => onPick(a.id)}
                className={`pressable w-full rounded-md border px-2.5 py-2 text-left ${
                  a.id === areaId ? "border-accent bg-accent/5" : "border-line hover:bg-surface-2"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-ink">
                    {a.id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                  <span
                    className={`rounded-sm px-1.5 py-0.5 text-2xs ${
                      a.aoi.role === "TEST" ? "bg-accent/15 text-accent" : "bg-surface-2 text-ink-dim"
                    }`}
                    title={
                      a.aoi.role === "TEST"
                        ? "Held-out area: never used to tune thresholds"
                        : "Tuning area: thresholds and calibration may be fit here"
                    }
                  >
                    {a.aoi.role}
                  </span>
                </div>
                <div className="mt-0.5 text-2xs text-ink-dim">
                  {a.aoi.county} Co. · {a.n_structures.toLocaleString()} structures ·{" "}
                  {a.n_needs_review.toLocaleString()} to review
                </div>
                <div className="tnum mt-0.5 text-2xs text-ink">
                  ≥ Major (expected): {Math.round(sev)}{" "}
                  <span className="text-ink-faint">
                    (80% {lo}–{hi})
                  </span>
                </div>
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
    loadReport().then(setRep).catch(() => setRep({ status: "UNAVAILABLE" }));
  }, []);
  const status = rep?.status as string | undefined;
  const roles = (rep?.roles ?? {}) as Record<
    string,
    { all: { n: number; macro_f1: number | null; destroyed_recall: number | null; ece?: number | null } }
  >;
  return (
    <section className="mb-4">
      <h2 className="section-title">Accuracy</h2>
      {!rep && <div className="skel mt-2 h-10" />}
      {rep && status !== "OK" && (
        <p className="mt-2 text-xs leading-relaxed text-ink-dim">
          <span className="font-medium text-dmg3">Not yet validated.</span>{" "}
          No ground-truth labels are loaded, so no accuracy figure is shown. Class
          probabilities come from provisional settings. Label buildings in the
          review queue to build the held-out test set.
        </p>
      )}
      {rep && status === "OK" &&
        Object.entries(roles).map(([role, r]) => (
          <div key={role} className="mt-2 text-xs">
            <div className="text-ink-dim">
              {role} areas · n = {r.all.n}
              {role === "TUNE" && " (fit here: optimistic)"}
            </div>
            <div className="tnum text-ink">
              macro-F1 {r.all.macro_f1?.toFixed(2) ?? "n/a"} · Destroyed recall{" "}
              {r.all.destroyed_recall?.toFixed(2) ?? "n/a"} · ECE{" "}
              {r.all.ece?.toFixed(2) ?? "n/a"}
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

function CollectionBoard() {
  const [h, setH] = useState<{ checked_utc: string; sources: HealthRow[] } | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    loadHealth().then(setH).catch(() => setErr(true));
  }, []);
  return (
    <section className="mb-4">
      <h2 className="section-title">Collection status</h2>
      {err && <p className="mt-2 text-xs text-ink-dim">Health check unavailable.</p>}
      {!h && !err && <div className="skel mt-2 h-24" />}
      <ul className="mt-2 space-y-1">
        {h?.sources.map((s) => (
          <li key={s.source} className="flex items-center gap-2 text-xs" title={s.detail}>
            <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[s.status]}`} />
            <span className="flex-1 truncate text-ink">{s.source.replace(/_/g, " ")}</span>
            <span className="tnum text-2xs text-ink-faint">
              {s.status === "ok" || s.status === "stale" ? fmtAge(s.data_age_s) || `${s.latency_ms} ms` : s.status}
            </span>
          </li>
        ))}
      </ul>
      {h && (
        <p className="mt-1 text-2xs text-ink-faint">
          checked {new Date(h.checked_utc).toLocaleString()}
        </p>
      )}
    </section>
  );
}

function ResponderAccess() {
  const [tok, setTok] = useState(responderToken());
  const [who, setWho] = useState(labelerName());
  return (
    <section className="mb-4">
      <h2 className="section-title">Responder access</h2>
      <p className="mt-1 text-2xs leading-relaxed text-ink-dim">
        Addresses, labels and building-level exports need the service token.
        Stored only in this browser.
      </p>
      <input
        type="password"
        value={tok}
        placeholder="Service token"
        onChange={(e) => setTok(e.target.value)}
        onBlur={() => setResponderToken(tok)}
        className="mt-1.5 w-full rounded-md border border-line bg-surface px-2 py-1 text-xs"
      />
      <input
        value={who}
        placeholder="Labeler name / initials"
        onChange={(e) => setWho(e.target.value)}
        onBlur={() => setLabelerName(who)}
        className="mt-1.5 w-full rounded-md border border-line bg-surface px-2 py-1 text-xs"
      />
    </section>
  );
}

function Legend() {
  return (
    <div className="panel px-2.5 py-2 text-2xs">
      <div className="mb-1 text-ink-dim">FEMA damage level (most likely)</div>
      {FEMA.map((c) => (
        <div key={c} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: FEMA_HEX[c] }} />
          <span className="text-ink">{FEMA_LABEL[c]}</span>
        </div>
      ))}
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: NOT_ASSESSED_HEX }} />
        <span className="text-ink">Not assessed (no footprint)</span>
      </div>
      <div className="mt-1 flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-[2px] border-2" style={{ borderColor: `rgb(${ACCENT.join(",")})` }} />
        <span className="text-ink">Needs human review</span>
      </div>
      <div className="mt-1 text-ink-faint">Fill opacity = confidence</div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
function OpsMap({
  fc,
  selected,
  reviewOnly,
  labels,
  onSelect,
}: {
  fc: OpsCollection;
  selected: string | null;
  reviewOnly: boolean;
  labels: Record<string, string>;
  onSelect: (id: string | null) => void;
}) {
  const center = useMemo<[number, number]>(() => {
    const f = fc.features[0];
    return f ? (f.properties.centroid as [number, number]) : [-82.2, 35.6];
  }, [fc]);
  const { containerRef, mapRef, ready } = useMapLibre({ center, zoom: 15, pitch: 0 });
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; p: OpsProps } | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !fc.features.length) return;
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    for (const f of fc.features) {
      const [lon, lat] = f.properties.centroid;
      w = Math.min(w, lon); e = Math.max(e, lon); s = Math.min(s, lat); n = Math.max(n, lat);
    }
    map.fitBounds([[w, s], [e, n]], { padding: 40, duration: 0 });
  }, [ready, fc, mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !selected) return;
    const f = fc.features.find((x) => x.properties.ncr_id === selected);
    if (f) map.easeTo({ center: f.properties.centroid as [number, number], zoom: Math.max(map.getZoom(), 17), duration: 500 });
  }, [selected, ready, fc, mapRef]);

  const data = useMemo(
    () => (reviewOnly ? fc.features.filter((f) => f.properties.needs_review) : fc.features),
    [fc, reviewOnly],
  );

  const layers = useMemo(
    () => [
      new GeoJsonLayer<OpsProps>({
        id: "ops-structures",
        data: data as OpsFeature[],
        pickable: true,
        stroked: true,
        filled: true,
        pointType: "circle",
        getPointRadius: 4,
        pointRadiusUnits: "pixels",
        lineWidthUnits: "pixels",
        getFillColor: (f): RGBA => {
          const p = f.properties;
          if (!p.damage_level) return [...hexRgb(NOT_ASSESSED_HEX), 200];
          // uncertainty through transparency, never colour alone
          const a = Math.round(70 + 170 * (p.confidence ?? 0));
          return [...hexRgb(FEMA_HEX[p.damage_level]), a];
        },
        getLineColor: (f): RGBA => {
          const p = f.properties;
          if (p.ncr_id === selected) return [255, 255, 255, 255];
          if (labels[p.ncr_id]) return [40, 40, 40, 255];
          if (p.needs_review) return [...ACCENT, 255];
          return [80, 80, 80, 160];
        },
        getLineWidth: (f) =>
          f.properties.ncr_id === selected ? 3 : f.properties.needs_review ? 1.8 : 0.6,
        updateTriggers: {
          getLineColor: [selected, labels],
          getLineWidth: [selected],
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
    ],
    [data, selected, labels, onSelect],
  );

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
      {hover && (
        <div
          className="panel pointer-events-none absolute z-10 px-2 py-1 text-2xs"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium text-ink">
            {hover.p.damage_level ? FEMA_LABEL[hover.p.damage_level] : "Not assessed"}
            {hover.p.confidence != null && ` · ${(hover.p.confidence * 100).toFixed(0)}%`}
          </div>
          <div className="tnum text-ink-dim">{hover.p.usng_10m}</div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
function RunSummary({ fc, areaId }: { fc: OpsCollection; areaId: string }) {
  const p = fc.properties;
  const [busy, setBusy] = useState(false);
  return (
    <section className="mb-3 border-b border-line pb-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="section-title">{p.event.name}</h2>
          <div className="text-2xs text-ink-dim">
            {p.event.declarations.join(", ")} · incident began {p.event.incident_begin} ·{" "}
            {p.aoi.county} Co. · {p.aoi.role} area
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
        <a
          href={briefUrl(areaId)}
          target="_blank"
          rel="noreferrer"
          className="pressable rounded-md border border-line px-2 py-1 text-2xs text-ink hover:bg-surface-2"
          title="One-page situation brief (printable; no addresses)"
        >
          Brief
        </a>
        <button
          disabled={busy}
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
          className="pressable shrink-0 rounded-md border border-line px-2 py-1 text-2xs text-ink hover:bg-surface-2"
          title="GeoJSON, CSV (USNG), KML, GeoPackage, File Geodatabase, Survey123 sheet + provenance"
        >
          {busy ? "Exporting…" : "Export"}
        </button>
        </div>
      </div>
      <table className="tnum mt-2 w-full text-2xs">
        <thead>
          <tr className="text-ink-faint">
            <th className="text-left font-normal">Level</th>
            <th className="text-right font-normal">Expected</th>
            <th className="text-right font-normal">80% range</th>
          </tr>
        </thead>
        <tbody>
          {FEMA.map((c) => (
            <tr key={c}>
              <td className="flex items-center gap-1.5 text-ink">
                <span className="h-2 w-2 rounded-[2px]" style={{ background: FEMA_HEX[c] }} />
                {FEMA_LABEL[c]}
              </td>
              <td className="text-right text-ink">{Math.round(p.expected_counts[c])}</td>
              <td className="text-right text-ink-dim">
                {p.expected_counts_80pct?.[c]?.join("–") ?? "n/a"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1.5 text-2xs text-ink-dim">
        {p.not_assessed.total.toLocaleString()} structures in the inventory have no
        footprint and were not assessed ({p.not_assessed.residential} residential).
      </p>
      {p.warnings.length > 0 && (
        <details className="mt-1.5 text-2xs text-ink-dim">
          <summary className="cursor-pointer text-ink">Data caveats ({p.warnings.length})</summary>
          <ul className="mt-1 list-disc pl-4">
            {p.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
            {p.pair_context.reasons.map((r) => (
              <li key={r} className="tnum">{r}</li>
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
    loadImpact(areaId).then(setImp).catch(() => setImp("none"));
  }, [areaId]);
  if (imp === null) return null;
  if (imp === "none")
    return (
      <p className="mb-3 text-2xs text-ink-dim">
        No people-impact run yet (<code>run.py ops-impact --area {areaId}</code>).
      </p>
    );
  const unadjusted = imp.occupancy_adjustment.startsWith("UNADJUSTED");
  return (
    <section className="mb-3 border-b border-line pb-3">
      <h2 className="section-title">People</h2>
      <div className="tnum mt-1 text-sm text-ink">
        ~{Math.round(imp.expected_displaced.median)} people likely displaced{" "}
        <span className="text-xs text-ink-dim">
          (80% {Math.round(imp.expected_displaced.p10)}–{Math.round(imp.expected_displaced.p90)})
        </span>
      </div>
      <p className="mt-1 text-2xs leading-relaxed text-ink-dim">
        {imp.residential_structures_assessed.toLocaleString()} residential structures.{" "}
        {unadjusted
          ? "Upper bound: seasonal and vacant homes are counted as occupied (no Census API key configured)."
          : imp.occupancy_adjustment + "."}{" "}
        Prioritization aid, not an eligibility determination.
      </p>
      <table className="tnum mt-1.5 w-full text-2xs">
        <thead>
          <tr className="text-ink-faint">
            <th className="text-left font-normal">Tract</th>
            <th className="text-right font-normal">Displaced</th>
            <th className="text-right font-normal">SVI</th>
            <th className="text-right font-normal">Need</th>
          </tr>
        </thead>
        <tbody>
          {imp.tracts.slice(0, 6).map((t) => (
            <tr key={t.tract}>
              <td className="text-ink" title={t.location ?? ""}>{t.tract.slice(5)}</td>
              <td className="text-right text-ink">{t.expected_displaced}</td>
              <td className="text-right text-ink-dim">{t.svi_percentile?.toFixed(2) ?? "n/a"}</td>
              <td className="text-right text-ink">{t.need_index ?? "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <a href={publicUrl(areaId)} className="mt-1.5 inline-block text-2xs text-accent underline" download>
        Public tract summary (GeoJSON, no addresses)
      </a>
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
    <section>
      <h2 className="section-title">Review queue</h2>
      <p className="mt-1 text-2xs text-ink-dim">
        {queue.length.toLocaleString()} open · {labeledCount} labeled. Ordered by
        P(≥ Major) × expected occupants. Keys: 0–4 label, x cannot tell, j/k next/prev.
      </p>
      <ul className="mt-2 space-y-1">
        {queue.slice(0, 200).map((p) => (
          <li key={p.ncr_id}>
            <button
              onClick={() => onPick(p.ncr_id)}
              className="pressable flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs hover:bg-surface-2"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-[2px]"
                style={{ background: p.damage_level ? FEMA_HEX[p.damage_level] : NOT_ASSESSED_HEX }}
              />
              <span className="tnum flex-1 truncate text-ink">{p.usng_10m}</span>
              <span className="tnum text-2xs text-ink-dim">
                P(≥Maj) {(pSevere(p) * 100).toFixed(0)}% · {occupantsOf(p)} ppl
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ProbBar({ probs }: { probs: Record<FemaClass, number> }) {
  return (
    <div className="flex h-3 w-full overflow-hidden rounded-sm" role="img"
      aria-label={FEMA.map((c) => `${FEMA_LABEL[c]} ${(probs[c] * 100).toFixed(0)}%`).join(", ")}>
      {FEMA.map((c) => (
        <div key={c} style={{ width: `${probs[c] * 100}%`, background: FEMA_HEX[c] }} />
      ))}
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
  return (
    <section className="panel px-3 py-3">
      <div className="flex items-start justify-between">
        <div>
          <div className="cap">Structure</div>
          <div className="tnum text-sm text-ink">{p.usng_1m}</div>
          <div className="tnum text-2xs text-ink-faint">{p.ncr_id}</div>
          {address && <div className="mt-0.5 text-xs text-ink">{address}</div>}
        </div>
        <button onClick={onClose} aria-label="Close" className="pressable -m-1 h-6 w-6 rounded-md text-ink-faint hover:text-ink">
          ×
        </button>
      </div>

      {assessed && p.damage_probs ? (
        <>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-sm font-medium" style={{ color: FEMA_HEX[p.damage_level!] }}>
              {FEMA_LABEL[p.damage_level!]}
            </span>
            <span className="tnum text-xs text-ink-dim">
              {(p.confidence! * 100).toFixed(0)}% (uncalibrated until labels exist)
            </span>
          </div>
          <div className="mt-1.5">
            <ProbBar probs={p.damage_probs} />
          </div>
          {p.needs_review && (
            <div className="mt-1.5 text-2xs text-accent">
              Needs review: {p.review_reasons.join(", ")}
            </div>
          )}
        </>
      ) : (
        <p className="mt-2 text-xs text-ink-dim">
          Not assessed: this structure is in the USACE inventory but no footprint
          source has it, so imagery was not read.
        </p>
      )}

      {assessed && (
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          {(["pre", "post"] as const).map((k) => (
            <figure key={k}>
              <img
                src={chipUrl(areaId, p.ncr_id, k)}
                alt={`${k}-event image of this structure`}
                className="aspect-square w-full rounded-sm bg-surface-2 object-cover"
                crossOrigin="anonymous"
              />
              <figcaption className="text-center text-2xs text-ink-faint">{k === "pre" ? "Before" : "After"}</figcaption>
            </figure>
          ))}
        </div>
      )}

      <div className="mt-2.5">
        <div className="cap">Record ground truth {labeled && <span className="text-accent">· labeled {labeled.replace("_", " ")}</span>}</div>
        <div className="mt-1 grid grid-cols-3 gap-1">
          {FEMA.map((c, i) => (
            <button
              key={c}
              onClick={() => onLabel(c)}
              className={`pressable rounded-md border px-1.5 py-1 text-2xs ${labeled === c ? "border-ink" : "border-line"} hover:bg-surface-2`}
            >
              <span className="tnum text-ink-faint">{i}</span> {FEMA_LABEL[c]}
            </button>
          ))}
          <button
            onClick={() => onLabel("cannot_tell")}
            className="pressable rounded-md border border-line px-1.5 py-1 text-2xs hover:bg-surface-2"
          >
            <span className="text-ink-faint">x</span> Can't tell
          </button>
        </div>
        <p className="mt-1 text-2xs text-ink-faint">
          Label only what the imagery shows (docs/ops/LABELING_PROTOCOL.md).
        </p>
      </div>

      <details className="mt-2.5 text-xs" open>
        <summary className="cursor-pointer text-ink">Evidence</summary>
        <ul className="mt-1 space-y-1">
          {p.evidence.map((e) => (
            <li key={e.id} className="text-2xs">
              <span className="tnum font-medium text-ink">{e.id}</span>{" "}
              {e.available ? (
                <span className="text-ink-dim">
                  weight {e.weight.toFixed(2)} · {e.status}
                  {e.reasons.length > 0 && <> · <span className="tnum">{e.reasons.join(", ")}</span></>}
                </span>
              ) : (
                <span className="text-ink-faint">unavailable: {e.unavailable_reason}</span>
              )}
            </li>
          ))}
        </ul>
      </details>

      <details className="mt-1.5 text-xs">
        <summary className="cursor-pointer text-ink">Structure & people</summary>
        <dl className="tnum mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-2xs">
          <dt className="text-ink-faint">Occupancy</dt>
          <dd className="text-ink">{p.primary_occupancy ?? p.occupancy ?? "unknown"}</dd>
          <dt className="text-ink-faint">Manufactured</dt>
          <dd className="text-ink">{p.flags.manufactured_home ? "yes" : "no"}</dd>
          <dt className="text-ink-faint">Occupants (NSI {p.occupants?.period ?? ""})</dt>
          <dd className="text-ink">{p.occupants?.nsi_estimate ?? "n/a"}</dd>
          <dt className="text-ink-faint">Occupants (USA Str.)</dt>
          <dd className="text-ink">
            {p.occupants?.usa_structures_median ?? "n/a"}
            {p.occupants?.usa_structures_ci95?.[0] != null &&
              ` (${p.occupants.usa_structures_ci95[0]}–${p.occupants.usa_structures_ci95[1]})`}
          </dd>
          <dt className="text-ink-faint">Stories</dt>
          <dd className="text-ink">{p.stories ?? "n/a"}</dd>
          <dt className="text-ink-faint">Foundation ht</dt>
          <dd className="text-ink">{p.foundation_height_ft != null ? `${p.foundation_height_ft} ft` : "n/a"}</dd>
          <dt className="text-ink-faint">Ground (NAVD88)</dt>
          <dd className="text-ink">{p.ground_elev_m_navd88 != null ? `${p.ground_elev_m_navd88.toFixed(1)} m` : "n/a"}</dd>
          <dt className="text-ink-faint">Flood zone</dt>
          <dd className="text-ink">{p.flood_zone ?? "n/a"}</dd>
          <dt className="text-ink-faint">Footprint</dt>
          <dd className="text-ink">{p.footprint_source ?? "none"}{p.footprint_image_date ? ` (${p.footprint_image_date})` : ""}</dd>
        </dl>
      </details>
      <details className="mt-1.5 text-xs">
        <summary className="cursor-pointer text-ink">All reason codes</summary>
        <p className="tnum mt-1 break-words text-2xs text-ink-dim">{p.reason_codes.join(" · ")}</p>
      </details>
    </section>
  );
}
