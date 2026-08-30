import { useMemo, useState } from "react";
import {
  matchClientSide,
  assessCommands,
  type CatalogEvent,
  type HazardMatch,
} from "../lib/catalog";
import type { IngestState } from "../lib/useAssess";
import HazardIcon from "./HazardIcon";
import type { EventConfig } from "../lib/types";
import type { HazardFC } from "../lib/hazards";

interface Props {
  events: EventConfig[];
  catalog: CatalogEvent[];
  online: boolean | null;
  jobs: Record<string, IngestState>;
  hazards: HazardFC;
  onOpenEvent: (id: string) => void;
  onIngest: (ev: { id: string; name: string; center: [number, number] | null }) => void;
}

/**
 * Live Monitor's bridge to assessment: cross-references the hazards currently
 * shown against the full Maxar catalogue, and offers a one-click ingest (or the
 * commands, with no server). Ingest state is owned by App via useAssess so this
 * and the top-bar picker stay in lockstep.
 */
export default function AssessPanel({
  events,
  catalog,
  online,
  jobs,
  hazards,
  onOpenEvent,
  onIngest,
}: Props) {
  const [q, setQ] = useState("");
  const [showCmd, setShowCmd] = useState<string | null>(null);
  const ingestedIds = useMemo(() => new Set(events.map((e) => e.id)), [events]);

  const matches: HazardMatch[] = useMemo(() => {
    if (!catalog.length || !hazards.features.length) return [];
    return matchClientSide(catalog, hazards, ingestedIds, 300);
  }, [catalog, hazards, ingestedIds]);

  const top = matches.filter((m) => m.score >= 0.35).slice(0, 6);

  // C4 bridge: a strong match whose imagery is genuinely recent — "post-event
  // imagery just published near something you're tracking"
  const fresh = matches.find(
    (m) =>
      !m.ingested &&
      m.type_match &&
      m.imagery_age_days != null &&
      m.imagery_age_days <= 120 &&
      m.distance_km <= 200,
  );

  const searchResults = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return catalog
      .filter(
        (e) => e.name.toLowerCase().includes(s) || e.hazard.includes(s) || e.id.toLowerCase().includes(s),
      )
      .slice(0, 8);
  }, [catalog, q]);

  const act = (ev: { id: string; name: string; center: [number, number] | null }) => {
    if (online) onIngest(ev);
    else setShowCmd((c) => (c === ev.id ? null : ev.id));
  };

  const Row = ({
    id,
    name,
    hazardKind,
    center,
    sub,
  }: {
    id: string;
    name: string;
    hazardKind: string;
    center: [number, number] | null;
    sub: string;
  }) => {
    const job = jobs[id];
    const ingested = ingestedIds.has(id);
    return (
      <li className="rounded-md px-2 py-1.5 hover:bg-surface-2">
        <div className="flex items-start gap-2">
          <HazardIcon hazard={hazardKind} size={13} className="mt-0.5 shrink-0 text-ink-faint" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs text-ink">{name}</div>
            <div className="tnum text-2xs text-ink-faint">{sub}</div>
          </div>
          {ingested ? (
            <button
              onClick={() => onOpenEvent(id)}
              className="pressable rounded-md border border-accent/60 px-2 py-0.5 text-2xs text-ink hover:bg-accent hover:text-[#05171a]"
            >
              Open
            </button>
          ) : (
            <button
              onClick={() => act({ id, name, center })}
              disabled={job?.phase === "running" || !center}
              className="pressable rounded-md border border-line px-2 py-0.5 text-2xs text-ink-dim hover:text-ink disabled:opacity-50"
            >
              {job?.phase === "running" ? "…" : online ? "Ingest" : "How"}
            </button>
          )}
        </div>
        {job?.phase === "running" && (
          <div className="tnum mt-1 pl-[21px] text-2xs text-accent">running · {job.step}</div>
        )}
        {job?.phase === "error" && <div className="mt-1 pl-[21px] text-2xs text-dmg2">{job.error}</div>}
        {showCmd === id && (
          <pre className="mt-1.5 overflow-x-auto rounded bg-canvas px-2 py-1.5 text-[10px] leading-relaxed text-ink-dim">
            {assessCommands({ id, center, name })}
          </pre>
        )}
      </li>
    );
  };

  return (
    <section className="panel px-3.5 py-3.5">
      <div className="mb-1.5 flex items-baseline justify-between">
        <h2 className="section-title">Assess a live hazard</h2>
        <span
          className="cap"
          title={online ? "pipeline server reachable" : "no server — commands shown instead"}
        >
          {online == null ? "" : online ? "server on" : "manual"}
        </span>
      </div>
      <p className="mb-2.5 text-2xs leading-relaxed text-ink-faint">
        Live USGS and GDACS hazards matched to Maxar Open Data imagery. Ingest one
        to run the damage pipeline for that location.
      </p>

      {fresh && (
        <div className="mb-2.5 rounded-md border border-accent/50 bg-accent/10 px-2.5 py-2">
          <div className="text-2xs font-medium text-accent">Fresh imagery available</div>
          <p className="mt-0.5 text-2xs leading-relaxed text-ink-dim">
            <span className="text-ink">{fresh.name}</span> — post-event imagery from{" "}
            {fresh.capture_dates?.[fresh.capture_dates.length - 1]}, {fresh.distance_km.toFixed(0)} km
            from an active {fresh.hazard_type ?? "hazard"}.
          </p>
          <button
            onClick={() => act({ id: fresh.event, name: fresh.name, center: fresh.center })}
            className="pressable mt-1.5 rounded-md border border-accent/60 px-2 py-0.5 text-2xs text-ink hover:bg-accent hover:text-[#05171a]"
          >
            {online ? "Ingest now" : "Show commands"}
          </button>
        </div>
      )}

      {top.length > 0 && (
        <ol className="space-y-0.5">
          {top.map((m) => (
            <Row
              key={m.event}
              id={m.event}
              name={m.name}
              hazardKind={m.hazard_type || ""}
              center={m.center}
              sub={`${m.distance_km.toFixed(0)} km from ${truncate(m.hazard, 24)}${
                m.capture_dates?.length ? ` · imagery ${m.capture_dates[m.capture_dates.length - 1]}` : ""
              }${m.type_match ? "" : " · type differs"}`}
            />
          ))}
        </ol>
      )}
      {catalog.length > 0 && top.length === 0 && (
        <p className="py-2 text-2xs text-ink-faint">
          No live hazard currently sits within Maxar Open Data coverage. Search the
          full catalogue below.
        </p>
      )}

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search all 55 Maxar events…"
        className="mt-2 w-full rounded-md border border-line bg-canvas px-2.5 py-1.5 text-xs text-ink outline-none placeholder:text-ink-faint focus-visible:border-accent"
      />
      {searchResults.length > 0 && (
        <ol className="mt-1 space-y-0.5">
          {searchResults.map((e) => (
            <Row
              key={e.id}
              id={e.id}
              name={e.name}
              hazardKind={e.hazard}
              center={e.center}
              sub={`${e.hazard} · imagery ${e.capture_dates?.[e.capture_dates.length - 1] ?? "?"} · ${e.n_quadkeys} tiles`}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

const truncate = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
