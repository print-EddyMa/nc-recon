import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  loadCatalog,
  serverUp,
  startAssess,
  pollAssess,
  assessCommands,
  inNC,
  type CatalogEvent,
} from "./catalog";

/**
 * Shared "assess an NC area" flow, used by the Assess screen and the ⌘K menu so
 * there is one code path and one source of truth for job state. Progress is
 * surfaced as a toast. `onIngested` receives the pipeline **area slug** of the
 * finished assessment.
 */
export type IngestPhase = "idle" | "running" | "done" | "error";

export interface IngestState {
  phase: IngestPhase;
  step?: string;
  error?: string;
}

/** An AOI to assess: a Maxar catalogue event, plus the exact point to center on
 * (defaults to the event centre when no explicit point is given). */
export interface AssessTarget {
  id: string;
  name: string;
  center: [number, number] | null;
  point?: [number, number] | null; // [lon, lat], an explicit AOI location
  subtitle?: string;
}

const STEP_PCT: Record<string, number> = {
  "fetch imagery": 15,
  "run damage model": 55,
  "cut map tiles": 85,
  "update registry": 95,
  done: 100,
};

// a pipeline run is fetch + infer + tiles + registry; ~2 min is typical, so give
// up polling well after that rather than spinning forever if a job hangs or the
// server reaps it (then /assess/{id} 404s and the poll no-ops).
const MAX_POLL_MS = 12 * 60_000;

export function useAssess(onIngested: (areaSlug: string) => void) {
  const [catalog, setCatalog] = useState<CatalogEvent[]>([]);
  const [online, setOnline] = useState<boolean | null>(null);
  const [jobs, setJobs] = useState<Record<string, IngestState>>({});
  const timers = useRef<Record<string, number>>({});
  const inFlight = useRef<Set<string>>(new Set());
  const onIngestedRef = useRef(onIngested);
  useLayoutEffect(() => {
    onIngestedRef.current = onIngested;
  });

  useEffect(() => {
    loadCatalog()
      .then(setCatalog)
      .catch(() => setCatalog([]));
    serverUp().then(setOnline).catch(() => setOnline(false));
    const running = timers.current;
    return () => {
      for (const id of Object.values(running)) window.clearInterval(id);
    };
  }, []);

  const ingest = useCallback(async (ev: AssessTarget) => {
    const tId = `ingest-${ev.id}`;
    // one assessment per target at a time, blocks a double-click and a
    // re-submit while an earlier poll loop is still running
    if (inFlight.current.has(ev.id)) return;
    inFlight.current.add(ev.id);
    const release = () => {
      inFlight.current.delete(ev.id);
      const t = timers.current[ev.id];
      if (t) {
        window.clearInterval(t);
        delete timers.current[ev.id];
      }
    };

    const pt = ev.point ?? ev.center;
    if (!pt) {
      setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: "no coordinates for this AOI" } }));
      toast.error(`${ev.name}: no coordinates`);
      return release();
    }
    const [lon, lat] = pt;
    if (!inNC(lon, lat)) {
      setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: "AOI is outside North Carolina" } }));
      toast.error("Outside North Carolina", {
        description: "NC Recon only assesses areas within NC.",
      });
      return release();
    }
    setJobs((j) => ({ ...j, [ev.id]: { phase: "running", step: "starting" } }));
    toast.loading(`Assessing ${ev.name}…`, { id: tId, description: "contacting the service" });

    const res = await startAssess({ event: ev.id, lat, lon, name: ev.name, subtitle: ev.subtitle });
    if (!res) {
      setJobs((j) => ({
        ...j,
        [ev.id]: { phase: "error", error: "assessment service not reachable" },
      }));
      toast.error(`${ev.name}: assessment service not reachable`, {
        id: tId,
        description: "Run the commands shown on the Assess screen, or point VITE_API_URL at a service.",
      });
      return release();
    }
    if (res.status === "error") {
      setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: res.error } }));
      toast.error(`${ev.name}: ${res.error ?? "rejected"}`, { id: tId });
      return release();
    }
    if (res.status === "done" || !res.job_id) {
      setJobs((j) => ({ ...j, [ev.id]: { phase: "done" } }));
      toast.success(`${ev.name} is already assessed`, { id: tId });
      const area = res.area;
      release();
      if (area) onIngestedRef.current(area);
      return;
    }

    const jobId = res.job_id;
    const started = Date.now();
    timers.current[ev.id] = window.setInterval(async () => {
      // a later callback can still be queued after we clear the interval
      if (!timers.current[ev.id]) return;
      if (Date.now() - started > MAX_POLL_MS) {
        release();
        setJobs((j) => ({
          ...j,
          [ev.id]: { phase: "error", error: "assessment timed out" },
        }));
        toast.error(`${ev.name}: assessment timed out`, {
          id: tId,
          description: "The job is taking longer than expected. Check the service, then retry.",
        });
        return;
      }
      const st = await pollAssess(jobId);
      if (!st || !timers.current[ev.id]) return;
      if (st.status === "done") {
        const area = st.area;
        release();
        setJobs((j) => ({ ...j, [ev.id]: { phase: "done" } }));
        toast.success(`${ev.name} assessed`, {
          id: tId,
          description: `${Math.round((Date.now() - started) / 1000)}s · opening the damage map`,
        });
        if (area) onIngestedRef.current(area);
      } else if (st.status === "error") {
        release();
        setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: st.error || "pipeline failed" } }));
        toast.error(`${ev.name}: ${st.error || "pipeline failed"}`, {
          id: tId,
          description: "This event may have no clean pre/post imagery pair over the AOI.",
        });
      } else {
        const step = st.step || st.status;
        setJobs((j) => ({ ...j, [ev.id]: { phase: "running", step } }));
        toast.loading(`Assessing ${ev.name}…`, {
          id: tId,
          description: `${step} · ~${STEP_PCT[step] ?? 30}%`,
        });
      }
    }, 2000);
  }, []);

  /** For the "no service" case, copyable commands. */
  const commandsFor = useCallback(
    (ev: { id: string; name: string; center: [number, number] | null; point?: [number, number] | null }) =>
      assessCommands({ id: ev.id, name: ev.name, center: ev.point ?? ev.center }),
    [],
  );

  return { catalog, online, jobs, ingest, commandsFor };
}
