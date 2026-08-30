import { useCallback, useEffect, useRef, useState } from "react";
import {
  loadCatalog,
  serverUp,
  startAssess,
  pollAssess,
  type CatalogEvent,
} from "./catalog";

/**
 * Shared "ingest a Maxar catalogue event" flow, used by both the top-bar event
 * picker and the Live Monitor's Assess panel so there is one code path and one
 * source of truth for job state.
 */
export type IngestPhase = "idle" | "running" | "done" | "error";

export interface IngestState {
  phase: IngestPhase;
  step?: string;
  error?: string;
}

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
      if (!ev.center) {
        setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: "no coordinates for this event" } }));
        return;
      }
      setJobs((j) => ({ ...j, [ev.id]: { phase: "running", step: "starting…" } }));
      const res = await startAssess({
        event: ev.id,
        lat: ev.center[1],
        lon: ev.center[0],
        name: ev.name,
      });
      if (!res) {
        setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: "pipeline server not reachable" } }));
        return;
      }
      if (res.status === "done" || !res.job_id) {
        setJobs((j) => ({ ...j, [ev.id]: { phase: "done" } }));
        onIngested(ev.id);
        return;
      }
      const jobId = res.job_id;
      timers.current[ev.id] = window.setInterval(async () => {
        const st = await pollAssess(jobId);
        if (!st) return;
        if (st.status === "done") {
          window.clearInterval(timers.current[ev.id]);
          setJobs((j) => ({ ...j, [ev.id]: { phase: "done" } }));
          onIngested(ev.id);
        } else if (st.status === "error") {
          window.clearInterval(timers.current[ev.id]);
          setJobs((j) => ({ ...j, [ev.id]: { phase: "error", error: st.error || "pipeline failed" } }));
        } else {
          setJobs((j) => ({ ...j, [ev.id]: { phase: "running", step: st.step || st.status } }));
        }
      }, 2000);
    },
    [onIngested],
  );

  return { catalog, online, jobs, ingest };
}
