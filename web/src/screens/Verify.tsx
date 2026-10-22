import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  FEMA,
  FEMA_LABEL,
  loadChip,
  loadOpsAreas,
  loadVerifyStatus,
  nextVerifyTask,
  postJudgment,
  setVerifierName,
  verifierName,
  type OpsAreaSummary,
  type VerifyAreaStatus,
  type VerifyTask,
} from "../lib/ops";

// NC Recon Verify (docs/truth/README.md). One building at a time, before and
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
const h2 = "text-sm font-semibold uppercase tracking-wide text-ink-dim";

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
    <figure className="min-w-0">
      {src ? (
        <img src={src} alt={`${kind === "pre" ? "Before" : "After"} the event`} className="aspect-square w-full rounded-md bg-surface-2 object-cover" />
      ) : (
        <div className="grid aspect-square w-full place-items-center rounded-md bg-surface-2 text-sm text-ink-dim">
          {failed ? "Image needs the responder token" : "Loading…"}
        </div>
      )}
      <figcaption className="mt-1 text-center text-sm font-medium text-ink">{kind === "pre" ? "Before" : "After"}</figcaption>
    </figure>
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
      <div className="mx-auto grid max-w-6xl gap-6 p-4 lg:grid-cols-[1fr_20rem]">
        <section className="min-w-0">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm text-ink-dim">
              Your name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={() => {
                  setVerifierName(name);
                  setWorker(name.trim());
                }}
                placeholder="first name or initials"
                className="mt-1 block w-44 rounded-md border border-line bg-surface px-2 py-1 text-ink"
              />
            </label>
            <label className="text-sm text-ink-dim">
              Area
              <select
                value={area}
                onChange={(e) => setArea(e.target.value)}
                className="mt-1 block rounded-md border border-line bg-surface px-2 py-1 text-ink"
              >
                {areas.map((a) => (
                  <option key={a.aoi.id} value={a.aoi.id}>
                    {(a.aoi as { name?: string }).name ?? a.aoi.id} ({roleOf(a) === "TEST" ? "held out" : roleOf(a).toLowerCase()})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 pb-1 text-sm text-ink-dim">
              <input type="checkbox" checked={role === "analyst"} onChange={(e) => setRole(e.target.checked ? "analyst" : "verifier")} />
              Analyst (settles disagreements)
            </label>
          </div>

          {!worker ? (
            <p className="mt-8 text-ink-dim">Enter your name to start. It is stored with each answer so agreement can be measured.</p>
          ) : !task ? (
            <p className="mt-8 text-ink-dim">Loading…</p>
          ) : task.done || !task.ncr_id ? (
            <p className="mt-8 text-ink">
              {role === "analyst"
                ? "No disagreements waiting in this area."
                : "Nothing left for you in this area. Thank you. Pick another area."}
            </p>
          ) : (
            <>
              <p className="mt-5 text-sm text-ink-dim">
                What does the after image show for the outlined building? Judge the imagery only.
                {task.judgments_so_far ? ` ${task.judgments_so_far} of ${task.needed} answers so far.` : ""}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Img key={`${task.ncr_id}-pre`} area={task.area} id={task.ncr_id} kind="pre" />
                <Img key={`${task.ncr_id}-post`} area={task.area} id={task.ncr_id} kind="post" />
              </div>
              <p className="mt-1 text-xs text-ink-dim">
                Before: {task.imagery?.pre ?? "date unknown"} · After: {task.imagery?.post ?? "date unknown"}
              </p>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                {[...FEMA, "cannot_tell" as const].map((k, i) => (
                  <button
                    key={k}
                    disabled={busy}
                    onClick={() => void judge(k)}
                    title={GUIDE[k]}
                    className="rounded-md border border-line bg-surface px-2 py-2 text-left text-sm text-ink hover:border-accent disabled:opacity-50"
                  >
                    <span className="mr-1 font-mono text-xs text-ink-dim">{k === "cannot_tell" ? "x" : i}</span>
                    {k === "cannot_tell" ? "Can't tell" : FEMA_LABEL[k]}
                  </button>
                ))}
              </div>
            </>
          )}
        </section>

        <aside className="space-y-5 text-sm">
          <div>
            <h2 className={h2}>This area</h2>
            {status ? (
              <dl className="tnum mt-2 grid grid-cols-2 gap-y-1 text-ink">
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
            <p className="mt-2 text-xs text-ink-dim">Your answers this session: {done}</p>
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
