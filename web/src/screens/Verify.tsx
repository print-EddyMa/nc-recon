import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  FEMA,
  FEMA_LABEL,
  loadCapPhotos,
  loadCapThumb,
  loadChip,
  loadOpsAreas,
  loadVerifyStatus,
  nextVerifyTask,
  postJudgment,
  setVerifierName,
  verifierName,
  type CapPhoto,
  type CapPhotos,
  type OpsAreaSummary,
  type VerifyAreaStatus,
  type VerifyTask,
} from "../lib/ops";
import { Kbd, Segmented, Spinner, Swatch } from "../components/ui/kit";

// Groma Verify (docs/truth/README.md). One building at a time, before and
// after imagery only. Deliberately blind: this screen never shows the model's
// level, probabilities or review flag, so verifiers are not anchored by it.

const KEYS: Record<string, string> = { "0": "no_damage", "1": "affected", "2": "minor", "3": "major", "4": "destroyed", x: "cannot_tell" };
const GUIDE: Record<string, string> = {
  no_damage: "Roof and surroundings unchanged.",
  affected: "Cosmetic only: a few shingles, debris in the yard, a damaged shed.",
  minor: "Part of the roof covering gone, a tarp, a tree on the roof without collapse.",
  major: "Part of the roof structure gone, a wall failed, shifted on its foundation.",
  destroyed: "Only the foundation or a debris pile remains, or it is gone.",
  cannot_tell: "Canopy, cloud, shadow or a bad outline. Use it freely.",
};
const h2 = "label";

function Img({ area, id, kind }: { area: string; id: string; kind: "pre" | "post" }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    let live = true;
    loadChip(area, id, kind)
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
  }, [area, id, kind]);
  return (
    <figure className="relative min-w-0">
      {src ? (
        <img src={src} alt={`${kind === "pre" ? "Before" : "After"} the event`} className="aspect-square w-full rounded bg-surface-2 object-cover" />
      ) : (
        <div className="grid aspect-square w-full place-items-center rounded bg-surface-2 text-sm text-ink-dim">
          {failed ? "Image needs responder access" : <Spinner />}
        </div>
      )}
      <figcaption className="absolute left-2 top-2 rounded-sm bg-ink/80 px-2 py-0.5 text-xs font-semibold text-canvas">
        {kind === "pre" ? "Before" : "After"}
      </figcaption>
    </figure>
  );
}

const fmtDay = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function CapThumb({ area, p }: { area: string; p: CapPhoto }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    let live = true;
    loadCapThumb(area, p.key)
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
  }, [area, p.key]);
  const km = p.dist_m >= 1000 ? `${(p.dist_m / 1000).toFixed(1)} km` : `${p.dist_m} m`;
  return (
    <figure className="min-w-0">
      <div className="relative aspect-[3/2] w-full overflow-hidden rounded-md bg-surface-2">
        {src ? (
          <img src={src} alt={`Civil Air Patrol ${p.kind} photo, ${fmtDay(p.date)}`} className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full place-items-center text-sm text-ink-dim">{failed ? "Photo unavailable" : "Loading photo…"}</div>
        )}
        {src && p.x_frac != null && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 w-px border-l border-dashed border-white/80"
            style={{ left: `${Math.min(98, Math.max(2, p.x_frac * 100))}%` }}
          />
        )}
      </div>
      <figcaption className="mt-1 flex justify-between gap-2 text-xs text-ink-dim">
        <span>
          {p.kind === "oblique" ? "Oblique" : "Overhead"} · {fmtDay(p.date)} · {km}
        </span>
        <a href={p.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-accent underline-offset-2 hover:underline">
          Original
        </a>
      </figcaption>
    </figure>
  );
}

function CapStrip({ area, id }: { area: string; id: string }) {
  const [d, setD] = useState<CapPhotos | null>(null);
  useEffect(() => {
    let live = true;
    loadCapPhotos(area, id)
      .then((x) => live && setD(x))
      .catch(() => live && setD({ photos: [], note: "Photos need the responder token", source: "", caveat: "" }));
    return () => {
      live = false;
    };
  }, [area, id]);
  if (!d) return null;
  if (!d.photos.length) return d.note ? <p className="mt-4 text-xs text-ink-dim">Civil Air Patrol photos: {d.note}.</p> : null;
  return (
    <section className="mt-5" aria-label="Civil Air Patrol photos">
      <h2 className={h2}>Civil Air Patrol photos</h2>
      <p className="mt-1 text-xs text-ink-dim">
        Taken days after the event. {d.caveat} The dashed line marks the direction of the building.
      </p>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {d.photos.map((p) => (
          <CapThumb key={p.key} area={area} p={p} />
        ))}
      </div>
    </section>
  );
}

