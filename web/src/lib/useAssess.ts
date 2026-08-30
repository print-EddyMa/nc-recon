import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  loadCatalog,
  serverUp,
  startAssess,
  pollAssess,
  assessCommands,
  type CatalogEvent,
} from "./catalog";

/**
 * Shared "ingest a Maxar catalogue event" flow, used by the top-bar event
 * picker, the Live Monitor's Assess panel and the ⌘K menu so there is one code
 * path and one source of truth for job state. Progress is surfaced as a toast.
 */
export type IngestPhase = "idle" | "running" | "done" | "error";

export interface IngestState {
  phase: IngestPhase;
  step?: string;
  error?: string;
}

const STEP_PCT: Record<string, number> = {
  "fetch imagery": 15,
  "run damage model": 55,
  "cut map tiles": 85,
  "update registry": 95,
  done: 100,
};

export function useAssess(onIngested: (eventId: string) => void) {
  const [catalog, setCatalog] = useState<CatalogEvent[]>([]);
  const [online, setOnline] = useState<boolean | null>(null);
  const [jobs, setJobs] = useState<Record<string, IngestState>>({});
  const timers = useRef<Record<string, number>>({});

  useEffect(() => {
    loadCatalog().then(setCatalog);
    serverUp().then(setOnline);
    const running = timers.current;
    return () => {
      for (const id of Object.values(running)) window.clearInterval(id);
    };
  }, []);

  const ingest = useCallback(
    async (ev: { id: string; name: string; center: [number, number] | null }) => {
      const tId = `ingest-${ev.id}`;
      if (!ev.center) {
        setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: "no coordinates for this event" } }));
        toast.error(`${ev.name}: no coordinates in the catalogue`);
        return;
      }
      setJobs((j) => ({ ...j, [ev.id]: { phase: "running", step: "starting" } }));
      toast.loading(`Ingesting ${ev.name}…`, { id: tId, description: "contacting pipeline" });

      const res = await startAssess({
        event: ev.id,
        lat: ev.center[1],
        lon: ev.center[0],
        name: ev.name,
      });
      if (!res) {
        setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: "pipeline server not reachable" } }));
        toast.error(`${ev.name}: pipeline server not reachable`, {
          id: tId,
          description: "Start it with `python server.py`, or run the commands manually.",
        });
        return;
      }
      if (res.status === "done" || !res.job_id) {
        setJobs((j) => ({ ...j, [ev.id]: { phase: "done" } }));
        toast.success(`${ev.name} is already assessed`, { id: tId });
        onIngested(ev.id);
        return;
      }

      const jobId = res.job_id;
      const started = Date.now();
      timers.current[ev.id] = window.setInterval(async () => {
        const st = await pollAssess(jobId);
        if (!st) return;
        if (st.status === "done") {
          window.clearInterval(timers.current[ev.id]);
          setJobs((j) => ({ ...j, [ev.id]: { phase: "done" } }));
          toast.success(`${ev.name} assessed`, {
            id: tId,
            description: `${Math.round((Date.now() - started) / 1000)}s · opening the damage map`,
          });
          onIngested(ev.id);
        } else if (st.status === "error") {
          window.clearInterval(timers.current[ev.id]);
          setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: st.error || "pipeline failed" } }));
          toast.error(`${ev.name}: ${st.error || "pipeline failed"}`, {
            id: tId,
            description: "This event may have no clean pre/post imagery pair.",
          });
        } else {
          const step = st.step || st.status;
          setJobs((j) => ({ ...j, [ev.id]: { phase: "running", step } }));
          toast.loading(`Ingesting ${ev.name}…`, {
            id: tId,
            description: `${step} · ~${STEP_PCT[step] ?? 30}%`,
          });
        }
      }, 2000);
    },
    [onIngested],
  );

  /** For the "no server" case — copyable commands. */
  const commandsFor = useCallback(
    (ev: { id: string; name: string; center: [number, number] | null }) => assessCommands(ev),
    [],
  );

  return { catalog, online, jobs, ingest, commandsFor };
}