export default function Verify() {
  const [areas, setAreas] = useState<OpsAreaSummary[]>([]);
  const [area, setArea] = useState<string>("");
  const [name, setName] = useState(verifierName());
  const [worker, setWorker] = useState(verifierName());
  const [role, setRole] = useState<"verifier" | "analyst">("verifier");
  const [task, setTask] = useState<VerifyTask | null>(null);
  const [status, setStatus] = useState<VerifyAreaStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const started = useRef(0);

  useEffect(() => {
    loadOpsAreas()
      .then((a) => {
        setAreas(a);
        const first = a.find((x) => x.aoi?.role === "TUNE") ?? a[0];
        if (first?.aoi?.id) setArea((cur) => cur || first.aoi.id);
      })
      .catch(() => toast.error("Could not load areas"));
  }, []);

  const refresh = useCallback(async () => {
    if (!area || !worker) return;
    try {
      const [t, s] = await Promise.all([nextVerifyTask(area, worker, role), loadVerifyStatus(area)]);
      setTask(t);
      setStatus(s);
      started.current = performance.now();
    } catch (e) {
      setTask(null);
      toast.error(e instanceof Error ? e.message : "Could not load a task");
    }
  }, [area, worker, role]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const judge = useCallback(
    async (label: string) => {
      if (!task?.ncr_id || busy) return;
      setBusy(true);
      try {
        const seconds = (performance.now() - started.current) / 1000;
        await postJudgment({ area: task.area, ncr_id: task.ncr_id, label, worker, role, seconds });
        setDone((d) => d + 1);
        toast.success("Saved");
        await refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Not saved");
      } finally {
        setBusy(false);
      }
    },
    [task, busy, worker, role, refresh],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "SELECT") return;
      const lab = KEYS[e.key.toLowerCase()];
      if (lab) {
        e.preventDefault();
        void judge(lab);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [judge]);

  const roleOf = (a: OpsAreaSummary) => a.aoi?.role ?? "";
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="min-w-0">
          <h1 className="text-lg">Verify</h1>
          <p className="mt-1 text-[13px] text-ink-dim">
            Judge one building at a time from its imagery. You never see the model's call.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3 border-b border-line pb-4">
            <label className="text-xs font-medium text-ink-dim">
              Your name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={() => {
                  setVerifierName(name);
                  setWorker(name.trim());
                }}
                placeholder="first name or initials"
                className="field mt-1 w-44"
              />
            </label>
            <label className="text-xs font-medium text-ink-dim">
              Area
              <select value={area} onChange={(e) => setArea(e.target.value)} className="field mt-1 w-56">
                {areas.map((a) => (
                  <option key={a.aoi.id} value={a.aoi.id}>
                    {(a.aoi as { name?: string }).name ?? a.aoi.id} ({roleOf(a) === "TEST" ? "held out" : roleOf(a).toLowerCase()})
                  </option>
                ))}
              </select>
            </label>
            <div className="pb-0.5">
              <Segmented
                label="Role"
                value={role}
                onChange={setRole}
                items={[
                  { id: "verifier", label: "Verifier", title: "Judge buildings blind" },
                  { id: "analyst", label: "Analyst", title: "Settle disagreements between verifiers" },
                ]}
              />
            </div>
            <span className="tnum ml-auto pb-1 font-mono text-xs text-ink-dim">{done} answered this session</span>
          </div>

          {!worker ? (
            <p className="mt-8 text-ink-dim">Enter your name to start. It is stored with each answer so agreement can be measured.</p>
          ) : !task ? (
            <p className="mt-8 flex items-center gap-2 text-ink-dim">
              <Spinner /> Loading…
            </p>
          ) : task.done || !task.ncr_id ? (
            <p className="mt-8 text-ink">
              {role === "analyst"
                ? "No disagreements waiting in this area."
                : "Nothing left for you in this area. Thank you. Pick another area."}
            </p>
          ) : (
            <>
              <div className="mt-5 flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-semibold text-ink">What does the after image show for the outlined building?</p>
                {task.judgments_so_far ? (
                  <span className="tnum font-mono text-xs text-ink-faint">
                    {task.judgments_so_far} of {task.needed} answers so far
                  </span>
                ) : null}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Img key={`${task.ncr_id}-pre`} area={task.area} id={task.ncr_id} kind="pre" />
                <Img key={`${task.ncr_id}-post`} area={task.area} id={task.ncr_id} kind="post" />
              </div>
              <p className="mt-1 text-xs text-ink-dim">
                Before: {task.imagery?.pre ?? "date unknown"} · After: {task.imagery?.post ?? "date unknown"}
              </p>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {[...FEMA, "cannot_tell" as const].map((k, i) => (
                  <button
                    key={k}
                    disabled={busy}
                    onClick={() => void judge(k)}
                    title={GUIDE[k]}
                    className="pressable flex h-11 items-center gap-2 rounded border border-line-strong bg-surface px-3 text-left text-sm font-semibold text-ink hover:border-accent hover:bg-accent-soft disabled:opacity-50"
                  >
                    {k !== "cannot_tell" && <Swatch c={k} />}
                    <span className="flex-1">{k === "cannot_tell" ? "Can't tell" : FEMA_LABEL[k]}</span>
                    <Kbd>{k === "cannot_tell" ? "x" : String(i)}</Kbd>
                  </button>
                ))}
              </div>
              <CapStrip key={`${task.ncr_id}-cap`} area={task.area} id={task.ncr_id} />
            </>
          )}
        </section>

        <aside className="space-y-5 text-sm">
          <div>
            <h2 className={h2}>This area</h2>
            {status && (
              <div
                className="mt-2 flex h-2 overflow-hidden rounded-full bg-surface-2"
                role="img"
                aria-label={`${status.verified} verified, ${status.in_progress} in progress, ${status.escalated} with an analyst, ${status.unverifiable} cannot be verified`}
              >
                {(
                  [
                    [status.verified, "bg-st-ok"],
                    [status.in_progress, "bg-accent"],
                    [status.escalated, "bg-st-warn"],
                    [status.unverifiable, "bg-st-unknown"],
                  ] as [number, string][]
                ).map(([v, c], i) => {
                  const t = status.verified + status.in_progress + status.escalated + status.unverifiable || 1;
                  return v ? <span key={i} className={c} style={{ width: `${(v / t) * 100}%` }} /> : null;
                })}
              </div>
            )}
            {status ? (
              <dl className="tnum mt-2 grid grid-cols-2 gap-y-1 font-mono text-[13px] text-ink">
                <dt className="text-ink-dim">Verified</dt>
                <dd className="text-right">{status.verified}</dd>
                <dt className="text-ink-dim">In progress</dt>
                <dd className="text-right">{status.in_progress}</dd>
                <dt className="text-ink-dim">Sent to an analyst</dt>
                <dd className="text-right">{status.escalated}</dd>
                <dt className="text-ink-dim">Can't be verified</dt>
                <dd className="text-right">{status.unverifiable}</dd>
                <dt className="text-ink-dim">Answers / verifiers</dt>
                <dd className="text-right">
                  {status.judgments} / {status.verifiers}
                </dd>
                <dt className="text-ink-dim">Released as labels</dt>
                <dd className="text-right">{status.released}</dd>
              </dl>
            ) : (
              <p className="mt-2 text-ink-dim">…</p>
            )}
          </div>
          <div>
            <h2 className={h2}>How to judge</h2>
            <ul className="mt-2 space-y-1.5 text-ink">
              {[...FEMA, "cannot_tell"].map((k, i) => (
                <li key={k}>
                  <span className="font-mono text-xs text-ink-dim">{k === "cannot_tell" ? "x" : i}</span>{" "}
                  <b className="font-medium">{k === "cannot_tell" ? "Can't tell" : FEMA_LABEL[k as (typeof FEMA)[number]]}</b>
                  <span className="text-ink-dim">: {GUIDE[k]}</span>
                </li>
              ))}
            </ul>
          </div>
          <p className="text-xs leading-relaxed text-ink-dim">
            Each building goes to three people who cannot see each other's answers or the model's call. Two agreeing
            answers settle it; disagreements go to an analyst. Settled answers become labels only when someone
            releases them, and they make the next assessment better calibrated.
          </p>
        </aside>
      </div>
    </div>
  );
}
